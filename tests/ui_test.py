"""Test d'interaction du HTML dbschema (Playwright + Chrome installe). Usage : python ui_test.py <html> <dossier_captures>"""
import os, sys, pathlib
from playwright.sync_api import sync_playwright
# Chrome installe (DBSCHEMA_CHROME pour un autre chemin) ; a defaut, le Chromium de Playwright
CHROME = os.environ.get('DBSCHEMA_CHROME') or next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') if os.path.exists(p)), None)

html, shots = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2])
shots.mkdir(exist_ok=True)
errors, results = [], []

def ok(name, cond, detail=''):
    results.append((name, bool(cond), detail))

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_page(viewport={'width': 1600, 'height': 1000})
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(html.as_uri())
    pg.wait_for_timeout(300)
    ok('vue initiale = all', pg.locator('.view[data-view="all"]').is_visible())
    # cibles tirees des donnees de la page (aucune valeur propre a un schema) : table la plus reliee, domaine le plus grand
    info = pg.evaluate('''() => { const deg = {}; for (const r of D.relations) for (const t of [r.from, r.to]) deg[t] = (deg[t] || 0) + 1;
      const tables = Object.keys(D.tables), top = tables.sort((a, b) => (deg[b] || 0) - (deg[a] || 0))[0];
      const out = tables.filter((t) => D.relations.some((r) => r.from === t)).sort((a, b) => b.length - a.length)[0] || top;
      const g = Object.keys(D.groups).sort((a, b) => D.groups[b].length - D.groups[a].length)[0];
      return { n: tables.length, top, out, g: g || null, gn: g ? D.groups[g].length : 0 }; }''')
    n = pg.locator('.view[data-view="all"] .tbl').count()
    ok(f'{info["n"]} tables dans la vue', n == info['n'], n)
    pg.screenshot(path=str(shots / '1_initial.png'))

    # survol d'une table
    pg.locator('.view[data-view="all"] .tbl[data-table="%s"]' % info['top']).hover()
    on = pg.locator('.view[data-view="all"] .rel.on').count()
    ok(f'survol {info["top"]} : focus + liens surlignes', pg.locator('main.focus').count() == 1 and on > 0, f'{on} liens')
    pg.screenshot(path=str(shots / '2_hover_equipment.png'))
    pg.mouse.move(5, 990)
    pg.wait_for_timeout(100)

    # recherche + Entree -> panneau
    pg.fill('#q', info['out'])
    pg.press('#q', 'Enter')
    pg.wait_for_timeout(200)
    ok(f'recherche -> panneau {info["out"]}', pg.locator('#panel').is_visible() and pg.locator('#panel h2').inner_text() == info['out'])
    ok('panneau : FK sortantes listees', 'référence (' in pg.locator('#panel').inner_text().lower())
    pg.screenshot(path=str(shots / '3_search_panel.png'))
    pg.keyboard.press('Escape')
    ok('Echap ferme le panneau', not pg.locator('#panel').is_visible())

    # clic sur un lien
    # clic reel sur un point du trace d'un lien, vue ajustee d'abord (la recherche a recentre et zoome : le point sortait de l'ecran)
    pg.click('#fit'); pg.wait_for_timeout(100)
    pt = pg.evaluate('''() => { const r = document.querySelector('.view[data-view="all"] .rel:not(.split) .ln');
      const L = r.getTotalLength(), p = r.getPointAtLength(Math.min(30, L / 2)), m = r.getScreenCTM();
      return [p.x * m.a + m.e, p.y * m.d + m.f]; }''')
    pg.mouse.click(pt[0], pt[1])
    ok('clic lien -> panneau FK', pg.locator('#panel').is_visible() and 'ON DELETE' in pg.locator('#panel').inner_text())
    pg.keyboard.press('Escape')

    # zoom molette
    t0 = pg.eval_on_selector('#stage', 'e => e.style.transform')
    pg.mouse.move(800, 500); pg.mouse.wheel(0, -400); pg.wait_for_timeout(100)
    t1 = pg.eval_on_selector('#stage', 'e => e.style.transform')
    ok('molette = zoom', t0 != t1, f'{t0} -> {t1}')
    pg.click('#fit')

    # modes
    pg.select_option('#mode', 'keys'); pg.wait_for_timeout(150)
    ok('mode cles visible', pg.locator('.view[data-view="keys"]').is_visible())
    pg.screenshot(path=str(shots / '4_keys.png'))
    pg.select_option('#mode', 'names'); pg.wait_for_timeout(150)
    ok('mode noms visible', pg.locator('.view[data-view="names"]').is_visible())
    pg.screenshot(path=str(shots / '5_names.png'))
    pg.select_option('#mode', 'all')
    if pg.locator('#full').count():
        pg.check('#full'); pg.wait_for_timeout(150)
        ok('liens hub complets', pg.locator('.view[data-view="all-full"]').is_visible())
        pg.uncheck('#full')
    if pg.locator('#frames').count():
        pg.check('#frames'); pg.wait_for_timeout(150)
        ok('cadres par domaine', pg.locator('.view[data-view="all-frames"]').is_visible())
        pg.screenshot(path=str(shots / '6_frames.png'))
        pg.uncheck('#frames')

    # legende domaine
    if info['g']:
        pg.click('.lg[data-group="%s"]' % info['g']); pg.wait_for_timeout(100)
        ok(f'clic domaine {info["g"]}', pg.locator('.view[data-view="all"] .tbl.on').count() == info['gn'], pg.locator('.view[data-view="all"] .tbl.on').count())
    pg.keyboard.press('Escape')

    # theme sombre
    pg.click('#theme'); pg.wait_for_timeout(150)
    ok('theme sombre', pg.eval_on_selector('html', 'e => e.dataset.theme') == 'dark')
    pg.screenshot(path=str(shots / '7_dark.png'))

    # redimensionnement : le zoom courant est conserve
    pg.click('#zin'); pg.click('#zin'); pg.wait_for_timeout(100)
    s0 = pg.eval_on_selector('#stage', 'e => e.style.transform.split("scale(")[1]')
    pg.set_viewport_size({'width': 1200, 'height': 800}); pg.wait_for_timeout(200)
    s1 = pg.eval_on_selector('#stage', 'e => e.style.transform.split("scale(")[1]')
    ok('redimensionnement : zoom conserve', s0 == s1, f'{s0} -> {s1}')
    pg.set_viewport_size({'width': 1600, 'height': 1000})
    ix = pg.locator('.view[data-view="all"] .ix').first.text_content()
    ok('libelle Indexes sans triangle de depliage', ix.startswith('Indexes ('), ix)

    # export PNG
    with pg.expect_download() as d:
        pg.click('#png')
    dl = d.value
    path = shots / dl.suggested_filename
    dl.save_as(str(path))
    ok('export PNG telecharge', path.stat().st_size > 50000, f'{dl.suggested_filename} {path.stat().st_size} o')
    b.close()

for n, c, d in results:
    print(('[OK] ' if c else '[ECHEC] ') + n + (f'  ({d})' if d != '' else ''))
print('erreurs console :', errors or 'aucune')
sys.exit(0 if all(c for _, c, _ in results) and not errors else 1)
