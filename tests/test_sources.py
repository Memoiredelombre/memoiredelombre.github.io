"""
Sources d'une fiche objet : affichage en lecture seule sur la fiche (pour
tout le monde), gestion complète (ajout, modification, suppression)
uniquement depuis le formulaire de modification de l'objet, réservé à
l'admin.

Lancer : python3 tests/test_sources.py
Prérequis : python3 tests/build_preview.py (régénère tests/preview.html)
"""
import asyncio
import pathlib
import tempfile
from playwright.async_api import async_playwright

PREVIEW = pathlib.Path(__file__).resolve().parent / "preview.html"
FAILURES = []


def check(label, condition, detail=""):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        errors = []
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"file://{PREVIEW}")
        await page.wait_for_timeout(1000)

        # ---- Invité : objet sans source -> le bloc "Sources" n'apparaît même pas ----
        if await page.locator("#loginCancelBtn").is_visible():
            await page.click("#loginCancelBtn")
        await page.wait_for_timeout(500)
        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(400)
        sources_wrap_empty_guest = await page.locator("#sourcesWrap").inner_html()
        check("un invité ne voit aucun bloc Sources sur un objet qui n'en a pas", sources_wrap_empty_guest.strip() == "")

        # ---- Connexion admin ----
        await page.click("#sidebarLoginBtn")
        await page.wait_for_timeout(300)
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(700)

        # ---- La fiche en consultation (même en admin) n'a pas de gestion de sources ----
        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(400)
        add_btn_on_fiche = await page.locator("#addSourceToggleBtn").count()
        check("aucun bouton d'ajout de source sur la fiche, même en admin", add_btn_on_fiche == 0)

        # ---- Formulaire de modification : la section Sources apparaît ----
        await page.evaluate("() => openForm('edit', ALL_OBJETS[0])")
        await page.wait_for_timeout(300)
        no_source_admin = await page.locator("#sourcesWrapForm .state-msg").count()
        check("le formulaire affiche « Aucune source renseignée » au départ", no_source_admin > 0)

        # ---- Ajoute une source avec lien + document joint ----
        await page.click("#addSourceToggleBtn")
        await page.wait_for_timeout(200)
        await page.select_option("#srcType", "Livre")
        await page.fill("#srcTitre", "Insignes de la Résistance, édition 1986")
        await page.fill("#srcAuteur", "Jean Dupont")
        await page.fill("#srcLien", "https://exemple.fr/reference")
        await page.fill("#srcNote", "Page 42, planche couleur.")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 fake pdf content for test\n")
            tmp_path = tmp.name
        await page.set_input_files("#srcFichier", tmp_path)

        await page.click("#saveSourceBtn")
        await page.wait_for_timeout(500)

        card_count = await page.locator("#sourcesWrapForm .source-card").count()
        check("la source ajoutée apparaît dans le formulaire", card_count == 1, f"{card_count} carte(s)")
        titre_text = await page.locator("#sourcesWrapForm .source-titre").inner_text()
        check("le titre de la source est affiché", "Insignes de la Résistance" in titre_text, titre_text)
        link_count = await page.locator("#sourcesWrapForm .source-links a").count()
        check("le lien et le document joint sont tous les deux affichés", link_count == 2, f"{link_count} lien(s)")

        bucket_has_file = await page.evaluate(
            "() => Object.keys(window.__FAKE_BUCKET__ || {}).some(k => k.startsWith('sources/'))"
        )
        check("le document a bien été envoyé (mock Scaleway)", bucket_has_file)

        # ---- La fiche en consultation affiche maintenant la source, en lecture seule ----
        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(400)
        fiche_card_count = await page.locator("#sourcesWrap .source-card").count()
        check("la source apparaît sur la fiche en consultation", fiche_card_count == 1, f"{fiche_card_count} carte(s)")
        fiche_edit_btn_count = await page.locator("#sourcesWrap .source-edit-btn, #sourcesWrap .source-del-btn").count()
        check("aucun bouton de modification/suppression sur la fiche", fiche_edit_btn_count == 0)

        # ---- Modifie la source depuis le formulaire ----
        await page.evaluate("() => openForm('edit', ALL_OBJETS[0])")
        await page.wait_for_timeout(300)
        await page.click("#sourcesWrapForm .source-edit-btn")
        await page.wait_for_timeout(200)
        source_id = await page.evaluate("() => CURRENT_FICHE_SOURCES[0].id")
        titre_edit_input = page.locator(f"#srcTitre_{source_id}")
        prefilled_value = await titre_edit_input.input_value()
        check("le champ titre du mini-formulaire est pré-rempli", "Insignes de la Résistance" in prefilled_value, prefilled_value)
        await titre_edit_input.fill("Insignes de la Résistance, édition 1986 (corrigée)")
        await page.click(f"#sourceEditForm_{source_id} .btn-primary")
        await page.wait_for_timeout(500)
        titre_after_edit = await page.locator("#sourcesWrapForm .source-titre").inner_text()
        check("le titre modifié est bien enregistré", "corrigée" in titre_after_edit, titre_after_edit)

        # ---- Supprime la source (passe par la modale de confirmation générique) ----
        await page.click("#sourcesWrapForm .source-del-btn")
        await page.wait_for_timeout(200)
        await page.click("#genericConfirmOkBtn")
        await page.wait_for_timeout(400)
        card_count_after = await page.locator("#sourcesWrapForm .source-card").count()
        check("la source supprimée disparaît du formulaire", card_count_after == 0, f"{card_count_after} carte(s)")
        no_source_after = await page.locator("#sourcesWrapForm .state-msg").count()
        check("on retombe sur « Aucune source renseignée » après suppression", no_source_after > 0)

        check("aucune erreur JS pendant le parcours sources", len(errors) == 0, str(errors))

        await browser.close()

        print()
        if FAILURES:
            print(f"{len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
            raise SystemExit(1)
        print("Tous les tests sources sont passés.")


if __name__ == "__main__":
    asyncio.run(main())
