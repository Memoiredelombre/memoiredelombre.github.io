"""
Sources d'une fiche objet : masquées de l'ajout pour un invité (lecture
seule), ajout d'une source avec lien + document joint par l'admin,
affichage sur la fiche, puis suppression.

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

        # ---- Invité : la fiche n'a pas de bouton d'ajout de source ----
        if await page.locator("#loginCancelBtn").is_visible():
            await page.click("#loginCancelBtn")
        await page.wait_for_timeout(500)
        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(400)
        no_source_guest = await page.locator("#sourcesWrap .state-msg").count()
        check("un invité voit « Aucune source renseignée »", no_source_guest > 0)
        add_btn_guest = await page.locator("#addSourceToggleBtn").count()
        check("un invité n'a pas de bouton pour ajouter une source", add_btn_guest == 0)

        # ---- Connexion admin ----
        await page.click("#sidebarLoginBtn")
        await page.wait_for_timeout(300)
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(700)

        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(400)
        no_source_admin = await page.locator("#sourcesWrap .state-msg").count()
        check("l'admin voit aussi « Aucune source renseignée » au départ", no_source_admin > 0)

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

        card_count = await page.locator("#sourcesWrap .source-card").count()
        check("la source ajoutée apparaît sur la fiche", card_count == 1, f"{card_count} carte(s)")
        titre_text = await page.locator("#sourcesWrap .source-titre").inner_text()
        check("le titre de la source est affiché", "Insignes de la Résistance" in titre_text, titre_text)
        link_count = await page.locator("#sourcesWrap .source-links a").count()
        check("le lien et le document joint sont tous les deux affichés", link_count == 2, f"{link_count} lien(s)")

        bucket_has_file = await page.evaluate(
            "() => Object.keys(window.__FAKE_BUCKET__ || {}).some(k => k.startsWith('sources/'))"
        )
        check("le document a bien été envoyé (mock Scaleway)", bucket_has_file)

        # ---- Supprime la source (passe par la modale de confirmation générique) ----
        await page.click("#sourcesWrap .source-del-btn")
        await page.wait_for_timeout(200)
        await page.click("#genericConfirmOkBtn")
        await page.wait_for_timeout(400)
        card_count_after = await page.locator("#sourcesWrap .source-card").count()
        check("la source supprimée disparaît de la fiche", card_count_after == 0, f"{card_count_after} carte(s)")
        no_source_after = await page.locator("#sourcesWrap .state-msg").count()
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
