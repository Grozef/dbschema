"""Non-regression des constats des audits de securite (vol ou acces a des donnees)."""
import os, re
import extract
from conftest import extract_cli


def test_nom_avec_retour_ligne_refuse(db, tmp_path):
    p = tmp_path / 'ctrl.sql'
    p.write_text('CREATE TABLE `h\nx` (id INT PRIMARY KEY);', encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    assert code != 0 and 'caracteres de controle' in out


def test_export_sans_compteur_auto_increment(db, tmp_path):
    p = tmp_path / 'ai.sql'
    p.write_text("CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY, v INT);\nINSERT INTO t (v) VALUES (1),(2),(3);", encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'), '--sql-out', str(tmp_path / 'o.sql'))
    d = (tmp_path / 'o.sql').read_text(encoding='utf-8')
    assert code == 0 and 'CREATE TABLE' in d and not re.search(r'AUTO_INCREMENT=\d', d)


def test_commentaire_intact_compteur_retire(db, tmp_path):
    p = tmp_path / 'aic.sql'
    p.write_text("CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY) COMMENT='voir AUTO_INCREMENT=7 ici';\nINSERT INTO t VALUES (5);",
                 encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'), '--sql-out', str(tmp_path / 'o.sql'))
    d = (tmp_path / 'o.sql').read_text(encoding='utf-8')
    assert code == 0 and 'voir AUTO_INCREMENT=7 ici' in d and 'AUTO_INCREMENT=6' not in d


def test_vue_trigger_detectes_export_tables_seules(db, tmp_path):
    sb = db.PREFIX + 'sec' + str(os.getpid())
    try:
        db.sandbox_open(sb)
        db.run('CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t; '
               'CREATE TRIGGER tr BEFORE INSERT ON t FOR EACH ROW SET NEW.id = NEW.id', db=sb)
        found = db.non_tables(sb)
        assert any(x.startswith('vue') for x in found) and any(x.startswith('trigger') for x in found), found
        db.dump(sb, str(tmp_path / 'd.sql'))
        d = (tmp_path / 'd.sql').read_text(encoding='utf-8')
        assert 'CREATE TABLE' in d and not re.search(r'VIEW|TRIGGER|DEFINER|GTID_PURGED', d)
    finally:
        db.sandbox_close(sb)


def test_vue_dans_un_commentaire_executable_refusee_par_le_filtre(db, tmp_path):
    """CREATE VIEW cache dans /*!50001 ... */ : refuse AVANT execution par le filtre. Le refus APRES execution (filtre
    contourne) est prouve par tests/functional/test_revue.py::test_refus_apres_execution_si_le_filtre_est_contourne."""
    p = tmp_path / 'v.sql'
    p.write_text('CREATE TABLE t (id INT);\n/*!50001 CREATE VIEW v AS SELECT id FROM t */;', encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    assert code != 0 and 'script refuse' in out and 'CREATE VIEW' in out


def test_orphelin_ancien_supprime(db):
    old = db.PREFIX + '20000101000000ab'
    try:
        db.run('CREATE DATABASE IF NOT EXISTS `%s`' % old)
        db.cleanup_stale()
        assert not db.run("SHOW DATABASES LIKE '%s'" % old.replace('_', '\\_')).strip()
    finally:
        db.run('DROP DATABASE IF EXISTS `%s`' % old)


def test_orphelin_recent_conserve(db):
    """Une execution en cours (moins d'une heure) n'est jamais nettoyee par une autre."""
    import time
    recent = db.PREFIX + time.strftime('%Y%m%d%H%M%S') + 'cd'
    db.run('CREATE DATABASE IF NOT EXISTS `%s`' % recent)
    try:
        db.cleanup_stale()
        assert db.run("SHOW DATABASES LIKE '%s'" % recent.replace('_', '\\_')).strip()
    finally:
        db.run('DROP DATABASE IF EXISTS `%s`' % recent)


def test_aucun_cnf_laisse_si_binaire_absent(tmp_path, monkeypatch):
    import tempfile
    before = set(os.listdir(tempfile.gettempdir()))
    monkeypatch.setenv('DBSCHEMA_MYSQL_BIN', str(tmp_path / 'absent'))
    try:
        extract.client('mysql', ('u', 'pw'))
    except SystemExit:
        pass
    assert not [f for f in set(os.listdir(tempfile.gettempdir())) - before if f.startswith('dbschema_')]


def test_cnf_supprime_apres_requete(db):
    import tempfile
    before = set(os.listdir(tempfile.gettempdir()))
    db.run('SELECT 1')
    assert not [f for f in set(os.listdir(tempfile.gettempdir())) - before if f.startswith('dbschema_')]


def test_csp_du_html_livre(demo):
    html = (demo['out'] / 'DEMO.html').read_text(encoding='utf-8')
    assert "default-src 'none'" in html and "connect-src 'none'" in html
