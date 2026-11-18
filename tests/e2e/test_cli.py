"""dbschema.sh all de bout en bout sur la demo : livrables, PNG valide, script Workbench, .mwb, mode sans navigateur."""
import ast, hashlib, json, os, re, struct, zipfile
from conftest import FIX, ROOT, run

DEMO = json.load(open(os.path.join(FIX, 'demo.model.json'), encoding='utf-8'))


def test_commande_reussit(demo):
    assert demo['code'] == 0, demo['log'][-1500:]
    views = [l.split(']')[0][1:] for l in demo['log'].splitlines() if l.startswith('[') and not l.startswith('[texte]') and l.endswith('-> OK')]
    assert views == ['all', 'keys', 'names', 'all-full', 'all-frames']


def test_livrables_presents(demo):
    for f in ('DEMO.html', 'DEMO.png', 'DEMO.sql', 'DEMO_workbench_layout.py', 'DEMO_layout.mwb'):
        p = demo['out'] / f
        assert p.exists() and p.stat().st_size > 1000, f


def test_png_valide(demo, chrome):
    data = (demo['out'] / 'DEMO.png').read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    w, h = struct.unpack('>II', data[16:24])
    lay = json.load(open(demo['out'] / '_build' / 'layout_all.json', encoding='utf-8'))
    assert (w, h) == (2 * int(-(-lay['width'] // 1)), 2 * int(-(-lay['height'] // 1)))  # double resolution, sans rognage
    assert len(data) > 50000


def test_sql_exporte_tables_seules(demo):
    sql = (demo['out'] / 'DEMO.sql').read_text(encoding='utf-8')
    assert sql.count('CREATE TABLE') == 19
    assert not re.search(r'AUTO_INCREMENT=\d|DEFINER|CREATE (ALGORITHM|VIEW|TRIGGER)', sql)


def test_script_workbench(demo):
    src = (demo['out'] / 'DEMO_workbench_layout.py').read_text(encoding='utf-8')
    ast.parse(src)
    box = json.loads(re.search(r'^BOX = (.*?)  #', src, re.M).group(1))
    assert set(box) == set(DEMO['tables'])
    for bad in ('newDocument', 'quit', 'os.system', 'subprocess', 'open('):
        assert bad not in src, bad


def test_mwb_corrige(demo):
    src = demo['mwb']
    out = demo['out'] / 'DEMO_layout.mwb'
    assert 'source inchangee' in demo['log']
    x0 = zipfile.ZipFile(src).read('document.mwb.xml').decode('utf-8')
    x1 = zipfile.ZipFile(out).read('document.mwb.xml').decode('utf-8')
    left = lambda x: re.findall(r'key="left">([-\d.e]+)<', x)
    assert len(left(x1)) == 19 and set(left(x0)) == {'0'} and len(set(left(x1))) > 1
    assert '1' in re.findall(r'key="drawSplit">(\d)<', x1)  # liens vers le hub "users" en split
    # seules les positions, drawSplit et tailles changent
    strip = lambda x: re.sub(r'key="(left|top|drawSplit|width|height)">[-\d.e]+<', '', x)
    assert strip(x0) == strip(x1)


def test_sans_navigateur(db, bash, tmp_path):
    env = {**os.environ, 'DBSCHEMA_CHROME': 'none'}
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--sql', os.path.join(FIX, 'edge-cases.sql'),
                     '--out', str(tmp_path), '--name', 'NB'], env=env)
    assert code == 0, out[-800:]
    assert 'PNG non produit' in out and 'debordement non mesure' in out
    assert (tmp_path / 'NB.html').exists() and (tmp_path / 'NB.sql').exists() and not (tmp_path / 'NB.png').exists()
