"""Bac a sable : l'utilisateur jetable n'a de droits que sur sa base (base temoin zz_dbschema_victim, creee puis supprimee)."""
import time
import pytest

V = 'zz_dbschema_victim'


@pytest.fixture
def sandbox(db):
    name = db.PREFIX + 'sbx' + time.strftime('%H%M%S')
    state = lambda: db.run("SELECT CONCAT(COUNT(*)) FROM `%s`.t; SELECT GROUP_CONCAT(TABLE_NAME) FROM information_schema.TABLES "
                           "WHERE TABLE_SCHEMA='%s'" % (V, V)).split()
    try:  # tout ce qui est cree l'est dans le try : nettoye meme si une etape echoue
        db.run('DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s`; CREATE TABLE `%s`.t (id INT); INSERT INTO `%s`.t VALUES (1)' % ((V,) * 4))
        before = state()
        cred = db.sandbox_open(name)
        yield name, cred
        assert state() == before, 'base temoin modifiee'
    finally:
        db.sandbox_close(name)
        db.run('DROP DATABASE IF EXISTS `%s`' % V)
    assert db.run("SELECT CONCAT(COUNT(*)) FROM mysql.user WHERE user='%s'" % name).strip() == '0'


def test_hotes_du_compte_sans_joker(db, sandbox):
    hosts = db.run("SELECT host FROM mysql.user WHERE user='%s'" % sandbox[0]).split()
    assert {'127.0.0.1', 'localhost'} <= set(hosts) and not any(c in h for h in hosts for c in '%_'), hosts


def test_droits_de_chaque_hote(db, sandbox):
    name = sandbox[0]
    for h in db.run("SELECT host FROM mysql.user WHERE user='%s'" % name).split():
        g = db.run("SHOW GRANTS FOR '%s'@'%s'" % (name, h)).strip().splitlines()
        assert len(g) == 2 and 'GRANT USAGE ON *.*' in g[0] and ('`%s`.*' % name.replace('_', '\\_')) in g[1], (h, g)


def test_ecriture_dans_sa_base(db, sandbox):
    name, cred = sandbox
    assert db.run('CREATE TABLE a (id INT); INSERT INTO a VALUES (1); SELECT COUNT(*) FROM a', db=name, cred=cred).strip() == '1'


@pytest.mark.parametrize('sql', ['CREATE TABLE `%s`.x (id INT)' % V, 'INSERT INTO `%s`.t VALUES (2)' % V, 'DROP TABLE `%s`.t' % V,
                                 'DROP DATABASE `%s`' % V, 'USE `%s`' % V, 'CREATE DATABASE `zz_dbschema_other`',
                                 'SELECT * FROM mysql.user', 'SET GLOBAL max_connections=1', 'CREATE USER zz_x',
                                 "SELECT 1 INTO OUTFILE '/tmp/zz_dbschema_out'"],
                         ids=['create', 'insert', 'drop_table', 'drop_db', 'use', 'create_db', 'mysql_user', 'set_global',
                              'create_user', 'outfile'])
def test_refuse_hors_de_sa_base(db, sandbox, sql):
    name, cred = sandbox
    with pytest.raises(RuntimeError) as e:
        db.run(sql, db=name, cred=cred)
    msg = str(e.value).lower()
    assert 'denied' in msg or 'access' in msg or 'privilege' in msg, msg


def test_load_file_renvoie_null(db, sandbox):
    """Sans le droit FILE, LOAD_FILE ne leve pas d'erreur : il renvoie NULL (aucun fichier lu)."""
    name, cred = sandbox
    for f in ('/etc/passwd', 'C:/Windows/win.ini'):
        assert db.run("SELECT IFNULL(LOAD_FILE('%s'), 'NULL')" % f, db=name, cred=cred).strip() == 'NULL'


def test_binary_mode_commande_client_inerte(db, sandbox):
    name, cred = sandbox
    try:
        out = db.run(None, db=name, stdin=b'CREATE TABLE b (id INT);\n\\! echo PWNED_SHELL\n', binary=True, cred=cred)
    except RuntimeError as e:
        out = str(e)
    assert 'PWNED_SHELL' not in out.replace('echo PWNED_SHELL', '')
