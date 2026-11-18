"""Interactions du HTML livre (Playwright) : reprise de ui_test.py. Cibles tirees des donnees de la page, pas d'un schema."""
import pytest

INFO = '''() => { const deg = {}; for (const r of D.relations) for (const t of [r.from, r.to]) deg[t] = (deg[t] || 0) + 1;
  const tables = Object.keys(D.tables), top = tables.sort((a, b) => (deg[b] || 0) - (deg[a] || 0))[0];
  const out = tables.filter((t) => D.relations.some((r) => r.from === t)).sort((a, b) => b.length - a.length)[0] || top;
  const g = Object.keys(D.groups).sort((a, b) => D.groups[b].length - D.groups[a].length)[0];
  return { n: tables.length, top, out, g: g || null, gn: g ? D.groups[g].length : 0 }; }'''


@pytest.fixture
def ui(page, demo):
    page.goto((demo['out'] / 'DEMO.html').as_uri())
    page.wait_for_timeout(300)
    page.info = page.evaluate(INFO)
    yield page
    assert page.errors == [], page.errors  # aucune erreur console dans aucun test


def test_vue_initiale(ui):
    assert ui.locator('.view[data-view="all"]').is_visible()
    assert ui.locator('.view[data-view="all"] .tbl').count() == ui.info['n'] == 19


def test_survol_surligne_les_liens(ui):
    ui.locator('.view[data-view="all"] .tbl[data-table="%s"]' % ui.info['top']).hover()
    assert ui.locator('main.focus').count() == 1 and ui.locator('.view[data-view="all"] .rel.on').count() > 0
    ui.mouse.move(5, 990)


def test_recherche_panneau_echap(ui):
    ui.fill('#q', ui.info['out'])
    ui.press('#q', 'Enter')
    ui.wait_for_timeout(200)
    assert ui.locator('#panel').is_visible() and ui.locator('#panel h2').inner_text() == ui.info['out']
    assert 'référence (' in ui.locator('#panel').inner_text().lower()
    ui.keyboard.press('Escape')
    assert not ui.locator('#panel').is_visible()


def test_recherche_par_colonne(ui):
    col = ui.evaluate("Object.values(D.tables).find(t => t.columns.length > 3).columns[2].name")
    ui.fill('#q', col)
    ui.wait_for_timeout(200)
    assert ui.locator('.view[data-view="all"] .tbl.match').count() >= 1


def test_clic_lien_panneau_fk(ui):
    ui.click('#fit')
    ui.wait_for_timeout(100)
    pt = ui.evaluate('''() => { const r = document.querySelector('.view[data-view="all"] .rel:not(.split) .ln');
      const L = r.getTotalLength(), p = r.getPointAtLength(Math.min(30, L / 2)), m = r.getScreenCTM();
      return [p.x * m.a + m.e, p.y * m.d + m.f]; }''')
    ui.mouse.click(pt[0], pt[1])
    assert ui.locator('#panel').is_visible() and 'ON DELETE' in ui.locator('#panel').inner_text()


def test_molette_zoom(ui):
    t0 = ui.eval_on_selector('#stage', 'e => e.style.transform')
    ui.mouse.move(800, 500)
    ui.mouse.wheel(0, -400)
    ui.wait_for_timeout(100)
    assert ui.eval_on_selector('#stage', 'e => e.style.transform') != t0


def test_glisser_deplace(ui):
    t0 = ui.eval_on_selector('#stage', 'e => e.style.transform')
    ui.mouse.move(700, 600)
    ui.mouse.down()
    ui.mouse.move(500, 400, steps=5)
    ui.mouse.up()
    assert ui.eval_on_selector('#stage', 'e => e.style.transform') != t0


@pytest.mark.parametrize('mode', ['keys', 'names', 'all'])
def test_modes(ui, mode):
    ui.select_option('#mode', mode)
    ui.wait_for_timeout(150)
    assert ui.locator('.view[data-view="%s"]' % mode).is_visible()


def test_liens_hub_complets_et_cadres(ui):
    ui.check('#full')
    ui.wait_for_timeout(150)
    assert ui.locator('.view[data-view="all-full"]').is_visible()
    ui.uncheck('#full')
    ui.check('#frames')
    ui.wait_for_timeout(150)
    assert ui.locator('.view[data-view="all-frames"]').is_visible()


def test_legende_domaine(ui):
    ui.click('.lg[data-group="%s"]' % ui.info['g'])
    ui.wait_for_timeout(100)
    assert ui.locator('.view[data-view="all"] .tbl.on').count() == ui.info['gn']


def test_theme_sombre(ui):
    ui.click('#theme')
    ui.wait_for_timeout(150)
    assert ui.eval_on_selector('html', 'e => e.dataset.theme') == 'dark'


def test_redimensionnement_conserve_le_zoom(ui):
    ui.click('#zin')
    ui.click('#zin')
    ui.wait_for_timeout(100)
    s0 = ui.eval_on_selector('#stage', 'e => e.style.transform.split("scale(")[1]')
    ui.set_viewport_size({'width': 1200, 'height': 800})
    ui.wait_for_timeout(200)
    assert ui.eval_on_selector('#stage', 'e => e.style.transform.split("scale(")[1]') == s0


def test_libelle_indexes(ui):
    assert ui.locator('.view[data-view="all"] .ix').first.text_content().startswith('Indexes (')


def test_export_png(ui, tmp_path):
    with ui.expect_download() as d:
        ui.click('#png')
    p = tmp_path / d.value.suggested_filename
    d.value.save_as(str(p))
    assert p.read_bytes()[:4] == b'\x89PNG' and p.stat().st_size > 50000
