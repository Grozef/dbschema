"""--cards (declare_cards) et depistage des migrations Laravel (foreign_connections), sans base."""
import copy, json, os
import pytest
import extract
from conftest import FIX, extract_cli

EDGE = json.load(open(os.path.join(FIX, 'edge.model.json'), encoding='utf-8'))


def test_cards_1_n_declare():
    m = copy.deepcopy(EDGE)
    extract.declare_cards(m, {'child_mandatory.parent_id': {'child': '1..N'}})
    r = next(r for r in m['relations'] if r['from'] == 'child_mandatory')
    assert r['card_child'] == '1..N' and r['declared'] == ['child']


def test_cards_par_nom_de_contrainte():
    m = copy.deepcopy(EDGE)
    name = next(r for r in m['relations'] if r['from'] == 'child_optional')['name']
    extract.declare_cards(m, {name: {'parent': '1'}})
    assert next(r for r in m['relations'] if r['from'] == 'child_optional')['card_parent'] == '1'


@pytest.mark.parametrize('decl,why', [
    ({'nope.parent_id': {'child': '1..N'}}, 'cle inconnue'),
    ({'child_mandatory.parent_id': {'parent': '1..N'}}, 'valeur invalide'),
    ({'composite_child.b': {'child': '1'}}, "colonne qui n'est pas la 1re d'une FK"),
    ({'child_mandatory.parent_id': '1..N'}, 'valeur non-objet'),
    ({'child_mandatory.parent_id': {}}, 'objet vide'),
    ({'child_mandatory.parent_id': {'side': '1'}}, 'cote inconnu'),
])
def test_cards_refus(decl, why):
    with pytest.raises(SystemExit, match='--cards'):
        extract.declare_cards(copy.deepcopy(EDGE), decl)


def test_laravel_connexion_mysql_acceptee(tmp_path):
    mig = tmp_path / 'database' / 'migrations'
    mig.mkdir(parents=True)
    (mig / 'a.php').write_text("<?php Schema::connection('mysql')->create('a', fn() => 1);")
    assert extract.foreign_connections(str(tmp_path)) == []


def test_laravel_motifs_suspects_refuses(tmp_path):
    mig = tmp_path / 'vendor' / 'pkg' / 'database' / 'migrations'
    mig.mkdir(parents=True)
    (mig / 'b.php').write_text("<?php Schema::connection('legacy')->create('b'); class B { protected $connection = $x; }\n"
                               "class C { public function getConnection() { return 'legacy'; } }\nDB::statement('USE prod');\n"
                               "DB::table('prod.users')->truncate(); config(['database.connections.mysql.database' => 'prod']);\n"
                               "Config::set('database.connections.mysql.username', 'root'); DB::disconnect('mysql'); new PDO('x'); User::on('legacy');")
    assert len(extract.foreign_connections(str(tmp_path))) == 10


def test_laravel_refuse_sans_trust_repo(tmp_path):
    code, out = extract_cli('--laravel', str(tmp_path), '--out', os.devnull)
    assert code != 0 and '--trust-repo' in out
