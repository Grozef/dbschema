"""Extraction contre un vrai serveur (MySQL ou MariaDB) : cardinalites, --cards, --db, demo, aller-retour, scripts, valeurs."""
import json, os, re
import pytest
from conftest import FIX, extract_cli

EXPECT = {
    'child_mandatory': ('1', '0..N'), 'child_optional': ('0..1', '0..N'),
    'one_to_one_mandatory': ('1', '0..1'), 'one_to_one_optional': ('0..1', '0..1'),
    'self_ref': ('0..1', '0..N'), 'composite_child': ('1', '0..N'), 'circular_y': ('1', '0..N'), 'circular_x': ('0..1', '0..N'),
    'hub_ref_9': ('0..1', '0..N'), 'profile': ('1', '0..1'), 'profile_photo': ('1', '0..N'), 'address': ('0..1', '0..N'),
}


@pytest.mark.parametrize('table', EXPECT)
def test_cardinalite(edge, table):
    r = {r['from']: r for r in edge['model']['relations']}[table]
    assert (r['card_parent'], r['card_child']) == EXPECT[table]


def test_fk_composite_et_table_isolee(edge):
    rel = {r['from']: r for r in edge['model']['relations']}
    assert rel['composite_child']['columns'] == ['a', 'b']
    assert 'isolated' in edge['model']['tables']


def test_modele_identique_a_la_reference(edge):
    """Meme modele quel que soit le serveur (MySQL 5.7/8, MariaDB) : tables, colonnes, types, valeurs par defaut, relations."""
    ref = json.load(open(os.path.join(FIX, 'edge.model.json'), encoding='utf-8'))
    got = edge['model']
    assert sorted(got['tables']) == sorted(ref['tables'])
    for t in ref['tables']:
        strip = lambda cols: [(c['name'], c['nullable'], c['default'], c['pk'], c['fk'], c['unique']) for c in cols]
        assert strip(got['tables'][t]['columns']) == strip(ref['tables'][t]['columns']), t
    key = lambda r: (r['from'], r['to'], r['columns'], r['ref_columns'], r['card_parent'], r['card_child'])
    assert sorted(map(key, got['relations'])) == sorted(map(key, ref['relations']))


def test_types_et_enum_demo(db, tmp_path):
    code, out = extract_cli('--sql', os.path.join(FIX, 'demo.sql'), '--out', str(tmp_path / 'm.json'))
    assert code == 0, out[-400:]
    got = json.load(open(tmp_path / 'm.json', encoding='utf-8'))
    ref = json.load(open(os.path.join(FIX, 'demo.model.json'), encoding='utf-8'))
    norm = lambda m: {(t, c['name']): (norm_type(c['type']), c['default']) for t, T in m['tables'].items() for c in T['columns']}
    assert norm(got) == norm(ref)


def norm_type(t):
    """Differences documentees entre serveurs, les seules admises : largeur d'affichage des entiers (MySQL 5.7, MariaDB ;
    tinyint(1) garde partout) et JSON stocke en longtext (MariaDB)."""
    t = re.sub(r'\b(tinyint|smallint|mediumint|int|bigint)\((\d+)\)',
               lambda m: m.group(0) if m.group(1) == 'tinyint' and m.group(2) == '1' else m.group(1), t)
    return 'json' if t == 'longtext' else t


def test_cards_1_n(db, tmp_path):
    p = tmp_path / 'c.json'
    p.write_text(json.dumps({'child_mandatory.parent_id': {'child': '1..N'}}))
    code, out = extract_cli('--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', str(tmp_path / 'm.json'), '--cards', str(p))
    r = {x['from']: x for x in json.load(open(tmp_path / 'm.json', encoding='utf-8'))['relations']}['child_mandatory']
    assert code == 0 and r['card_child'] == '1..N' and r['declared'] == ['child']


def test_cards_cle_inconnue_refusee(db, tmp_path):
    p = tmp_path / 'c.json'
    p.write_text(json.dumps({'nope.parent_id': {'child': '1..N'}}))
    code, out = extract_cli('--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', str(tmp_path / 'm.json'), '--cards', str(p))
    assert code != 0 and '--cards' in out


def test_db_inexistante_refusee(db, tmp_path):
    code, out = extract_cli('--db', 'zz_dbschema_inexistante_xyz', '--out', str(tmp_path / 'x.json'))
    assert code != 0 and 'inexistante' in out


def test_db_lecture_seule(db, tmp_path):
    """--db sur une base existante : modele lu, SQL exporte, aucune ecriture (releve des tables identique)."""
    name = db.PREFIX + 'readonly'
    try:
        db.run('DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s`; CREATE TABLE `%s`.p (id INT PRIMARY KEY); '
               'CREATE TABLE `%s`.c (id INT PRIMARY KEY, p_id INT NOT NULL, FOREIGN KEY (p_id) REFERENCES `%s`.p(id))' % ((name,) * 5))
        before = db.run("SELECT GROUP_CONCAT(TABLE_NAME, CREATE_TIME) FROM information_schema.TABLES WHERE TABLE_SCHEMA='%s'" % name)
        code, out = extract_cli('--db', name, '--out', str(tmp_path / 'm.json'), '--sql-out', str(tmp_path / 'd.sql'))
        assert code == 0 and 'tables=2' in out and 'relations=1' in out, out[-300:]
        assert 'CREATE TABLE' in (tmp_path / 'd.sql').read_text(encoding='utf-8')
        assert db.run("SELECT GROUP_CONCAT(TABLE_NAME, CREATE_TIME) FROM information_schema.TABLES WHERE TABLE_SCHEMA='%s'" % name) == before
    finally:
        db.run('DROP DATABASE IF EXISTS `%s`' % name)


def test_demo_19_tables_31_fk(db, tmp_path):
    code, out = extract_cli('--sql', os.path.join(FIX, 'demo.sql'), '--groups', os.path.join(FIX, 'demo.groups.json'),
                            '--out', str(tmp_path / 'm.json'))
    assert code == 0 and 'tables=19' in out and 'relations=31' in out and 'groupes=6' in out, out[-300:]


def test_groupes_table_inconnue_refusee(db, tmp_path):
    p = tmp_path / 'g.json'
    p.write_text(json.dumps({'X': ['nope']}))
    code, out = extract_cli('--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', str(tmp_path / 'm.json'), '--groups', str(p))
    assert code != 0 and 'tables inconnues' in out


def test_aller_retour_sql(db, tmp_path):
    code, out = extract_cli('--sql', os.path.join(FIX, 'demo.sql'), '--out', str(tmp_path / 'a.json'), '--sql-out', str(tmp_path / 'r.sql'))
    assert code == 0, out[-300:]
    code, out = extract_cli('--sql', str(tmp_path / 'r.sql'), '--out', str(tmp_path / 'b.json'))
    assert code == 0, out[-300:]
    a, b = (json.load(open(tmp_path / f, encoding='utf-8')) for f in ('a.json', 'b.json'))
    assert a['tables'] == b['tables'] and a['relations'] == b['relations']


def test_script_legitime_accepte(db, tmp_path):
    p = tmp_path / 's.sql'
    p.write_text("CREATE TABLE t (id INT PRIMARY KEY, ratio DECIMAL(5,2) DEFAULT 1.5, note VARCHAR(20) DEFAULT 'a.b');", encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    assert code == 0 and 'tables=1' in out, out[-300:]


@pytest.mark.parametrize('sql', [
    'CREATE DATABASE IF NOT EXISTS zz_probe_victim;\nUSE zz_probe_victim;\nCREATE TABLE t (id INT PRIMARY KEY);',
    'CREATE TABLE t (id INT PRIMARY KEY, u INT, FOREIGN KEY (u) REFERENCES autre_base.users(id));',
], ids=['use', 'qualifie'])
def test_script_dangereux_refuse_avant_execution(db, tmp_path, sql):
    p = tmp_path / 's.sql'
    p.write_text(sql, encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    assert code != 0 and 'script refuse' in out
    assert not db.run("SHOW DATABASES LIKE 'zz\\_probe\\_victim'").strip()
