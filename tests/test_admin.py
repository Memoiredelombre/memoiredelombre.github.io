"""
Connexion admin et formulaire objet : identifiants valides/invalides,
champs privés visibles une fois connecté, état de chargement du bouton
Enregistrer, création d'un objet, et le select "Département" (liste fixe +
saisie libre via "Autre").

Lancer : python3 tests/test_admin.py
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

        # ---- Mauvais identifiants : message d'erreur, reste invité ----
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "mauvais-mot-de-passe")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(500)
        login_error = await page.locator("#loginMsg").inner_text()
        check("mauvais identifiants -> message d'erreur affiché", "incorrect" in login_error.lower(), login_error)

        # ---- Bons identifiants : passe en admin ----
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(700)
        is_admin = await page.evaluate("() => IS_ADMIN")
        check("bons identifiants -> IS_ADMIN devient true", is_admin is True)
        modal_hidden = await page.evaluate(
            "() => document.getElementById('loginModal').style.display === 'none'"
        )
        check("la modale de connexion se ferme après connexion", modal_hidden)

        # ---- Champs privés visibles en admin sur une fiche ----
        await page.evaluate("() => openFiche(ALL_OBJETS[0].uid)")
        await page.wait_for_timeout(300)
        locked_panel_visible = await page.locator("text=Informations privées").count()
        check("le bloc « Informations privées » apparaît en mode admin", locked_panel_visible > 0)

        # ---- Formulaire : création d'un objet ----
        await page.evaluate("() => openForm('create', null)")
        await page.wait_for_timeout(300)
        save_btn_label_create = await page.locator("#saveObjetBtn").inner_text()
        check(
            "le bouton du formulaire de création dit « Créer l'objet »",
            "créer" in save_btn_label_create.lower(),
            save_btn_label_create,
        )

        titre_input = page.locator("#f_titre")
        if await titre_input.count() == 0:
            titre_input = page.locator('[id^="f_titre"]').first
        await titre_input.fill("Objet créé par le test")
        type_select = page.locator("#f_type_objet, select[id*='type_objet']").first
        if await type_select.count() > 0:
            await type_select.select_option(index=1)

        await page.click("#saveObjetBtn")
        await page.wait_for_timeout(200)
        btn_during = await page.locator("#saveObjetBtn").inner_text()
        check(
            "le bouton affiche un texte de chargement pendant l'enregistrement",
            "enregistr" in btn_during.lower() or "créat" in btn_during.lower(),
            btn_during,
        )
        await page.wait_for_timeout(600)
        # Photos et sources préparées dans le formulaire sont envoyées avec
        # la création : une fois tout enregistré, on arrive sur la fiche.
        active_view = await page.evaluate("() => document.querySelector('.view.active')?.id")
        check("après « Créer », on atterrit sur la fiche du nouvel objet", active_view == "view-fiche")

        # ---- Formulaire : édition d'un objet existant ----
        # (par uid plutôt que ALL_OBJETS[0] : la création d'un objet juste
        # au-dessus, suivie d'un loadAll() trié par id_public, peut avoir
        # fait passer l'objet nouvellement créé — sans id_public — en
        # première position du tableau.)
        edit_target_uid = await page.evaluate("() => ALL_OBJETS.find(o => o.uid === 'uid-000').uid")
        await page.evaluate(
            "(uid) => openForm('edit', ALL_OBJETS.find(o => o.uid === uid))",
            edit_target_uid,
        )
        await page.wait_for_timeout(300)
        save_btn_label_edit = await page.locator("#saveObjetBtn").inner_text()
        check(
            "le bouton du formulaire d'édition dit « Enregistrer les modifications »",
            "enregistrer" in save_btn_label_edit.lower(),
            save_btn_label_edit,
        )

        # ---- Département : select fixe + saisie libre via "Autre" ----
        dept_hidden_initial = await page.locator("#f_departement").input_value()
        check(
            "le champ département caché reprend la valeur initiale de l'objet",
            dept_hidden_initial == "35 Ille-et-Vilaine",
            dept_hidden_initial,
        )
        await page.select_option("#f_departement_select", "__autre__")
        await page.wait_for_timeout(100)
        autre_visible = await page.locator("#f_departement_autre").is_visible()
        check("choisir « Autre » révèle le champ de saisie libre", autre_visible)
        await page.fill("#f_departement_autre", "Zone occupée (non précisée)")
        dept_hidden_after_custom = await page.locator("#f_departement").input_value()
        check(
            "la saisie libre met à jour le département réellement enregistré",
            dept_hidden_after_custom == "Zone occupée (non précisée)",
            dept_hidden_after_custom,
        )
        await page.select_option("#f_departement_select", "29 Finistère")
        dept_hidden_after_reselect = await page.locator("#f_departement").input_value()
        check(
            "revenir à une valeur fixe de la liste remet à jour le département enregistré",
            dept_hidden_after_reselect == "29 Finistère",
            dept_hidden_after_reselect,
        )

        # ---- Déconnexion : repasse en invité, champs privés masqués ----
        # (#loginBtn n'existe que pour le dock mobile — display:none dès
        # 901px ; en desktop c'est #sidebarLoginBtn qui relaie le clic)
        await page.click("#sidebarLoginBtn")
        await page.wait_for_timeout(600)
        is_admin_after_logout = await page.evaluate("() => IS_ADMIN")
        check("la déconnexion repasse IS_ADMIN à false", is_admin_after_logout is False)

        check("aucune erreur JS pendant le parcours admin", len(errors) == 0, str(errors))

        await browser.close()

        print()
        if FAILURES:
            print(f"{len(FAILURES)} échec(s) : " + ", ".join(FAILURES))
            raise SystemExit(1)
        print("Tous les tests admin sont passés.")


if __name__ == "__main__":
    asyncio.run(main())
