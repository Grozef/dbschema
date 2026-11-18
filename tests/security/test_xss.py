"""XSS : noms et commentaires hostiles (fixtures/xss.sql) affiches tels quels dans le HTML livre, jamais executes."""
import os
import pytest
from conftest import FIX, ROOT, run

EVIL = ['<img src=x onerror=alert(1)>', '"><svg onload=alert(2)>', '<script>alert(7)</script>']


@pytest.fixture(scope='module')
def xss_html(db, bash, tmp_path_factory):
    d = tmp_path_factory.mktemp('xss')
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--sql', os.path.join(FIX, 'xss.sql'), '--out', str(d), '--name', 'XSS'])
    assert code == 0, out[-1500:]
    return d / 'XSS.html'


def test_aucune_execution_a_l_ouverture(page, xss_html):
    page.goto(xss_html.as_uri())
    page.wait_for_timeout(500)
    assert page.dialogs == []
    assert page.evaluate("document.querySelectorAll('script').length") == 1
    assert page.evaluate("document.querySelectorAll('img[onerror], svg[onload], [onerror], [onload]').length") == 0
    assert page.errors == []


def test_noms_affiches_litteralement(page, xss_html):
    page.goto(xss_html.as_uri())
    tables = page.evaluate("[...document.querySelectorAll('.view[data-view=\"all\"] .tbl')].map(t => t.dataset.table)")
    assert set(EVIL[:1] + EVIL[2:]) <= set(tables) and '__proto__' in tables
    text = page.evaluate("document.querySelector('.view[data-view=\"all\"]').textContent")
    assert EVIL[1] in text  # nom de colonne


def test_panneau_et_recherche_sans_execution(page, xss_html):
    page.goto(xss_html.as_uri())
    for t in (EVIL[0], EVIL[2], '__proto__'):
        page.fill('#q', t)
        page.press('#q', 'Enter')
        page.wait_for_timeout(150)
        assert page.locator('#panel').is_visible() and page.locator('#panel h2').inner_text() == t
        page.keyboard.press('Escape')
    page.fill('#q', EVIL[0])
    page.press('#q', 'Enter')
    assert '<script>alert(4)</script>' in page.locator('#panel').inner_text()  # commentaire de colonne, en texte
    assert page.dialogs == [] and page.errors == []


def test_aucune_requete_externe(page, xss_html):
    page.goto(xss_html.as_uri())
    page.wait_for_timeout(300)
    assert all(u.startswith(('file:', 'data:', 'blob:')) for u in page.requests), page.requests
