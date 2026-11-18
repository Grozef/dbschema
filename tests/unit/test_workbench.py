"""lib/workbench.py : script GRT (noms pieges = chaines), mise a l'echelle, patch d'un .mwb synthetique. Sans Workbench."""
import ast, hashlib, json, re, zipfile
import pytest
import workbench
from mwb_fixture import write_mwb

LAY = {'tables': {'a': {'x': 0, 'y': 0, 'w': 150, 'h': 100}, 'b': {'x': 300, 'y': 200, 'w': 150, 'h': 100},
                  'c': {'x': 0, 'y': 400, 'w': 150, 'h': 100}}, 'hubs': ['a']}


@pytest.fixture
def lay(tmp_path):
    p = tmp_path / 'lay.json'
    p.write_text(json.dumps(LAY), encoding='utf-8')
    return p


def test_scaled_conserve_les_ecarts():
    box = workbench.boxes(LAY)
    pos, rx, ry = workbench.scaled(box, {'a': (180, 118), 'b': (150, 100), 'c': (150, 100)})
    assert rx == pytest.approx(1.2) and ry == pytest.approx(1.18)
    assert pos['b'] == (360, 236) and pos['a'] == (0, 0)


def test_scaled_jamais_reduit():
    _, rx, ry = workbench.scaled(workbench.boxes(LAY), {'a': (100, 50)})
    assert (rx, ry) == (1, 1)


def test_script_nom_piege_reste_une_chaine(tmp_path):
    p = tmp_path / 'lay.json'
    trap = 'h\nprint("PWN")\n#'
    p.write_text(json.dumps({'tables': {trap: {'x': 0, 'y': 0, 'w': 100, 'h': 60}}, 'hubs': [trap]}), encoding='utf-8')
    out = tmp_path / 'wb.py'
    workbench.cmd_script(str(p), str(out))
    src = out.read_text(encoding='utf-8')
    tree = ast.parse(src)
    calls = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call) and 'PWN' in ast.unparse(n.func)]
    assert not calls and not any(l.startswith('print("PWN")') for l in src.splitlines())


def test_script_contient_les_tables(lay, tmp_path):
    out = tmp_path / 'wb.py'
    workbench.cmd_script(str(lay), str(out))
    src = out.read_text(encoding='utf-8')
    ast.parse(src)
    box = json.loads(re.search(r'^BOX = (.*?)  #', src, re.M).group(1))
    assert set(box) == {'a', 'b', 'c'} and 'HUBS = ["a"]' in src
    assert 'newDocument' not in src and 'save' not in src.lower().replace('file > save', '')


def test_patch_positions_split_source_intacte(lay, tmp_path):
    src = tmp_path / 'src.mwb'
    write_mwb(str(src), ['a', 'b', 'c'], [('b', 'a'), ('c', 'b')])
    h0 = hashlib.sha256(src.read_bytes()).hexdigest()
    dst = tmp_path / 'out.mwb'
    workbench.cmd_patch(str(lay), str(src), str(dst))
    assert hashlib.sha256(src.read_bytes()).hexdigest() == h0
    x = zipfile.ZipFile(dst).read('document.mwb.xml').decode('utf-8')
    figs = re.findall(r'TableFigure" id="\{F(\d)\}">.*?key="left">([-\d.e]+)<.*?key="top">([-\d.e]+)<.*?key="name">(\w)<', x, re.S)
    pos = {n: (float(l), float(t)) for _, l, t, n in figs}
    # tailles reelles 180 x 118 (fixture) contre 150 x 100 : echelle 1.2 / 1.18
    assert pos == {'a': (0, 0), 'b': (360, 236), 'c': (0, 472)}
    splits = re.findall(r'key="drawSplit">(\d)<', x)
    assert splits == ['1', '0']  # b -> a (hub) en split, c -> b non
    assert sorted(zipfile.ZipFile(dst).namelist()) == sorted(zipfile.ZipFile(src).namelist())


def test_patch_refuse_sortie_egale_source(lay, tmp_path):
    src = tmp_path / 'src.mwb'
    write_mwb(str(src), ['a', 'b', 'c'], [])
    with pytest.raises(SystemExit, match='la sortie est la source'):
        workbench.cmd_patch(str(lay), str(src), str(src))


def test_patch_refuse_doctype_entity(lay, tmp_path):
    """Entites XML (expansion exponentielle, lecture de fichier) : jamais dans un .mwb, refusees avant tout analyseur."""
    from mwb_fixture import xml
    src = tmp_path / 'src.mwb'
    doc = xml(['a', 'b', 'c'], []).replace('<data ', '<!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>\n<data ', 1)
    with zipfile.ZipFile(src, 'w') as z:
        z.writestr('document.mwb.xml', doc)
    with pytest.raises(SystemExit, match='DOCTYPE'):
        workbench.cmd_patch(str(lay), str(src), str(tmp_path / 'out.mwb'))


def test_patch_refuse_plusieurs_calques(lay, tmp_path):
    src = tmp_path / 'src.mwb'
    write_mwb(str(src), ['a', 'b', 'c'], [], layers=2)
    with pytest.raises(SystemExit, match='plusieurs calques'):
        workbench.cmd_patch(str(lay), str(src), str(tmp_path / 'out.mwb'))


def test_patch_refuse_modele_sans_table_du_schema(lay, tmp_path):
    """Mauvais fichier --mwb : refus lisible, plus de ValueError (revue du 2026-11-18)."""
    src = tmp_path / 'src.mwb'
    write_mwb(str(src), ['autre1', 'autre2'], [])
    with pytest.raises(SystemExit, match='aucune table du schema'):
        workbench.cmd_patch(str(lay), str(src), str(tmp_path / 'out.mwb'))
    assert not (tmp_path / 'out.mwb').exists()


def test_patch_refuse_bombe_de_decompression(lay, tmp_path, monkeypatch):
    src = tmp_path / 'src.mwb'
    write_mwb(str(src), ['a', 'b', 'c'], [])
    monkeypatch.setattr(workbench, 'MAX_UNZIPPED', 1000)  # document.mwb.xml du modele synthetique : plus de 1 000 octets
    with pytest.raises(SystemExit, match='decompresse'):
        workbench.cmd_patch(str(lay), str(src), str(tmp_path / 'out.mwb'))


def test_patch_refuse_layout_qui_se_chevauche(tmp_path):
    """Dernier filet : si le layout se chevauche deja, les positions mises a l'echelle se chevauchent aussi -> refus."""
    p = tmp_path / 'lay.json'
    p.write_text(json.dumps({'tables': {'a': {'x': 0, 'y': 0, 'w': 150, 'h': 100}, 'b': {'x': 50, 'y': 50, 'w': 150, 'h': 100}},
                             'hubs': []}), encoding='utf-8')
    src = tmp_path / 'src.mwb'
    write_mwb(str(src), ['a', 'b'], [])
    with pytest.raises(SystemExit, match='chevauchements'):
        workbench.cmd_patch(str(p), str(src), str(tmp_path / 'out.mwb'))
