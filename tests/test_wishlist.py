"""
Liste de souhaits : masquée pour les invités, création/ouverture d'un
souhait, restauration du scroll au retour de la fiche, conversion en
objet du catalogue ("Trouvé").

Lancer : python3 tests/test_wishlist.py
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

        check("aucune erreur JS pendant le parcours souhaits", len(errors) == 0, str(errors))

        await browser.close()

        print()
        if FAILURES:
            print(f"{len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
            raise SystemExit(1)
        print("Tous les tests souhaits sont passés.")


if __name__ == "__main__":
    asyncio.run(main())
