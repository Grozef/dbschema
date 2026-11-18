"""Fixtures communes. Le marqueur vient du dossier (unit/, functional/, e2e/, perf/, security/).
Base ou navigateur absents : test saute en local, ECHEC si DBSCHEMA_REQUIRE_DB=1 / DBSCHEMA_REQUIRE_BROWSER=1 (CI)."""
import json, os, shutil, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, 'lib')
FIX = os.path.join(HERE, 'fixtures')
sys.path.insert(0, LIB)
import extract  # noqa: E402

DIRS = {'unit', 'functional', 'e2e', 'perf', 'security'}


def pytest_collection_modifyitems(items):
    for it in items:
        parts = set(os.path.relpath(str(it.path), HERE).replace('\\', '/').split('/'))
        for d in DIRS & parts:
            it.add_marker(getattr(pytest.mark, d))


def run(cmd, env=None, cwd=None, timeout=900):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=cwd, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def extract_cli(*args, env=None):
    # DBSCHEMA_COV=1 (CI) : couverture mesuree aussi dans ce sous-processus, toujours en -I comme en production (dbschema.sh) ;
    # la configuration passe par --rcfile, pas par l'environnement (que -I ignorerait)
    if os.environ.get('DBSCHEMA_COV') == '1':
        cov = [sys.executable, '-I', '-m', 'coverage', 'run', '--parallel-mode', '--rcfile=' + os.path.join(ROOT, '.coveragerc')]
        return run(cov + [os.path.join(LIB, 'extract.py'), *args], env=env, cwd=ROOT)
    return run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), *args], env=env)


def need(kind, ok, why):
    if ok:
        return
    if os.environ.get('DBSCHEMA_REQUIRE_' + kind) == '1':
        pytest.fail('%s requis (DBSCHEMA_REQUIRE_%s=1) : %s' % (kind, kind, why))
    pytest.skip(why)


_db = {}


def db_ready():
    if 'ok' not in _db:
        try:
            extract.run('SELECT 1')
            _db['ok'], _db['why'] = True, ''
        except (SystemExit, Exception) as e:  # binaire absent (SystemExit) ou serveur injoignable
            _db['ok'], _db['why'] = False, 'serveur MySQL/MariaDB injoignable : %s' % str(e)[:150]
    return _db['ok'], _db['why']


@pytest.fixture(scope='session')
def db():
    need('DB', *db_ready())
    return extract


def find_chrome():
    """Meme recherche que lib/build.mjs."""
    env = os.environ.get('DBSCHEMA_CHROME')
    if env == 'none':
        return None
    cands = [env] + [d + s for d in ('C:/Program Files', 'C:/Program Files (x86)', os.environ.get('LOCALAPPDATA') or '//')
                     for s in ('/Google/Chrome/Application/chrome.exe', '/Microsoft/Edge/Application/msedge.exe')]
    cands += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
              '/Applications/Chromium.app/Contents/MacOS/Chromium']
    cands += [shutil.which(n) for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge')]
    return next((c for c in cands if c and os.path.isfile(c)), None)


@pytest.fixture(scope='session')
def chrome():
    c = find_chrome()
    need('BROWSER', c, 'ni Chrome, Edge ni Chromium')
    return c


@pytest.fixture(scope='session')
def bash():
    b = shutil.which('bash')
    need('DB', b, 'bash introuvable')  # les tests de bout en bout tournent avec la base : meme exigence
    return b


@pytest.fixture(scope='session')
def edge(db, tmp_path_factory):
    """edge-cases.sql extrait puis construit une fois : modele, sortie du build, dossier."""
    d = tmp_path_factory.mktemp('edge')
    m = d / 'model.json'
    code, out = extract_cli('--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', str(m), '--sql-out', str(d / 'edge.sql'))
    assert code == 0, out[-800:]
    bcode, bout = run(['node', os.path.join(LIB, 'build.mjs'), str(m), str(d / 'out'), 'EDGE'])
    return {'dir': d, 'model': json.load(open(m, encoding='utf-8')), 'extract': out, 'code': bcode, 'build': bout,
            'lay': lambda v: json.load(open(d / 'out' / '_build' / ('layout_%s.json' % v), encoding='utf-8'))}


@pytest.fixture(scope='session')
def demo(db, bash, tmp_path_factory):
    """dbschema.sh all sur la demo (groupes, cadres, .mwb synthetique) une fois pour toute la session."""
    from mwb_fixture import write_mwb
    d = tmp_path_factory.mktemp('demo')
    model = json.load(open(os.path.join(FIX, 'demo.model.json'), encoding='utf-8'))
    mwb = d / 'source.mwb'
    write_mwb(str(mwb), list(model['tables']), [(r['from'], r['to']) for r in model['relations']])
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--sql', os.path.join(FIX, 'demo.sql'),
                     '--groups', os.path.join(FIX, 'demo.groups.json'), '--frames', '--mwb', str(mwb),
                     '--out', str(d / 'out'), '--name', 'DEMO'])
    return {'dir': d, 'out': d / 'out', 'code': code, 'log': out, 'mwb': mwb}


@pytest.fixture(scope='session')
def browser(chrome):
    """Chromium pilote par Playwright, sur le navigateur installe (le meme que build.mjs)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        need('BROWSER', False, 'Playwright pour Python absent (pip install -r requirements-dev.txt)')
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chrome)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    """Page 1600x1000 ; errors = erreurs console + exceptions ; dialogs = alert/confirm ouverts ; requests = URL chargees."""
    ctx = browser.new_context(viewport={'width': 1600, 'height': 1000}, accept_downloads=True)
    pg = ctx.new_page()
    pg.errors, pg.dialogs, pg.requests = [], [], []
    pg.on('console', lambda m: pg.errors.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: pg.errors.append(str(e)))
    pg.on('dialog', lambda d: (pg.dialogs.append(d.message), d.dismiss()))
    pg.on('request', lambda r: pg.requests.append(r.url))
    yield pg
    ctx.close()
