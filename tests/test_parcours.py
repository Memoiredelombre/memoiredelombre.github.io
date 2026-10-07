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

        # ---- Top plus-value : un objet reçu en don (prix d'achat 0 €) compte ----
        await page.evaluate("""() => {
          ALL_OBJETS.forEach(o => { o.prix_achat = 10; o.valeur_estimee_actuelle = 20; });
          const gift = ALL_OBJETS.find(o => o.uid === 'uid-003');
          gift.prix_achat = 0; gift.valeur_estimee_actuelle = 90; gift.titre = 'Insigne reçu en don';
          const unknown = ALL_OBJETS.find(o => o.uid === 'uid-004');
          unknown.prix_achat = null; unknown.valeur_estimee_actuelle = 500;
          switchView('dashboard'); pushNav('dashboard', null); renderDashboard();
        }""")
        await page.wait_for_timeout(300)
        best = await page.locator("#bestPlusValue").inner_text()
        check("le top plus-value retient l'objet reçu à 0 € (plus-value 90 €)", "Insigne reçu en don" in best and "90" in best, best)
        check("un prix d'achat non renseigné reste exclu du top", "Objet test 4" not in best, best)
        n_tiles = await page.locator("#bestPlusValue .best-pv-tile").count()
        check("le top plus-value affiche 4 objets", n_tiles == 4, str(n_tiles))
        first_title = await page.locator("#bestPlusValue .best-pv-tile").first.locator(".best-pv-titre").inner_text()
        check("le n°1 est l'objet à la plus forte plus-value", first_title == "Insigne reçu en don", first_title)
        check("l'objet reçu à 0 € affiche +100 % dans le top", "+100%" in (await page.locator("#bestPlusValue .best-pv-tile").first.inner_text()))
        await page.locator("#bestPlusValue .best-pv-tile").nth(1).click()
        await page.wait_for_timeout(300)
        check("un clic sur une vignette du top ouvre la fiche", await active_view(page) == "view-fiche")
        await page.click("#backBtn")
        await page.wait_for_timeout(300)

        # Fiche de l'objet reçu à 0 € : +100 % à la place du pourcentage
        await page.evaluate("() => openFiche('uid-003')")
        await page.wait_for_timeout(300)
        hero = await page.locator("#ficheContent .mont-hero-card.accent").inner_text()
        check("fiche d'un objet à 0 € : +100 % s'affiche sous la plus-value",
              "+100%" in hero and "90" in hero, hero)
        await page.evaluate("() => openFiche('uid-005')")
        await page.wait_for_timeout(300)
        hero = await page.locator("#ficheContent .mont-hero-card.accent").inner_text()
        check("fiche d'un objet payé : le pourcentage sur le capital investi reste affiché", "%" in hero, hero)

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

        # ---- Création : champs + photos + sources en une seule fois ----
        await page.evaluate("() => openForm('create', null)")
        await page.wait_for_timeout(300)
        check("la page de création propose déjà Photos et Sources",
              await page.locator("#galleryWrapForm").count() == 1 and await page.locator("#sourcesWrapForm").count() == 1)
        check("pas de zone de suppression en création", await page.locator("#deleteObjetBtn").count() == 0)
        check("bouton retour = « Annuler » en création",
              "annuler" in (await page.locator("#formBackBtn").inner_text()).lower())
        await page.fill("#f_titre", "Objet jetable du test")
        await page.select_option("#f_type_objet", index=1)

        # photos : recto + 2 photos supplémentaires, prévisualisées avant envoi
        await page.set_input_files("#galleryWrapForm .photo-upload-row label:nth-child(1) input", png)
        await page.wait_for_timeout(200)
        await page.set_input_files("#galleryWrapForm .extra-photos-row input[type=file]", [png, png])
        await page.wait_for_timeout(300)
        check("le recto choisi est prévisualisé", await page.locator("#galleryWrapForm .photo-upload-row .photo-tile img").count() == 1)
        check("les 2 photos supplémentaires sont prévisualisées", await page.locator("#galleryWrapForm .extra-photos-row .photo-tile img").count() == 2)
        await page.locator("#galleryWrapForm .extra-photos-row .del-btn").first.click()
        await page.wait_for_timeout(200)
        check("on peut retirer une photo avant la création", await page.locator("#galleryWrapForm .extra-photos-row .photo-tile img").count() == 1)

        # source préparée (avec document joint)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 test\n")
            pdf = tmp.name
        await page.click("#addSourceToggleBtn")
        await page.fill("#srcTitre", "Source du test")
        await page.set_input_files("#srcFichier", pdf)
        await page.click("#saveSourceBtn")
        await page.wait_for_timeout(300)
        check("la source préparée apparaît dans la liste",
              await page.locator("#sourcesWrapForm .source-card").count() == 1)
        nothing_yet = await page.evaluate("() => window.__FAKE_SOURCES__.length")
        check("rien n'est envoyé avant « Créer l'objet »", nothing_yet == 0, str(nothing_yet))

        await page.click("#saveObjetBtn")
        await page.wait_for_timeout(2500)
        check("après « Créer », on arrive sur la fiche", await active_view(page) == "view-fiche")
        new_uid = await page.evaluate("() => CURRENT_FICHE_UID")
        photos = await page.evaluate("(u) => (PHOTOS_BY_OBJET[u]||[]).map(p => p.label).sort().join(',')", new_uid)
        check("recto + 1 photo supplémentaire enregistrés avec l'objet", photos == "Autre,Recto", photos)
        sources = await page.evaluate("(u) => window.__FAKE_SOURCES__.filter(s => s.objet_uid === u).length", new_uid)
        check("la source est enregistrée avec l'objet", sources == 1, str(sources))
        check("le document joint est dans le stockage", await page.evaluate(
            "() => Object.keys(window.__FAKE_BUCKET__).some(k => k.startsWith('sources/'))"))
        check("la fiche affiche la source", await page.locator("#sourcesWrap .source-card").count() == 1)

        # ---- Suppression depuis la page de modification ----
        await page.click("#editObjetBtn")
        await page.wait_for_timeout(400)
        await page.click("#deleteObjetBtn")
        await page.wait_for_timeout(300)
        await page.click("#deleteConfirmOkBtn")
        await page.wait_for_timeout(900)
        gone = not await page.evaluate("(u) => ALL_OBJETS.some(o => o.uid === u)", new_uid)
        check("la suppression depuis la page de modification retire l'objet", gone)
        check("on retombe sur le catalogue après suppression", await active_view(page) == "view-catalogue")
        orphan_sources = await page.evaluate("(u) => window.__FAKE_SOURCES__.filter(s => s.objet_uid === u).length", new_uid)
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
