"""
Liste de souhaits : masquée pour les invités, création/ouverture d'un
souhait, restauration du scroll au retour de la fiche, conversion en
objet du catalogue ("Trouvé"), photos gérées depuis la page de modification
(fiche en lecture seule) et photos choisies dès la création.

Lancer : python3 tests/test_wishlist.py
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

    pathlib.Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        errors = []
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"file://{PREVIEW}")
        await page.wait_for_timeout(1000)

        # ---- Invité : onglet Souhaits masqué ----
        if await page.locator("#loginCancelBtn").is_visible():
            await page.click("#loginCancelBtn")
        await page.wait_for_timeout(500)
        wishlist_tab_visible = await page.locator('button[data-view="wishlist"]').is_visible()
        check("l'onglet Souhaits est masqué pour un invité", not wishlist_tab_visible)

        # ---- Connexion admin ----
        # (#loginBtn n'existe que pour le dock mobile — display:none dès
        # 901px ; en desktop c'est #sidebarLoginBtn qui relaie le clic et
        # rouvre la modale, qu'on avait fermée pour le test invité.)
        await page.click("#sidebarLoginBtn")
        await page.wait_for_timeout(300)
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(700)
        wishlist_tab_visible_admin = await page.locator('button[data-view="wishlist"]').is_visible()
        check("l'onglet Souhaits apparaît pour l'admin", wishlist_tab_visible_admin)

        # ---- Ajoute plusieurs souhaits directement (plus rapide que le formulaire) ----
        await page.evaluate(
            """async () => {
                for (let i = 0; i < 15; i++) {
                    await sb.from('wishlist').insert({
                        titre: 'Souhait test ' + i, type_objet: 'Insigne',
                        region: 'Bretagne', departement: '35', indice_rarete: 'M',
                    }).select().single();
                }
                await loadWishlist();
                switchView('wishlist');
            }"""
        )
        await page.wait_for_timeout(400)
        wish_count = await page.locator("#wishlistGrid [data-wish-id]").count()
        check("les souhaits ajoutés apparaissent dans la liste", wish_count == 15, f"{wish_count} affichés")

        # ---- Ouvre un souhait, vérifie la restauration du scroll au retour ----
        await page.evaluate("() => window.scrollTo(0, 400)")
        await page.wait_for_timeout(200)
        scroll_before = await page.evaluate("() => window.scrollY")
        card = page.locator("#wishlistGrid [data-wish-id]").nth(5)
        await card.click()
        await page.wait_for_timeout(300)
        active_view = await page.evaluate("() => document.querySelector('.view.active')?.id")
        check("cliquer une carte ouvre la fiche du souhait", active_view == "view-wish-fiche")

        await page.click("#wishFicheBackBtn")
        await page.wait_for_timeout(300)
        scroll_after = await page.evaluate("() => window.scrollY")
        check(
            "le retour à la liste restaure la position de scroll",
            abs(scroll_after - scroll_before) < 5,
            f"scrollY={scroll_after} attendu≈{scroll_before}",
        )

        # ---- "Trouvé" : convertit un souhait en objet du catalogue ----
        objets_before = await page.evaluate("() => ALL_OBJETS.length")
        wish_uid = await page.evaluate(
            "() => document.querySelector('#wishlistGrid [data-wish-id]').dataset.wishId"
        )
        await page.evaluate(
            """(wishId) => {
                const w = ALL_WISHLIST.find(x => String(x.id) === String(wishId));
                return markWishFoundAndCreate(w);
            }""",
            wish_uid,
        )
        await page.wait_for_timeout(500)
        objets_after = await page.evaluate("() => ALL_OBJETS.length")
        check(
            "« Trouvé » crée bien un nouvel objet dans le catalogue",
            objets_after == objets_before + 1,
            f"{objets_before} -> {objets_after}",
        )
        active_view_after_found = await page.evaluate("() => document.querySelector('.view.active')?.id")
        check("après conversion, on atterrit sur la fiche du nouvel objet", active_view_after_found == "view-fiche")
        wish_count_after = await page.evaluate("() => ALL_WISHLIST.length")
        check("le souhait converti disparaît de la liste des souhaits", wish_count_after == 14, f"{wish_count_after} restants")

        # ---- Photos : fiche en lecture seule, gestion dans la page de modification ----
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            png = tmp.name
        tiny_png(png)
        wid = await page.evaluate("() => ALL_WISHLIST[0].id")
        await page.evaluate("(id) => openWishFiche(ALL_WISHLIST.find(x => x.id === id))", wid)
        await page.wait_for_timeout(300)
        n_controls = await page.locator("#wishFicheGalleryWrap input[type=file], #wishFicheGalleryWrap .edit-btn, #wishFicheGalleryWrap .del-btn").count()
        check("la fiche d'un souhait n'a aucun contrôle d'ajout/modification de photo", n_controls == 0, str(n_controls))
        await page.click("#wishFicheEditBtn")
        await page.wait_for_timeout(300)
        check("« Modifier » ouvre la page de modification du souhait",
              await page.evaluate("() => document.querySelector('.view.active')?.id") == "view-wish-form")
        back = (await page.locator("#wishFormBackBtn").inner_text()).strip()
        check("le bouton retour dit « Retour au souhait »", "souhait" in back.lower(), back)
        check("la page de modification propose la section Photos",
              await page.locator("#wishGalleryWrapForm input[type=file]").count() >= 3)
        await page.set_input_files("#wishGalleryWrapForm .photo-upload-row label:nth-child(1) input", png)
        await page.wait_for_timeout(1500)
        has_recto = await page.evaluate("(id) => (WISHLIST_PHOTOS_BY_ID[id]||[]).some(p => p.label === 'Recto')", wid)
        check("le recto ajouté depuis la page de modification est enregistré", has_recto)
        check("la photo apparaît dans la page de modification",
              await page.locator("#wishGalleryWrapForm .photo-tile:not(.empty) img").count() >= 1)
        await page.click("#wishFormBackBtn")
        await page.wait_for_timeout(300)
        check("« Retour au souhait » revient sur la fiche",
              await page.evaluate("() => document.querySelector('.view.active')?.id") == "view-wish-fiche")
        check("la fiche affiche la photo ajoutée", await page.locator("#wishFicheGalleryWrap .photo-tile:not(.empty) img").count() >= 1)

        # ---- Création : photos choisies avant « Enregistrer » ----
        await page.evaluate("() => openWishForm(null)")
        await page.wait_for_timeout(300)
        await page.fill("#wf_titre", "Souhait avec photos")
        await page.select_option("#wf_type_objet", index=1)
        await page.set_input_files("#wishGalleryWrapForm .photo-upload-row label:nth-child(1) input", png)
        await page.set_input_files("#wishGalleryWrapForm .extra-photos-row input[type=file]", png)
        await page.wait_for_timeout(300)
        check("les photos choisies sont prévisualisées avant l'enregistrement",
              await page.locator("#wishGalleryWrapForm .photo-tile img").count() == 2)
        await page.click("#wishSaveBtn")
        await page.wait_for_timeout(2500)
        check("après l'enregistrement, on arrive sur la fiche du souhait",
              await page.evaluate("() => document.querySelector('.view.active')?.id") == "view-wish-fiche")
        new_id = await page.evaluate("() => ALL_WISHLIST.find(w => w.titre === 'Souhait avec photos')?.id")
        labels = await page.evaluate("(id) => (WISHLIST_PHOTOS_BY_ID[id]||[]).map(p => p.label).sort().join(',')", new_id)
        check("recto + photo supplémentaire enregistrés avec le souhait", labels == "Autre,Recto", labels)

        check("aucune erreur JS pendant le parcours souhaits", len(errors) == 0, str(errors))

        await browser.close()

        print()
        if FAILURES:
            print(f"{len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
            raise SystemExit(1)
        print("Tous les tests souhaits sont passés.")


if __name__ == "__main__":
    asyncio.run(main())
