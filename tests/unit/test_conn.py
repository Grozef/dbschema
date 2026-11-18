"""Binaires (Laragon/XAMPP/WAMP/MAMP sur arborescence factice), connexion, versions, fichier d'options, refus en ligne de commande."""
import os
import pytest
import extract
from conftest import FIX, extract_cli


@pytest.fixture
def fake(tmp_path, monkeypatch):
    for d, n in (('xampp/mysql/bin', 'mysql'), ('xampp/mysql/bin', 'mysqldump'),
                 ('wamp/bin/mariadb/mariadb11/bin', 'mariadb'), ('wamp/bin/mariadb/mariadb11/bin', 'mariadb-dump')):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
        (tmp_path / d / (n + extract.EXE)).write_bytes(b'')
    monkeypatch.delenv('DBSCHEMA_MYSQL_BIN', raising=False)
    return tmp_path


def test_mariadb_seul_repli_mariadb_dump(fake, monkeypatch):
    monkeypatch.setattr(extract, 'STACKS', [str(fake / 'wamp' / 'bin' / 'mariadb' / '*' / 'bin')])
    assert extract.mysql_bin('mysqldump').endswith('mariadb-dump' + extract.EXE)
    assert extract.mysql_bin('mysql').endswith('mariadb' + extract.EXE)


def test_deux_installations_refus(fake, monkeypatch):
    monkeypatch.setattr(extract, 'STACKS', [str(fake / 'xampp' / 'mysql' / 'bin'), str(fake / 'wamp' / 'bin' / 'mariadb' / '*' / 'bin')])
    with pytest.raises(SystemExit, match='plusieurs'):
        extract.mysql_bin('mysql')


def test_variable_prioritaire(fake, monkeypatch):
    monkeypatch.setattr(extract, 'STACKS', [str(fake / 'wamp' / 'bin' / 'mariadb' / '*' / 'bin')])
    monkeypatch.setenv('DBSCHEMA_MYSQL_BIN', str(fake / 'xampp' / 'mysql' / 'bin'))
    assert 'xampp' in extract.mysql_bin('mysql')


def test_variable_dossier_vide(tmp_path, monkeypatch):
    monkeypatch.setenv('DBSCHEMA_MYSQL_BIN', str(tmp_path))
    with pytest.raises(SystemExit, match='binaire absent'):
        extract.mysql_bin('mysql')


@pytest.mark.parametrize('host,port', [('db;rm -rf', '3306'), ('127.0.0.1', '99999'), ('127.0.0.1', '0'), ('127.0.0.1', '33a'),
                                       ('h\nost', '3306'), ('127.0.0.1', '٣٣٠٦'), ('héte', '3306'),
                                       ('a"b', '3306'), ('', '3306')])
def test_hote_port_invalides(host, port, monkeypatch):
    monkeypatch.setenv('DBSCHEMA_MYSQL_HOST', host)
    monkeypatch.setenv('DBSCHEMA_MYSQL_PORT', port)
    with pytest.raises(SystemExit, match='invalides'):
        extract.conn()


def test_hote_port_par_defaut(monkeypatch):
    monkeypatch.delenv('DBSCHEMA_MYSQL_HOST', raising=False)
    monkeypatch.delenv('DBSCHEMA_MYSQL_PORT', raising=False)
    assert extract.conn() == ('127.0.0.1', '3306')


@pytest.mark.parametrize('raw,want', [("'a''b'", "a'b"), ('NULL', None), ("'NULL'", 'NULL'), ('current_timestamp()', 'current_timestamp()'),
                                      ('0', '0'), (None, None), ("''", '')])
def test_maria_default(raw, want):
    assert extract.maria_default(raw) == want


@pytest.mark.parametrize('out,exe,want', [
    ('mysqldump  Ver 10.13 Distrib 5.7.44, for Linux (x86_64)', 'mysqldump', ('mysql', 5)),
    ('mysqldump  Ver 8.4.3 for Win64 on x86_64 (MySQL Community Server - GPL)', 'mysqldump.exe', ('mysql', 8)),
    ('mysqldump  Ver 8.0.40-0ubuntu0.24.04.1 for Linux on x86_64 ((Ubuntu))', '/usr/bin/mysqldump', ('mysql', 8)),
    ('mysqldump  Ver 10.19 Distrib 10.11.6-MariaDB, for debian-linux-gnu (x86_64)', 'mysqldump', ('mariadb', 10)),
    ('mariadb-dump from 11.4.4-MariaDB, client 10.19 for Linux (x86_64)', '/usr/bin/mariadb-dump', ('mariadb', 11)),
    ('', 'mariadb-dump.exe', ('mariadb', 0)),
])
def test_dump_version(out, exe, want):
    assert extract.dump_version(out, exe) == want


@pytest.fixture
def fake_mysql(tmp_path, monkeypatch):
    (tmp_path / ('mysql' + extract.EXE)).write_bytes(b'')
    monkeypatch.setenv('DBSCHEMA_MYSQL_BIN', str(tmp_path))
    monkeypatch.setenv('DBSCHEMA_MYSQL_HOST', 'localhost')
    monkeypatch.setenv('DBSCHEMA_MYSQL_PORT', '3307')


def test_fichier_options(fake_mysql):
    cmd, cnf = extract.client('mysql', ('zz_user', 'S3cret "x\\y'))
    try:
        txt = open(cnf, encoding='utf-8').read()
    finally:
        os.remove(cnf)
    assert cmd[1].startswith('--defaults-file=') and not any('S3cret' in c for c in cmd)
    assert 'password="S3cret \\"x\\\\y"' in txt and 'local-infile=0' in txt
    assert 'host="localhost"' in txt and 'port=3307' in txt and 'protocol=TCP' in txt


def test_retour_ligne_dans_identifiants_refuse(fake_mysql):
    with pytest.raises(SystemExit, match='retour a la ligne'):
        extract.client('mysql', ('u', 'a\nhost=evil'))


@pytest.mark.parametrize('host', ['db.example.com', 'LOCALHOST', '127.0.0.2', '0', '10.0.0.5'])
def test_sql_hote_non_local_refuse(host):
    code, out = extract_cli('--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', os.devnull,
                            env={**os.environ, 'DBSCHEMA_MYSQL_HOST': host})
    assert code != 0 and 'serveur local seulement' in out, out[-200:]


def test_db_nom_invalide_refuse_sans_requete():
    code, out = extract_cli('--db', "x' OR 1=1 -- ", '--out', os.devnull)
    assert code != 0 and 'nom de base refuse' in out


@pytest.mark.parametrize('db', ['zz_dbschema_20260101000000ab', 'zz_dbschema_sbx1'])
def test_garde_fou_base_jetable_acceptee(db):
    extract.jetable(db)


@pytest.mark.parametrize('db', ['commissioning', 'prod', 'zz_dbschema_x;DROP', 'zz_dbschema_`x`', 'ZZ_DBSCHEMA_x', '', 'zz_dbschem',
                                'zz_dbschema_x\n'])  # \n final : DBNAME en \Z (relecture du 2026-11-18)
def test_garde_fou_refuse_toute_autre_base(db):
    with pytest.raises(SystemExit, match='garde-fou'):
        extract.jetable(db)
