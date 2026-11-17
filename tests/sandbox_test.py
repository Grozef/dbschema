"""Bac a sable MySQL : l'utilisateur jetable n'a de droits que sur sa base. Cibles : une base temoin zz_dbschema_victim
(creee puis supprimee ici) ; aucune autre base n'est visee. Usage : python -I sandbox_test.py <dossier lib>"""
import sys, time
sys.path.insert(0, sys.argv[1])
import extract

V = 'zz_dbschema_victim'
results = []


def ok(name, cond, detail=''):
    results.append(bool(cond))
    print(('[OK] ' if cond else '[ECHEC] ') + name + (f'  ({detail})' if detail != '' else ''))


def victim_state():
    return extract.run("SELECT CONCAT(COUNT(*)) FROM `%s`.t; SELECT GROUP_CONCAT(TABLE_NAME) FROM information_schema.TABLES WHERE TABLE_SCHEMA='%s'" % (V, V)).split()


extract.run('DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s`; CREATE TABLE `%s`.t (id INT); INSERT INTO `%s`.t VALUES (1)' % (V, V, V, V))
db = extract.PREFIX + 'sbx' + time.strftime('%H%M%S')
try:
    before = victim_state()
    cred = extract.sandbox_open(db)
    grants = extract.run("SHOW GRANTS FOR '%s'@'127.0.0.1'" % db).strip().splitlines()
    ok('droits : USAGE global + ALL sur sa seule base', len(grants) == 2 and 'GRANT USAGE ON *.*' in grants[0]
       and ('`%s`.*' % db.replace('_', '\\_')) in grants[1], grants)
    ok('ecriture dans sa base', extract.run('CREATE TABLE a (id INT); INSERT INTO a VALUES (1); SELECT COUNT(*) FROM a', db=db, cred=cred).strip() == '1')
    for name, sql in [('CREATE TABLE dans une autre base', 'CREATE TABLE `%s`.x (id INT)' % V),
                      ('INSERT dans une autre base', 'INSERT INTO `%s`.t VALUES (2)' % V),
                      ('DROP TABLE dans une autre base', 'DROP TABLE `%s`.t' % V),
                      ('DROP DATABASE autre', 'DROP DATABASE `%s`' % V),
                      ('USE autre base', 'USE `%s`' % V),
                      ('CREATE DATABASE', 'CREATE DATABASE `zz_dbschema_other`')]:
        try:
            extract.run(sql, db=db, cred=cred); refused = False
        except RuntimeError as e:
            refused = 'denied' in str(e).lower()
        ok('refuse : ' + name, refused)
    out = ''
    try:
        out = extract.run(None, db=db, stdin=b'CREATE TABLE b (id INT);\n\\! echo PWNED_SHELL\n', binary=True, cred=cred)
    except RuntimeError as e:
        out = str(e)
    ok('--binary-mode : commande \\! non executee', 'PWNED_SHELL' not in out.replace('echo PWNED_SHELL', ''), out[:80])
    ok('base temoin intacte', victim_state() == before, (before, victim_state()))
finally:
    extract.sandbox_close(db)
    extract.run('DROP DATABASE IF EXISTS `%s`' % V)
left = extract.run("SELECT CONCAT(COUNT(*)) FROM mysql.user WHERE user LIKE 'zz\\_dbschema\\_%'; SHOW DATABASES LIKE 'zz\\_dbschema\\_%'").split()
ok('nettoyage : aucun utilisateur ni base zz_dbschema_ restants', left == ['0'], left)
sys.exit(0 if all(results) else 1)
