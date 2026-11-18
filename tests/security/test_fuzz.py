"""Fuzz du filtre check_script (graine fixe). La verite vient de la construction du script, pas du filtre :
fragment dangereux en position executable -> refuse ; le meme fragment dans une chaine ou un commentaire -> accepte."""
import os, random
import pytest
import extract
from conftest import extract_cli

N = 2000
DANGER = ['USE prod', 'DROP TABLE prod.users', 'CREATE DATABASE x', 'SET GLOBAL general_log=1', 'DROP DATABASE prod',
          'INSERT INTO prod.users VALUES (1)', 'GRANT ALL ON *.* TO x', 'CREATE VIEW v AS SELECT 1', "SET PASSWORD = 'x'",
          'ALTER TABLE `prod`.`users` ADD x INT', 'DELETE FROM prod.users', "LOAD DATA INFILE '/etc/passwd' INTO TABLE t",
          'SET PERSIST max_connections=1', 'CREATE TABLE prod . t (id INT)', 'TRUNCATE prod.users', "SELECT 1 INTO OUTFILE '/tmp/x'"]
SEPS = [' ', '\t', '\n', '  ', ' /**/ ']


def mixcase(rng, s):
    return ''.join(c.upper() if rng.random() < .5 else c.lower() for c in s)


def safe(rng, n):
    lit = "'" + rng.choice(['a.b', 'x;y', 'prod.users', '-- z', '/* w */', "it''s", 'USE prod', '#h']) + "'"
    k = rng.randrange(10 ** 9)  # noms et cles uniques dans le script : executable tel quel
    return rng.choice([f'CREATE TABLE t{n}_{k} (id INT PRIMARY KEY, v VARCHAR(40))', f'INSERT INTO t{n} (id, v) VALUES ({k}, {lit})',
                       f'ALTER TABLE t{n} ADD COLUMN c{k} INT', f'CREATE INDEX i{k} ON t{n} (v)'])


def gen(rng, i):
    d = rng.choice(DANGER)
    exposed = rng.random() < .5
    sep = rng.choice(SEPS if exposed else SEPS[:2] + SEPS[3:4])  # pas de /**/ ni \n dans un commentaire (ils le fermeraient)
    d = mixcase(rng, d).replace(' ', sep)
    if exposed:
        frag = rng.choice([d + ';', '/*!40101 ' + d + ' */;', '/*! ' + d + ' */;'])
    else:
        frag = rng.choice(['/* ' + d + ' */', '-- ' + d + '\n', '# ' + d + '\n',
                           "INSERT INTO t%d (id, v) VALUES (%d, '%s');" % (i, -1 - i, d.replace("'", "''").replace('\n', ' '))])
    stmts = [f'CREATE TABLE t{i} (id INT PRIMARY KEY, v VARCHAR(200));'] + [safe(rng, i) + ';' for _ in range(rng.randint(0, 3))]
    stmts.insert(rng.randint(1, len(stmts)), frag)
    return ''.join(s + rng.choice(['\n', ' ', '\r\n']) for s in stmts), exposed


def refused(sql):
    try:
        extract.check_script(sql)
        return False
    except SystemExit:
        return True


SCRIPTS = [gen(random.Random(1000 + i), i) for i in range(N)]


def test_fuzz_verite_de_construction():
    wrong = [(exp, sql) for sql, exp in SCRIPTS if refused(sql) != exp]
    assert not wrong, '%d/%d erreurs, ex. : %r' % (len(wrong), N, wrong[:3])


def test_fuzz_couvre_les_deux_cas():
    assert 0.4 < sum(e for _, e in SCRIPTS) / N < 0.6


def test_fuzz_scripts_acceptes_executes_sans_ecart(db, tmp_path):
    """50 scripts acceptes (fragments caches), executes ensemble : extraction OK, aucun ecart hors base jetable (sinon code 3)."""
    ok = [sql for sql, exp in SCRIPTS if not exp][:50]
    p = tmp_path / 'fuzz.sql'
    p.write_text('\n'.join(ok), encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    assert code == 0, out[-600:]
    assert int(out.split('tables=')[1].split()[0]) >= 50
