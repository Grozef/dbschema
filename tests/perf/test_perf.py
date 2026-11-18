"""Performance : schemas generes de 25, 100 et 250 tables. Echec si un budget (tests/perf/budgets.json) est depasse.
Mesures ecrites dans $DBSCHEMA_PERF_OUT (artefact CI) ou dans le dossier temporaire du test."""
import json, os, sys, time
import pytest
from conftest import LIB, extract_cli, run
from gen_schema import generate

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGETS = json.load(open(os.path.join(HERE, 'budgets.json'), encoding='utf-8'))
RESULTS = {}


@pytest.fixture(scope='module', autouse=True)
def report(tmp_path_factory):
    yield
    out = os.environ.get('DBSCHEMA_PERF_OUT') or str(tmp_path_factory.getbasetemp() / 'perf.json')
    json.dump(RESULTS, open(out, 'w', encoding='utf-8'), indent=1)
    print('\nmesures de performance : %s\n%s' % (out, json.dumps(RESULTS, indent=1)))


@pytest.mark.parametrize('n', [25, 100, 250])
def test_budget(db, chrome, tmp_path, n):
    sql = tmp_path / 's.sql'
    sql.write_text(generate(n), encoding='utf-8')
    t0 = time.perf_counter()
    code, out = extract_cli('--sql', str(sql), '--out', str(tmp_path / 'm.json'))
    t1 = time.perf_counter()
    assert code == 0, out[-500:]
    bcode, bout = run(['node', os.path.join(LIB, 'build.mjs'), str(tmp_path / 'm.json'), str(tmp_path / 'o'), 'P'])
    t2 = time.perf_counter()
    assert bcode == 0, bout[-1200:]
    html = (tmp_path / 'o' / 'P.html').stat().st_size
    cross = {l.split(']')[0][1:]: int(l.split('croisements=')[1].split()[0]) for l in bout.splitlines() if 'croisements=' in l}
    m = RESULTS[str(n)] = {'extract_s': round(t1 - t0, 2), 'build_s': round(t2 - t1, 2), 'html_kb': round(html / 1024), 'crossings': cross,
                           'platform': sys.platform}
    b = BUDGETS[str(n)]
    over = {k: (m[k], b[k]) for k in ('extract_s', 'build_s', 'html_kb') if m[k] > b[k]}
    assert not over, 'budget depasse (mesure, budget) : %s' % over
