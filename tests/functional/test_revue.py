"""Corrections de la revue du 2026-11-18, contre un vrai serveur : exports phpMyAdmin et Adminer, BOM, erreur MySQL lisible,
--db avec un compte en SELECT seul, vue au nom piege, refus APRES execution (2e ligne de defense)."""
import os, re, secrets, sys, time
import pytest
from conftest import FIX, LIB, extract_cli


def fresh(db):
    """Nom jetable au format reconnu par cleanup_stale (horodatage) : nettoye meme apres un arret brutal."""
    return db.PREFIX + time.strftime('%Y%m%d%H%M%S') + secrets.token_hex(2)


@pytest.mark.parametrize('fixture', ['phpmyadmin.sql', 'adminer.sql'])
def test_export_outil_accepte(db, tmp_path, fixture):
    code, out = extract_cli('--sql', os.path.join(FIX, fixture), '--out', str(tmp_path / 'm.json'))
    assert code == 0 and 'tables=2' in out and 'relations=1' in out, out[-500:]


def test_fichier_avec_bom_accepte(db, tmp_path):
    p = tmp_path / 'bom.sql'
    p.write_bytes(b'\xef\xbb\xbf' + open(os.path.join(FIX, 'adminer.sql'), 'rb').read())
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    assert code == 0 and 'tables=2' in out, out[-500:]


def test_erreur_mysql_lisible_sans_trace(db, tmp_path):
    p = tmp_path / 'faute.sql'
    p.write_text('CREATE TABLE t (id INT;', encoding='utf-8')
    code, out = extract_cli('--sql', str(p), '--out', str(tmp_path / 'm.json'))
    # le client MariaDB recopie l'instruction fautive avant "ERROR 1064" : on exige le prefixe et le code, pas leur contiguite
    assert code != 0 and 'erreur : ' in out and 'ERROR 1064' in out and 'Traceback' not in out, out[-500:]


def test_db_avec_compte_en_select_seul(db, tmp_path):
    """Cas normal d'un serveur distant : ni LOCK TABLES ni PROCESS ; mysqldump doit passer (--skip-lock-tables, --no-tablespaces)."""
    name = fresh(db)
    pw = 'Ro9' + secrets.token_hex(8)
    try:
        db.run('CREATE DATABASE `%s`; CREATE TABLE `%s`.p (id INT PRIMARY KEY); '
               'CREATE TABLE `%s`.c (id INT PRIMARY KEY, p_id INT NOT NULL, FOREIGN KEY (p_id) REFERENCES `%s`.p(id))' % ((name,) * 4))
        for h in db.sandbox_hosts():
            db.run(None, stdin=("CREATE USER '%s'@'%s' IDENTIFIED BY '%s';" % (name, h, pw)).encode())
            db.run("GRANT SELECT, SHOW VIEW ON `%s`.* TO '%s'@'%s'" % (name.replace('_', '\\_'), name, h))
        env = {**os.environ, 'DBSCHEMA_MYSQL_USER': name, 'DBSCHEMA_MYSQL_PASSWORD': pw}
        code, out = extract_cli('--db', name, '--out', str(tmp_path / 'm.json'), '--sql-out', str(tmp_path / 'd.sql'), env=env)
        assert code == 0 and 'tables=2' in out and 'relations=1' in out, out[-600:]
        assert (tmp_path / 'd.sql').read_text(encoding='utf-8').count('CREATE TABLE') == 2
    finally:
        db.sandbox_close(name)  # compte (tous ses hotes) et base


def test_vue_au_nom_piege_refusee_a_l_export(db, tmp_path):
    """Avant : le nom etait coupe au retour a la ligne, la vue echappait a ignore-table et finissait dans le SQL exporte."""
    name = fresh(db)
    try:
        db.run('CREATE DATABASE `%s`' % name)
        db.run("CREATE TABLE t (id INT PRIMARY KEY); CREATE VIEW `v\nresult-file=x\n#` AS SELECT id FROM t", db=name)
        code, out = extract_cli('--db', name, '--out', str(tmp_path / 'm.json'), '--sql-out', str(tmp_path / 'd.sql'))
        assert code != 0 and 'noms de vues refuses' in out, out[-400:]
        assert not (tmp_path / 'd.sql').exists()
    finally:
        db.run('DROP DATABASE IF EXISTS `%s`' % name)


def test_vue_ordinaire_exclue_de_l_export(db, tmp_path):
    name = fresh(db)
    try:
        db.run('CREATE DATABASE `%s`' % name)
        db.run('CREATE TABLE t (id INT PRIMARY KEY); CREATE VIEW v AS SELECT id FROM t', db=name)
        code, out = extract_cli('--db', name, '--out', str(tmp_path / 'm.json'), '--sql-out', str(tmp_path / 'd.sql'))
        assert code == 0, out[-400:]
        assert not re.search(r'VIEW', (tmp_path / 'd.sql').read_text(encoding='utf-8'))
    finally:
        db.run('DROP DATABASE IF EXISTS `%s`' % name)


def test_refus_apres_execution_si_le_filtre_est_contourne(db, tmp_path, monkeypatch, capsys):
    """2e ligne de defense : filtre neutralise, le script cree une vue -> main() refuse APRES execution, base jetable nettoyee."""
    sys.path.insert(0, LIB)
    import extract
    p = tmp_path / 'v.sql'
    p.write_text('CREATE TABLE t (id INT);\nCREATE VIEW v AS SELECT id FROM t;', encoding='utf-8')
    monkeypatch.setattr(extract, 'check_script', lambda sql: None)
    monkeypatch.setattr(sys, 'argv', ['extract.py', '--sql', str(p), '--out', str(tmp_path / 'm.json')])
    before = set(db.run("SHOW DATABASES LIKE 'zz\\_dbschema\\_%'").split())
    with pytest.raises(SystemExit) as e:
        extract.main()
    assert 'autre chose que des tables' in str(e.value) and "vue v" in str(e.value)
    assert set(db.run("SHOW DATABASES LIKE 'zz\\_dbschema\\_%'").split()) == before  # base jetable supprimee malgre le refus
    assert not (tmp_path / 'm.json').exists()


def test_table_creee_hors_base_jetable_arrete_tout(db, tmp_path, monkeypatch, capsys):
    """Releve avant/apres dans main() : une table apparue ailleurs pendant l'extraction -> code 3, aucun modele ecrit."""
    import extract
    snaps = iter([{'shop.t': ('2026-01-01', '')}, {'shop.t': ('2026-01-01', ''), 'prod.evil': ('2026-11-18', '')}])
    monkeypatch.setattr(extract, 'snapshot', lambda: next(snaps))
    p = tmp_path / 's.sql'
    p.write_text('CREATE TABLE t (id INT PRIMARY KEY);', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['extract.py', '--sql', str(p), '--out', str(tmp_path / 'm.json')])
    with pytest.raises(SystemExit) as e:
        extract.main()
    assert e.value.code == 3 and '+ prod.evil' in capsys.readouterr().err
    assert not (tmp_path / 'm.json').exists()


def test_laravel_tables_du_framework_retirees_et_annoncees(db, tmp_path, monkeypatch, capsys):
    """Branche --laravel de main() avec un migrate simule (aucun code PHP) : tables du framework retirees, et dites."""
    import extract

    def fake_migrate(repo, name, cred):
        extract.run('CREATE TABLE sessions (id INT PRIMARY KEY); CREATE TABLE migrations (id INT PRIMARY KEY); '
                    'CREATE TABLE commandes (id INT PRIMARY KEY)', db=name, cred=cred)
    monkeypatch.setattr(extract, 'laravel_migrate', fake_migrate)
    for keep, expect in ((False, {'commandes'}), (True, {'commandes', 'migrations', 'sessions'})):
        out = tmp_path / ('m%d.json' % keep)
        monkeypatch.setattr(sys, 'argv', ['extract.py', '--laravel', str(tmp_path), '--trust-repo', '--out', str(out)]
                            + (['--keep-framework'] if keep else []))
        extract.main()
        model = __import__('json').load(open(out, encoding='utf-8'))
        assert set(model['tables']) == expect and model['source']['kind'] == 'laravel'
        err = capsys.readouterr().err
        assert ('tables du framework retirees' in err) != keep and ('migrations, sessions' in err) != keep


def test_fk_vers_base_homonyme_a_la_casse_pres(db, tmp_path):
    """Serveur sensible a la casse seulement (Linux : CI, Docker) : FK de « ..shop » vers « ..Shop » = externe, build possible."""
    import extract
    extract.server.cache_clear()
    if not extract.server()[2]:
        pytest.skip('serveur insensible a la casse (lower_case_table_names != 0) : cas impossible ici')
    lo = fresh(db)
    up = lo.upper()  # meme nom, seule la casse differe
    try:
        db.run('CREATE DATABASE `%s`; CREATE DATABASE `%s`; CREATE TABLE `%s`.users (id INT PRIMARY KEY); '
               'CREATE TABLE `%s`.orders (id INT PRIMARY KEY, u INT, FOREIGN KEY (u) REFERENCES `%s`.users(id))' % (lo, up, up, lo, up))
        code, out = extract_cli('--db', lo, '--out', str(tmp_path / 'm.json'))
        assert code == 0 and 'relations=0' in out and 'FK vers une autre base' in out, out[-400:]
    finally:
        db.run('DROP DATABASE IF EXISTS `%s`; DROP DATABASE IF EXISTS `%s`' % (lo, up))
