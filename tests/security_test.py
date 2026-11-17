"""Non-regression des constats de l'audit de securite (vol ou acces a des donnees). Ecrit seulement dans des bases et comptes
zz_dbschema_* (supprimes). Usage : python -I security_test.py <dossier lib> <dossier temporaire>"""
import ast, json, os, re, subprocess, sys
LIB, TMP = sys.argv[1], sys.argv[2]
sys.path.insert(0, LIB)
import extract, workbench

os.makedirs(TMP, exist_ok=True)
results = []


def ok(name, cond, detail=''):
    results.append(bool(cond))
    print(('[OK] ' if cond else '[ECHEC] ') + name + (f'  ({detail})' if detail != '' else ''))


def cli(*args):
    r = subprocess.run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), *args], capture_output=True, text=True, encoding='utf-8')
    return r.returncode, r.stdout + r.stderr


# 1. script Workbench : un nom de table avec retour a la ligne ne doit jamais devenir du code
lay = {'tables': {'h\nprint("PWN")\n#': {'x': 0, 'y': 0, 'w': 100, 'h': 60}, 't': {'x': 0, 'y': 100, 'w': 100, 'h': 60}},
       'hubs': ['h\nprint("PWN")\n#']}
lp, sp = os.path.join(TMP, 'lay.json'), os.path.join(TMP, 'wb.py')
json.dump(lay, open(lp, 'w', encoding='utf-8'))
workbench.cmd_script(lp, sp)
src = open(sp, encoding='utf-8').read()
tree = ast.parse(src)
# le nom piege ne doit exister que dans des chaines (constantes), jamais comme appel ni sur une ligne de code
calls = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call) and 'PWN' in ast.unparse(n.func)]
ok('script Workbench : nom piege reste une chaine, jamais du code', not calls and not any(l.startswith('print("PWN")') for l in src.splitlines()),
   calls)

# 2. noms avec caracteres de controle refuses a l'extraction
p = os.path.join(TMP, 'ctrl.sql')
open(p, 'w', encoding='utf-8').write('CREATE TABLE `h\nx` (id INT PRIMARY KEY);')
code, out = cli('--sql', p, '--out', os.path.join(TMP, 'ctrl.json'))
ok('nom de table avec retour a la ligne refuse', code != 0 and 'caracteres de controle' in out, out.strip().splitlines()[-1][:90])

# 3. mot de passe jamais sur la ligne de commande ; aucun my.ini lu ; local-infile=0
cmd, cnf = extract.client('mysql', ('zz_user', 'S3cret_pw'))
txt = open(cnf, encoding='utf-8').read(); os.remove(cnf)
ok('identifiants hors ligne de commande (--defaults-file en 1er)', cmd[1].startswith('--defaults-file=') and not any('S3cret' in c for c in cmd)
   and 'password="S3cret_pw"' in txt and 'local-infile=0' in txt, cmd[1:])

# 4. export : ni AUTO_INCREMENT=N ni DEFINER ni trigger
p = os.path.join(TMP, 'ai.sql')
open(p, 'w', encoding='utf-8').write("CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY, v INT);\nINSERT INTO t (v) VALUES (1),(2),(3);")
code, out = cli('--sql', p, '--out', os.path.join(TMP, 'ai.json'), '--sql-out', os.path.join(TMP, 'ai_out.sql'))
dumped = open(os.path.join(TMP, 'ai_out.sql'), encoding='utf-8').read() if code == 0 else ''
ok('export sans AUTO_INCREMENT=N', code == 0 and 'CREATE TABLE' in dumped and not re.search(r'AUTO_INCREMENT=\d', dumped),
   out.strip().splitlines()[-1][:80])
# un AUTO_INCREMENT=N dans un COMMENTAIRE n'est pas touche (retrait limite aux options de table)
p = os.path.join(TMP, 'aic.sql')
open(p, 'w', encoding='utf-8').write("CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY) COMMENT='voir AUTO_INCREMENT=7 ici';\nINSERT INTO t VALUES (5);")
code, out = cli('--sql', p, '--out', os.path.join(TMP, 'aic.json'), '--sql-out', os.path.join(TMP, 'aic_out.sql'))
dumped = open(os.path.join(TMP, 'aic_out.sql'), encoding='utf-8').read() if code == 0 else ''
ok('commentaire intact, compteur retire', "voir AUTO_INCREMENT=7 ici" in dumped and 'AUTO_INCREMENT=6' not in dumped)  # compteur reel apres id 5

# 4b. vue / trigger / routine dans la base jetable : detectes apres execution (contournement du filtre), export = tables seules
sb = extract.PREFIX + 'sec' + str(os.getpid())
try:
    extract.sandbox_open(sb)
    extract.run('CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t; '
                'CREATE TRIGGER tr BEFORE INSERT ON t FOR EACH ROW SET NEW.id = NEW.id', db=sb)
    found = extract.non_tables(sb)
    ok('vue et trigger detectes apres execution', any(x.startswith('vue') for x in found) and any(x.startswith('trigger') for x in found), found)
    dp = os.path.join(TMP, 'tables_only.sql')
    extract.dump(sb, dp)
    d = open(dp, encoding='utf-8').read()
    ok('export : tables seules (ni vue, ni trigger, ni DEFINER, ni GTID)', 'CREATE TABLE' in d and not re.search(r'VIEW|TRIGGER|DEFINER|GTID_PURGED', d))
finally:
    extract.sandbox_close(sb)

# 4c. jeux de caracteres a echappement multi-octets refuses par le filtre (decalage de chaine)
try:
    extract.check_script("SET NAMES gbk; INSERT INTO t VALUES ('\xbf\\\\'); CREATE VIEW v AS SELECT 1; -- ');"); refused = False
except SystemExit:
    refused = True
ok('SET NAMES gbk refuse', refused)

# 4d. fichier d'options : aucun fichier laisse si le binaire est introuvable
before = set(os.listdir(os.environ.get('TEMP', '/tmp')))
os.environ['DBSCHEMA_MYSQL_BIN'] = os.path.join(TMP, 'absent')
try:
    extract.client('mysql', ('u', 'pw'))
except SystemExit:
    pass
del os.environ['DBSCHEMA_MYSQL_BIN']
left = [f for f in set(os.listdir(os.environ.get('TEMP', '/tmp'))) - before if f.startswith('dbschema_')]
ok('aucun .cnf laisse quand le binaire manque', not left, left)

# 5. --laravel refuse sans --trust-repo (le code du depot serait execute)
code, out = cli('--laravel', TMP, '--out', os.path.join(TMP, 'l.json'))
ok('--laravel refuse sans --trust-repo', code != 0 and '--trust-repo' in out)

# 6. orphelins d'une execution tuee (plus d'une heure) supprimes au lancement suivant
old = extract.PREFIX + '20000101000000ab'
extract.run('CREATE DATABASE IF NOT EXISTS `%s`' % old)
extract.cleanup_stale()
ok('base orpheline ancienne supprimee', not extract.run("SHOW DATABASES LIKE '%s'" % old.replace('_', '\\_')).strip())

# 7. HTML : CSP sans connexion externe
html = open(os.path.join(TMP, '..', 'com_out', 'COM.html'), encoding='utf-8').read() if os.path.exists(os.path.join(TMP, '..', 'com_out', 'COM.html')) else ''
ok('HTML : CSP default-src none, connect-src none', "default-src 'none'" in html and "connect-src 'none'" in html)
sys.exit(0 if all(results) else 1)
