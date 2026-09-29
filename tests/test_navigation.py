"""
Parcours catalogue / fiche / navigation : mode invité, scroll infini,
ouverture de fiche, retour (bouton in-app + bouton "précédent" du
navigateur) avec restauration de la position de scroll.

Lancer : python3 tests/test_navigation.py
Prérequis : python3 tests/build_preview.py (régénère tests/preview.html)
"""
import asyncio
import pathlib
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

        # ---- Mode invité : on ferme la modale de connexion ----
        if await page.locator("#loginCancelBtn").is_visible():
            await page.click("#loginCancelBtn")
        await page.wait_for_timeout(800)

        is_admin = await page.evaluate("() => IS_ADMIN")
        check("mode invité par défaut (IS_ADMIN=false)", is_admin is False)

        # ---- Catalogue : rendu initial ----
        await page.click('nav.tabs button[data-view="catalogue"]')
        await page.wait_for_timeout(500)
        tile_count = await page.locator("#catalogueGrid [data-uid]").count()
        check("le catalogue affiche des tuiles", tile_count > 0, f"{tile_count} tuiles")

        # ---- Gonfle la collection à 100 objets pour tester le scroll infini ----
        await page.evaluate(
            """() => {
                const base = ALL_OBJETS[0];
                for (let i = 0; i < 70; i++) {
                    ALL_OBJETS.push(Object.assign({}, base, {
                        uid: 'extra-' + i, id_public: 'EXTRA-' + i, titre: 'Objet supplémentaire ' + i,
                    }));
                }
                renderGrid('Tous', '');
            }"""
        )
        await page.wait_for_timeout(300)
        rendered_first_batch = await page.evaluate("() => CATALOGUE_RENDERED")
        check(
            "premier lot limité à 30 (scroll infini, pas tout d'un coup)",
            rendered_first_batch == 30,
            f"rendu={rendered_first_batch}",
        )

        for _ in range(6):
            h = await page.evaluate("() => document.documentElement.scrollHeight")
            await page.evaluate("(h) => window.scrollTo(0, h)", h)
            await page.wait_for_timeout(350)
            if await page.evaluate("() => CATALOGUE_RENDERED") >= 70:
                break
        rendered_after_scroll = await page.evaluate("() => CATALOGUE_RENDERED")
        check(
            "le scroll infini charge des lots supplémentaires",
            rendered_after_scroll > 30,
            f"rendu={rendered_after_scroll}",
        )

        # ---- Ouvre une fiche loin dans la liste, vérifie la sauvegarde du scroll ----
        tile = page.locator("#catalogueGrid [data-uid]").nth(40)
        await tile.scroll_into_view_if_needed()
        await page.wait_for_timeout(200)
        scroll_before = await page.evaluate("() => window.scrollY")
        await tile.click()
        await page.wait_for_timeout(400)
        active_view = await page.evaluate("() => document.querySelector('.view.active')?.id")
        check("le clic sur une tuile ouvre la fiche", active_view == "view-fiche")
        saved_y = await page.evaluate("() => CATALOGUE_SCROLL_Y")
        check(
            "la position de scroll est mémorisée avant d'ouvrir la fiche",
            abs(saved_y - scroll_before) < 2,
            f"sauvegardé={saved_y} attendu≈{scroll_before}",
        )

        # ---- Bouton "Retour" in-app : la position doit être restaurée ----
        await page.click("#backBtn")
        await page.wait_for_timeout(400)
        scroll_after_back = await page.evaluate("() => window.scrollY")
        check(
            "le bouton Retour restaure la position de scroll",
            abs(scroll_after_back - scroll_before) < 5,
            f"scrollY={scroll_after_back} attendu≈{scroll_before}",
        )

        # ---- Bouton "précédent" du navigateur (popstate) : même chose ----
        await tile.scroll_into_view_if_needed()
        await page.wait_for_timeout(200)
        scroll_before2 = await page.evaluate("() => window.scrollY")
        await tile.click()
        await page.wait_for_timeout(400)
        await page.go_back()
        await page.wait_for_timeout(400)
        scroll_after_popstate = await page.evaluate("() => window.scrollY")
        check(
            "le bouton précédent du navigateur restaure aussi la position",
            abs(scroll_after_popstate - scroll_before2) < 5,
            f"scrollY={scroll_after_popstate} attendu≈{scroll_before2}",
        )

        # ---- Champs privés absents en mode invité ----
        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(300)
        locked_panel_visible = await page.locator("text=Informations privées").count()
        check("le bloc « Informations privées » est absent en mode invité", locked_panel_visible == 0)

        check("aucune erreur JS pendant le parcours", len(errors) == 0, str(errors))

        await browser.close()

        print()
        if FAILURES:
            print(f"{len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
            raise SystemExit(1)
        print("Tous les tests de navigation sont passés.")


if __name__ == "__main__":
    asyncio.run(main())
