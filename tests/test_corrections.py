"""
Non-régression des corrections issues de l'audit :
 1. liens des Notes : un guillemet dans une URL ne peut plus injecter de code
 2. liens de sources : seules les adresses http(s)/www deviennent cliquables
 3. plus-value du dashboard calculée sur les objets ayant prix ET valeur
 4. barres cliquables (fabricants, régions) : noms avec guillemets/antislash OK,
    et le catalogue affiche exactement le nombre indiqué par la barre

Lancer : python3 tests/test_corrections.py
Prérequis : python3 tests/build_preview.py
"""
import asyncio
import pathlib
from playwright.async_api import async_playwright

PREVIEW = pathlib.Path(__file__).resolve().parent / "preview.html"
FAILURES = []


def check(label, condition, detail=""):
    print(f"[{'OK' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"file://{PREVIEW}")
        await page.wait_for_timeout(1000)
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(1500)

        # ---- 1. Notes : pas d'injection d'attribut ----
        r = await page.evaluate("""() => {
            const d = document.createElement('div');
            d.innerHTML = formatRichText('Voir http://a.com/x"onmouseover="window.__pwn=1" fin');
            const a = d.querySelector('a');
            return { attrs: [...a.attributes].map(x => x.name), nb: d.querySelectorAll('a').length };
        }""")
        check("notes : aucun attribut injecté par un guillemet dans l'URL", "onmouseover" not in r["attrs"], str(r))
        r = await page.evaluate("() => formatRichText('lien http://a.com/**x** ok **gras** et *ital*')")
        check("notes : les * dans une URL ne cassent pas le lien", 'href="http://a.com/**x**"' in r, r)
        check("notes : gras et italique toujours pris en charge", "<strong>gras</strong>" in r and "<em>ital</em>" in r, r)
        check("notes : lien www. complété en https", 'href="https://www.exemple.fr"' in await page.evaluate("() => formatRichText('www.exemple.fr')"))
        await page.evaluate("() => { ALL_OBJETS[5].notes = 'x http://a.com/x\"onmouseover=\"window.__pwn=1\" y'; showFiche(ALL_OBJETS[5].uid); }")
        await page.wait_for_timeout(600)
        await page.locator(".rich-text a").first.hover()
        await page.wait_for_timeout(200)
        check("notes : le survol d'un lien piégé n'exécute rien", await page.evaluate("() => window.__pwn") is None)

        # ---- 2. Sources : javascript: non cliquable ----
        r = await page.evaluate("""() => [safeLinkUrl('javascript:alert(1)'), safeLinkUrl(' https://a.fr/x '), safeLinkUrl('www.a.fr'), safeLinkUrl('data:text/html,x')]""")
        check("sources : javascript: et data: refusés, http(s)/www acceptés",
              r == ["", "https://a.fr/x", "https://www.a.fr", ""], str(r))

        # ---- 3. Plus-value sur objets comparables ----
        r = await page.evaluate("""() => {
            ALL_OBJETS.length = 3;
            Object.assign(ALL_OBJETS[0], {prix_achat: 100, valeur_estimee_actuelle: 150});
            Object.assign(ALL_OBJETS[1], {prix_achat: null, valeur_estimee_actuelle: 200});
            Object.assign(ALL_OBJETS[2], {prix_achat: 50, valeur_estimee_actuelle: null});
            renderDashboard();
            const g = id => document.getElementById(id).textContent;
            return { pv: g('kpiPlusValue'), pct: g('kpiPlusValuePct'), moy: g('kpiPlusValueMoy') };
        }""")
        check("plus-value : 50 € (et non 200 €) sur l'objet comparable", r["pv"].startswith("50,00"), str(r))
        check("plus-value : +50 % sur 1 objet", r["pct"].startswith("+50%") and "1 objet" in r["pct"], str(r))
        check("plus-value : moyenne sur les objets comparables", r["moy"].startswith("50,00"), str(r))
        r = await page.evaluate("""() => {
            ALL_OBJETS.forEach(o => { o.prix_achat = null; o.valeur_estimee_actuelle = null; });
            renderDashboard();
            return document.getElementById('kpiPlusValue').textContent + '|' + document.getElementById('kpiPlusValuePct').textContent;
        }""")
        check("plus-value : sans objet comparable, tirets (pas de 0,00 €)", r == "—|—", r)

        # ---- 4. Barres cliquables ----
        await page.reload()
        await page.wait_for_timeout(1000)
        await page.fill("#loginEmail", "admin@test.fr")
        await page.fill("#loginPassword", "test1234")
        await page.click("#loginSubmitBtn")
        await page.wait_for_timeout(1500)
        await page.evaluate("""() => {
            ALL_OBJETS.forEach(o => { o.fabricant = null; o.region = null; });
            ALL_OBJETS[0].fabricant = 'Maison "Dupont" & Fils';
            ALL_OBJETS[1].fabricant = 'Maison "Dupont" & Fils';
            ALL_OBJETS[2].fabricant = "L'Atelier";
            ALL_OBJETS[3].fabricant = 'Back\\\\slash';
            ALL_OBJETS[4].titre = 'Proche de Maison "Dupont" & Fils';
            ALL_OBJETS[5].notes = "cité : L'Atelier";
            ALL_OBJETS[0].region = 'Bretagne'; ALL_OBJETS[1].region = 'Bretagne; Normandie';
            ALL_OBJETS[6].titre = 'Insigne de Bretagne'; ALL_OBJETS[7].notes = 'trouvé en Bretagne';
            renderFabricantChart(); renderDepartementChart();
            switchView('dashboard');
        }""")
        await page.wait_for_timeout(500)
        rows = page.locator("#fabricantList .prov-row")
        for i in range(await rows.count()):
            txt = (await rows.nth(i).inner_text()).replace("\n", " ")
            n_bar = int(txt.rsplit(" ", 1)[1])
            nom = txt.rsplit(" ", 1)[0]
            before = len(errors)
            await rows.nth(i).click()
            await page.wait_for_timeout(400)
            tuiles = await page.evaluate("() => CATALOGUE_ITEMS.length")
            tag = await page.evaluate("() => document.getElementById('quickFilterTag').textContent")
            check(f"fabricant « {nom} » : le catalogue affiche {n_bar} objet(s) comme la barre", tuiles == n_bar and len(errors) == before, f"{tuiles} vs {n_bar} {errors[before:]}")
            check(f"fabricant « {nom} » : puce de filtre visible", "Fabricant" in tag, tag)
            await page.evaluate("() => switchView('dashboard')")
            await page.wait_for_timeout(300)
        # région exacte
        row = page.locator("#departementList .prov-row", has_text="Bretagne").first
        txt = (await row.inner_text()).replace("\n", " ")
        n_bar = int(txt.rsplit(" ", 1)[1])
        await row.click()
        await page.wait_for_timeout(400)
        tuiles = await page.evaluate("() => CATALOGUE_ITEMS.length")
        check("région Bretagne : le catalogue affiche exactement le nombre de la barre", tuiles == n_bar == 2, f"{tuiles} vs {n_bar}")
        # on retire le filtre avec la croix
        await page.click("#quickFilterTag button")
        await page.wait_for_timeout(300)
        total = await page.evaluate("() => ALL_OBJETS.length")
        check("la croix de la puce retire le filtre", await page.evaluate("() => CATALOGUE_ITEMS.length") == total)
        check("aucune erreur JavaScript", not errors, str(errors))

        await browser.close()
    if FAILURES:
        print(f"\n{len(FAILURES)} échec(s) :", *FAILURES, sep="\n - ")
        raise SystemExit(1)
    print("\nTous les tests de corrections sont passés.")


asyncio.run(main())
