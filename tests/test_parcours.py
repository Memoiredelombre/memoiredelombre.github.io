"""
Parcours utilisateur simplifié : titre « Sources » unique, bouton Retour qui
ramène à l'écran d'origine (catalogue / galerie / dashboard), pied de page
sans mention technique pour les invités, bouton « Filtres », et page de
modification unique (champs + photos + sources + suppression) alors que la
fiche reste en lecture seule.

Lancer : python3 tests/test_parcours.py
Prérequis : python3 tests/build_preview.py (régénère tests/preview.html)
"""
import asyncio
import pathlib
import struct
import tempfile
import zlib
from playwright.async_api import async_playwright

PREVIEW = pathlib.Path(__file__).resolve().parent / "preview.html"
FAILURES = []


def check(label, condition, detail=""):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def tiny_png(path):
    """PNG 8x8 valide (le code compresse via <canvas>, il lui faut une vraie image)."""
    w = h = 8
    raw = b"".join(b"\x00" + b"\xc8\x40\x40" * w for _ in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    pathlib.Path(path).write_bytes(data)


async def active_view(page):
    return await page.evaluate("() => document.querySelector('.view.active')?.id")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        errors = []
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"file://{PREVIEW}")
        await page.wait_for_timeout(1000)
        if await page.locator("#loginCancelBtn").is_visible():
            await page.click("#loginCancelBtn")
        await page.wait_for_timeout(500)

        # ---- Invité : pied de page et bouton « Filtres » ----
        foot_visible = await page.locator(".foot-status").first.is_visible()
        check("un invité ne voit pas « Connecté à votre base Supabase »", not foot_visible)
        label = (await page.locator("#advSearchToggle .btn-label").inner_text()).strip()
        check("le bouton de recherche avancée s'appelle « Filtres »", label == "Filtres", label)

        # ---- Bouton Retour : catalogue ----
        await page.evaluate("() => { switchView('catalogue'); }")
        await page.wait_for_timeout(300)
        await page.locator("#view-catalogue [data-uid]").first.click()
        await page.wait_for_timeout(300)
        check("fiche ouverte depuis le catalogue", await active_view(page) == "view-fiche")
        back_txt = (await page.locator("#backBtn").inner_text()).strip()
        check("le bouton dit « Retour au catalogue »", "catalogue" in back_txt.lower(), back_txt)
        await page.click("#backBtn")
        await page.wait_for_timeout(300)
        check("Retour ramène au catalogue", await active_view(page) == "view-catalogue")

        # ---- Bouton Retour : galerie ----
        await page.evaluate("() => { switchView('galerie'); pushNav('galerie', null); }")
        await page.wait_for_timeout(500)
        await page.locator("#view-galerie .ig-tile").first.click()
        await page.wait_for_timeout(300)
        check("fiche ouverte depuis la galerie", await active_view(page) == "view-fiche")
        back_txt = (await page.locator("#backBtn").inner_text()).strip()
        check("le bouton dit « Retour à la galerie »", "galerie" in back_txt.lower(), back_txt)
        await page.click("#backBtn")
        await page.wait_for_timeout(300)
        check("Retour ramène à la galerie", await active_view(page) == "view-galerie")

        # ---- Bouton Retour : dashboard ----
        await page.evaluate("() => { switchView('dashboard'); pushNav('dashboard', null); }")
        await page.wait_for_timeout(300)
        row = page.locator("#view-dashboard [data-uid]").first
        if await row.count() > 0:
            await row.click()
            await page.wait_for_timeout(300)
            check("fiche ouverte depuis le dashboard", await active_view(page) == "view-fiche")
            back_txt = (await page.locator("#backBtn").inner_text()).strip()
            check("le bouton dit « Retour au dashboard »", "dashboard" in back_txt.lower(), back_txt)
            await page.click("#backBtn")
            await page.wait_for_timeout(300)
            check("Retour ramène au dashboard", await active_view(page) == "view-dashboard")
        else:
            check("une ligne cliquable existe sur le dashboard", False, "aucun [data-uid]")

        # ---- Connexion admin ----
        await page.click("#sidebarLoginBtn")
        await page.wait_for_timeout(300)
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(700)
        check("l'admin voit le statut de connexion en pied de page", await page.locator(".foot-status").first.is_visible())

        # ---- Fiche en lecture seule (même en admin) ----
        await page.evaluate("() => openFiche('uid-000')")
        await page.wait_for_timeout(400)
        btns = [t.strip() for t in await page.locator("#ficheContent .header-actions button").all_inner_texts()]
        check("la fiche n'a que le bouton « Modifier »", btns == ["Modifier"], str(btns))
        n_edit = await page.locator("#galleryWrap .edit-btn, #galleryWrap .del-btn, #galleryWrap input[type=file]").count()
        check("aucun contrôle d'ajout/modification de photo sur la fiche", n_edit == 0, str(n_edit))
        n_imgs = await page.locator("#galleryWrap .photo-tile img").count()
        check("la fiche affiche toujours les photos", n_imgs >= 1, str(n_imgs))
        check("pas de bouton « Supprimer l'objet » sur la fiche", await page.locator("#ficheContent #deleteObjetBtn").count() == 0)

        # ---- Page de modification unique ----
        await page.click("#editObjetBtn")
        await page.wait_for_timeout(400)
        check("« Modifier » ouvre la page de modification", await active_view(page) == "view-form")
        back_form = (await page.locator("#formBackBtn").inner_text()).strip()
        check("le bouton retour du formulaire dit « Retour à la fiche »", "fiche" in back_form.lower(), back_form)
        titles = [t.strip().lower() for t in await page.locator("#formContent h4").all_inner_texts()]
        check("un seul titre « Sources » dans la page de modification", titles.count("sources") == 1, str(titles))
        check("la section Photos est présente", "photos" in titles, str(titles))
        check("le bloc de suppression est présent", await page.locator("#formContent #deleteObjetBtn").count() == 1)
        check("le Recto existant est modifiable", await page.locator("#galleryWrapForm .edit-btn").count() >= 1)

        # Ajout d'une photo supplémentaire depuis la page de modification
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            png = tmp.name
        tiny_png(png)
        before = await page.evaluate("() => (PHOTOS_BY_OBJET['uid-000']||[]).length")
        await page.set_input_files("#galleryWrapForm .extra-photos-row input[type=file]", png)
        await page.wait_for_timeout(1500)
        after = await page.evaluate("() => (PHOTOS_BY_OBJET['uid-000']||[]).length")
        check("la photo ajoutée est enregistrée", after == before + 1, f"{before} -> {after}")
        extra_tiles = await page.locator("#galleryWrapForm .extra-photos-row .photo-tile.small:not(.empty)").count()
        check("la nouvelle photo apparaît dans la page de modification", extra_tiles == 1, str(extra_tiles))

        # Supprime cette photo
        await page.click("#galleryWrapForm .del-btn")
        await page.wait_for_timeout(200)
        await page.click("#genericConfirmOkBtn")
        await page.wait_for_timeout(700)
        final = await page.evaluate("() => (PHOTOS_BY_OBJET['uid-000']||[]).length")
        check("la photo supprimée disparaît", final == before, f"{final} attendu {before}")

        # Retour à la fiche
        await page.click("#formBackBtn")
        await page.wait_for_timeout(300)
        check("« Retour à la fiche » revient sur la fiche", await active_view(page) == "view-fiche")

        # ---- Création en 3 étapes puis suppression depuis la page de modification ----
        await page.evaluate("() => openForm('create', null)")
        await page.wait_for_timeout(300)
        check("pas de section Photos/Sources/Suppression avant la création",
              await page.locator("#galleryWrapForm, #sourcesWrapForm, #deleteObjetBtn").count() == 0)
        check("bouton retour = « Annuler » en création",
              "annuler" in (await page.locator("#formBackBtn").inner_text()).lower())
        await page.fill("#f_titre", "Objet jetable du test")
        await page.select_option("#f_type_objet", index=1)
        await page.click("#saveObjetBtn")
        await page.wait_for_timeout(800)
        check("après « Créer », on est sur la page de modification avec Photos + Sources",
              await active_view(page) == "view-form" and await page.locator("#galleryWrapForm").count() == 1
              and await page.locator("#sourcesWrapForm").count() == 1)
        new_uid = await page.evaluate("() => FORM_UID")
        check("le nouvel objet existe en base", new_uid is not None and await page.evaluate(
            "(u) => ALL_OBJETS.some(o => o.uid === u)", new_uid))

        # Ajoute une source à l'objet tout juste créé, puis supprime l'objet
        await page.click("#addSourceToggleBtn")
        await page.fill("#srcTitre", "Source du test")
        await page.click("#saveSourceBtn")
        await page.wait_for_timeout(500)
        check("une source peut être ajoutée juste après la création",
              await page.locator("#sourcesWrapForm .source-card").count() == 1)

        await page.click("#deleteObjetBtn")
        await page.wait_for_timeout(300)
        await page.click("#deleteConfirmOkBtn")
        await page.wait_for_timeout(900)
        gone = not await page.evaluate("(u) => ALL_OBJETS.some(o => o.uid === u)", new_uid)
        check("la suppression depuis la page de modification retire l'objet", gone)
        check("on retombe sur le catalogue après suppression", await active_view(page) == "view-catalogue")
        orphan_sources = await page.evaluate("(u) => (window.__FAKE_SOURCES__||[]).filter(s => s.objet_uid === u).length", new_uid)
        check("les sources de l'objet supprimé sont supprimées aussi", orphan_sources == 0, str(orphan_sources))

        check("aucune erreur JS pendant le parcours", len(errors) == 0, str(errors))
        await browser.close()

        print()
        if FAILURES:
            print(f"{len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
            raise SystemExit(1)
        print("Tous les tests de parcours sont passés.")


if __name__ == "__main__":
    asyncio.run(main())
