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


def test_laravel_source_du_framework_ignoree(tmp_path):
    # Laravel neuf sous Windows (2026-11-27) : glob insensible a la casse prenait le code du Migrator
    # (src/Illuminate/Database/Migrations/) pour des migrations et refusait --laravel
    src = tmp_path / 'vendor' / 'laravel' / 'framework' / 'src' / 'Illuminate' / 'Database' / 'Migrations'
    src.mkdir(parents=True)
    (src / 'Migrator.php').write_text("<?php class Migrator { public function getConnection() {} }")
    assert extract.foreign_connections(str(tmp_path)) == []


def test_laravel_dossier_migrations_de_paquet_toute_casse(tmp_path):
    # loadMigrationsFrom(__DIR__.'/Migrations') : Laravel execute ces fichiers, quel que soit l'OS
    for d, f in [('database/Migrations', 'c.php'), ('src/Database/Migrations', 'd.PHP')]:
        p = tmp_path / 'vendor' / 'pkg' / d
        p.mkdir(parents=True)
        (p / f).write_text("<?php Schema::connection('legacy')->create('t');")
    bad = extract.foreign_connections(str(tmp_path))
    assert len(bad) == 2 and any('c.php' in b for b in bad) and any('d.PHP' in b for b in bad)


@pytest.mark.parametrize('d', ['laravel/framework/evil/migrations', 'laravel/telescope/database/migrations'])
def test_laravel_exclusion_bornee_au_code_illuminate(tmp_path, d):
    # seul vendor/laravel/framework/src/Illuminate est exclu : un autre dossier de laravel/* reste scanne
    p = tmp_path / 'vendor' / d
    p.mkdir(parents=True)
    (p / 'z.php').write_text("<?php Schema::connection('legacy')->create('t');")
    assert len(extract.foreign_connections(str(tmp_path))) == 1


def test_laravel_paquet_en_lien_scanne(tmp_path):
    # paquet Composer de type path : vendor/pkg est un lien vers le code du paquet
    cible = tmp_path / 'pkgsrc' / 'database' / 'migrations'
    cible.mkdir(parents=True)
    (cible / 'e.php').write_text("<?php Schema::connection('legacy')->create('t');")
    repo = tmp_path / 'repo'
    (repo / 'vendor').mkdir(parents=True)
    try:
        os.symlink(tmp_path / 'pkgsrc', repo / 'vendor' / 'pkg', target_is_directory=True)
    except OSError:
        pytest.skip('liens symboliques non autorises sur ce poste')
    assert len(extract.foreign_connections(str(repo))) == 1


def test_laravel_connexion_affectee_dans_le_constructeur_refusee(tmp_path):
    # $this->connection = ... (constructeur ou up()) : le Migrator le lit par getConnection()
    mig = tmp_path / 'database' / 'migrations'
    mig.mkdir(parents=True)
    (mig / 'c.php').write_text("<?php return new class extends Migration { function __construct() { $this->connection = 'legacy'; } };")
    assert len(extract.foreign_connections(str(tmp_path))) == 1


def test_laravel_refuse_sans_trust_repo(tmp_path):
    code, out = extract_cli('--laravel', str(tmp_path), '--out', os.devnull)
    assert code != 0 and '--trust-repo' in out
