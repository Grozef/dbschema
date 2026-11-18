"""Tests de bout en bout de dbschema : extraction (cardinalites), mise en page + controles, sorties.
Usage : python tests/run_tests.py <dossier_temporaire>   (code de sortie 1 au premier echec)"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, '..', 'lib')
FIX = os.path.join(HERE, 'fixtures')
tmp = sys.argv[1]
os.makedirs(tmp, exist_ok=True)
fails = []


def ok(name, cond, detail=''):
    print(('[OK] ' if cond else '[ECHEC] ') + name + (f'  ({detail})' if detail != '' else ''))
    if not cond:
        fails.append(name)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return r.returncode, r.stdout + r.stderr


# 1. extraction des cas limites
m_path = os.path.join(tmp, 'edge_model.json')
code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', os.path.join(FIX, 'edge-cases.sql'),
                 '--out', m_path, '--sql-out', os.path.join(tmp, 'edge.sql')])
ok('extraction edge-cases', code == 0, out.strip().splitlines()[-1] if out.strip() else '')
m = json.load(open(m_path, encoding='utf-8'))
rel = {r['from']: r for r in m['relations']}
expect = {
    'child_mandatory': ('1', '0..N'), 'child_optional': ('0..1', '0..N'),
    'one_to_one_mandatory': ('1', '0..1'), 'one_to_one_optional': ('0..1', '0..1'),
    'self_ref': ('0..1', '0..N'), 'composite_child': ('1', '0..N'), 'circular_y': ('1', '0..N'), 'circular_x': ('0..1', '0..N'),
    'hub_ref_9': ('0..1', '0..N'),
    'profile': ('1', '0..1'), 'profile_photo': ('1', '0..N'), 'address': ('0..1', '0..N'),
}
for t, (p, c) in expect.items():
    r = rel.get(t)
    ok(f'cardinalite {t}', r and (r['card_parent'], r['card_child']) == (p, c), r and (r['card_parent'], r['card_child']))
ok('FK composite : 2 colonnes', rel['composite_child']['columns'] == ['a', 'b'], rel['composite_child']['columns'])
ok('table isolee presente', 'isolated' in m['tables'])

# 2. mise en page + controles + sorties
code, out = run(['node', os.path.join(LIB, 'build.mjs'), m_path, os.path.join(tmp, 'edge_out'), 'EDGE'])
ok('build edge-cases (controles OK)', code == 0, ' | '.join(l for l in out.splitlines() if l.startswith('[')) if code == 0 else out.strip()[-600:])
lay = json.load(open(os.path.join(tmp, 'edge_out', '_build', 'layout_all.json'), encoding='utf-8'))
ok('hub detecte', lay['hubs'] == ['hub'], lay['hubs'])
ok('9 liens hub en amorces', len(lay['splits']) == 9, len(lay['splits']))
self_e = [e for e in lay['edges'] if e['from'] == e['to'] == 'self_ref']
ok('auto-reference tracee', len(self_e) == 1 and len(self_e[0]['points']) >= 2, self_e and len(self_e[0]['points']))
for f in ('EDGE.html', 'EDGE.png'):
    p = os.path.join(tmp, 'edge_out', f)
    ok(f'sortie {f}', os.path.exists(p) and os.path.getsize(p) > 1000, os.path.exists(p) and os.path.getsize(p))
ok('texte mesure dans Chrome, 0 debordement (noms accentues et chinois compris)', '[texte] debordements mesures' in out and ': 0 -> OK' in out,
   [l for l in out.splitlines() if l.startswith('[texte]')])
# arrivee sur la colonne referencee : parent.id recoit des FK de cardinalite 1 et 0..1 -> un port par cote ; profile.parent_id
# est a la fois depart (FK) et arrivee (referencee) ; country.iso (UNIQUE, pas PK) reste visible en mode cles
by = {}
for e in lay['edges']:
    by.setdefault(e['to'], []).append(e)
sides = {(e['card_parent'], 'E' if abs(e['points'][-1][0] - lay['tables']['parent']['x']) > 1 else 'W') for e in by['parent']}
ok('parent.id : un port par cardinalite parent, sur deux cotes', len(sides) == 2 and len({s for _, s in sides}) == 2, sorted(sides))
keys = json.load(open(os.path.join(tmp, 'edge_out', '_build', 'layout_keys.json'), encoding='utf-8'))
ok('mode cles : country.iso visible', 'iso' in keys['tables']['country']['rows'], keys['tables']['country']['rows'])
import importlib.util
# controles : chaque mutation (accroche, completude, etiquettes, cadre, traversee) doit etre detectee
code, out = run(['node', os.path.join(HERE, 'check_mutations.mjs'), os.path.join(tmp, 'edge_out', '_build', 'layout_all.json'),
                 os.path.join(tmp, 'edge_out', '_build', 'layout_names.json')])
ok('controles : mutations detectees', code == 0, ' | '.join(l for l in out.splitlines() if 'ECHEC' in l) or out.count('[OK]'))
# filtre du script : 16 scripts dangereux refuses, 5 legitimes acceptes (fonction seule, sans base)
code, out = run([sys.executable, '-I', os.path.join(HERE, 'script_probes.py'), LIB])
ok('filtre du script : sondes', code == 0, ' | '.join(l for l in out.splitlines() if 'ECHEC' in l) or out.strip().splitlines()[-1])

# cardinalites declarees (--cards) : 1..N accepte, cle inconnue et valeur invalide refusees
cards_ok = os.path.join(tmp, 'cards_ok.json'); json.dump({'child_mandatory.parent_id': {'child': '1..N'}}, open(cards_ok, 'w'))
code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', os.path.join(FIX, 'edge-cases.sql'),
                 '--out', os.path.join(tmp, 'cards.json'), '--cards', cards_ok])
r = {x['from']: x for x in json.load(open(os.path.join(tmp, 'cards.json'), encoding='utf-8'))['relations']}['child_mandatory']
ok('--cards : 1..N declare', code == 0 and r['card_child'] == '1..N' and r['declared'] == ['child'], (r['card_child'], r.get('declared')))
for bad, why in (({'nope.parent_id': {'child': '1..N'}}, 'cle inconnue'), ({'child_mandatory.parent_id': {'parent': '1..N'}}, 'valeur invalide'),
                 ({'composite_child.a': {'child': '1..N'}, 'composite_child.b': {'child': '1'}}, 'colonne qui n\'est pas la 1re d\'une FK'),
                 ({'child_mandatory.parent_id': '1..N'}, 'valeur non-objet')):
    p = os.path.join(tmp, 'cards_bad.json'); json.dump(bad, open(p, 'w'))
    code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', os.path.join(tmp, 'x.json'), '--cards', p])
    ok('--cards refuse : ' + why, code != 0 and '--cards' in out, out.strip().splitlines()[-1][:80])

# Laravel : une migration vers une autre connexion est refusee AVANT migrate
spec = importlib.util.spec_from_file_location('extract', os.path.join(LIB, 'extract.py')); ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
# deux depots distincts : un dossier temporaire reutilise ne melange pas le cas sain et le cas piege
ok_mig = os.path.join(tmp, 'lara_ok', 'database', 'migrations'); os.makedirs(ok_mig, exist_ok=True)
open(os.path.join(ok_mig, 'a.php'), 'w').write("<?php Schema::connection('mysql')->create('a', fn() => 1);")
ok('Laravel : connexion mysql explicite acceptee', ex.foreign_connections(os.path.join(tmp, 'lara_ok')) == [],
   ex.foreign_connections(os.path.join(tmp, 'lara_ok')))
mig = os.path.join(tmp, 'lara', 'database', 'migrations'); os.makedirs(mig, exist_ok=True)
open(os.path.join(mig, 'b.php'), 'w').write("<?php Schema::connection('legacy')->create('b'); class B { protected $connection = $x; }\n"
                                            "class C { public function getConnection() { return 'legacy'; } }\nDB::statement('USE prod');\n"
                                            "DB::table('prod.users')->truncate(); config(['database.connections.mysql.database' => 'prod']);\n"
                                            "Config::set('database.connections.mysql.username', 'root'); DB::disconnect('mysql'); new PDO('x'); User::on('legacy');")
found = ex.foreign_connections(os.path.join(tmp, 'lara'))
ok('Laravel : autre connexion, getConnection, USE, base.table, config(), Config::set, disconnect, PDO, ::on refuses', len(found) == 10, found)
# --db : nom invalide refuse avant toute requete ; base inexistante refusee (lecture seule)
code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--db', "x' OR 1=1 -- ", '--out', os.path.join(tmp, 'x.json')])
ok('--db : nom invalide refuse', code != 0 and 'nom de base refuse' in out, out.strip()[-80:])
code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--db', 'zz_dbschema_inexistante_xyz', '--out', os.path.join(tmp, 'x.json')])
ok('--db : base inexistante refusee', code != 0 and 'inexistante' in out, out.strip()[-80:])

# 2b. portabilite : binaires (Laragon/XAMPP/WAMP/MAMP) sur une arborescence factice, hote et port, valeurs par defaut MariaDB
def exits(f, *a):
    try:
        return 'ok', f(*a)
    except SystemExit as e:
        return 'exit', str(e)
fake = os.path.join(tmp, 'stacks')
for d, n in (('xampp/mysql/bin', 'mysql'), ('wamp/bin/mariadb/mariadb11/bin', 'mariadb'), ('wamp/bin/mariadb/mariadb11/bin', 'mariadb-dump')):
    os.makedirs(os.path.join(fake, d), exist_ok=True)
    open(os.path.join(fake, d, n + ex.EXE), 'w').close()
saved_env, saved_stacks = dict(os.environ), ex.STACKS
try:
    os.environ.pop('DBSCHEMA_MYSQL_BIN', None)
    ex.STACKS = [os.path.join(fake, 'wamp', 'bin', 'mariadb', '*', 'bin')]
    r = exits(ex.mysql_bin, 'mysqldump')
    ok('binaires : MariaDB 11 seul -> mariadb-dump', r[0] == 'ok' and r[1].endswith('mariadb-dump' + ex.EXE), r)
    ex.STACKS = [os.path.join(fake, 'xampp', 'mysql', 'bin'), os.path.join(fake, 'wamp', 'bin', 'mariadb', '*', 'bin')]
    r = exits(ex.mysql_bin, 'mysql')
    ok('binaires : deux installations -> refus', r[0] == 'exit' and 'plusieurs' in r[1], r)
    os.environ['DBSCHEMA_MYSQL_BIN'] = os.path.join(fake, 'xampp', 'mysql', 'bin')
    r = exits(ex.mysql_bin, 'mysql')
    ok('binaires : DBSCHEMA_MYSQL_BIN prioritaire', r[0] == 'ok' and 'xampp' in r[1], r)
    del os.environ['DBSCHEMA_MYSQL_BIN']
    for h, p in (('db;rm -rf', '3306'), ('127.0.0.1', '99999'), ('127.0.0.1', '33a'), ('h\nost', '3306'),
                 ('127.0.0.1', '٣٣٠٦'), ('héte', '3306'), ('a"b', '3306')):
        os.environ.update(DBSCHEMA_MYSQL_HOST=h, DBSCHEMA_MYSQL_PORT=p)
        r = exits(ex.conn)
        ok('hote/port invalide refuse : %s:%s' % (ascii(h), ascii(p)), r[0] == 'exit' and 'invalides' in r[1], ascii(r))  # console cp1252
finally:
    ex.STACKS = saved_stacks
    os.environ.clear(); os.environ.update(saved_env)
for h in ('db.example.com', 'LOCALHOST', '127.0.0.2', '0'):
    r = subprocess.run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', os.path.join(FIX, 'edge-cases.sql'), '--out',
                        os.path.join(tmp, 'x.json')], capture_output=True, text=True, env={**os.environ, 'DBSCHEMA_MYSQL_HOST': h})
    ok('--sql vers un hote non local refuse (avant toute connexion) : ' + h, r.returncode != 0 and 'serveur local seulement' in r.stderr,
       r.stderr.strip()[-90:])
md = {"'a''b'": "a'b", 'NULL': None, "'NULL'": 'NULL', 'current_timestamp()': 'current_timestamp()', '0': '0', None: None}
ok('MariaDB : COLUMN_DEFAULT normalise', all(ex.maria_default(k) == v for k, v in md.items()), {k: ex.maria_default(k) for k in md})

# 3. Schema de demonstration (librairie) : 19 tables, 31 FK, 6 domaines, controles OK sur toutes les vues
cm = os.path.join(tmp, 'com_model.json')
code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', os.path.join(FIX, 'demo.sql'),
                 '--groups', os.path.join(FIX, 'demo.groups.json'), '--out', cm])
ok('extraction demo', code == 0 and 'tables=19' in out and 'relations=31' in out, out.strip())
code, out = run(['node', os.path.join(LIB, 'build.mjs'), cm, os.path.join(tmp, 'com_out'), 'COM', '--frames'])
views_ok = [l.split(']')[0][1:] for l in out.splitlines() if l.startswith('[') and not l.startswith('[texte]') and l.endswith('-> OK')]
ok('build demo (5 vues OK + texte)', code == 0 and len(views_ok) == 5 and ': 0 -> OK' in out, views_ok)

# 4. garde-fou : un script ne doit jamais ecrire hors de la base jetable
probe_ok = {
    'defaut_numerique.sql': 'CREATE TABLE t (id INT PRIMARY KEY, ratio DECIMAL(5,2) DEFAULT 1.5, note VARCHAR(20) DEFAULT \'a.b\');',
}
probe_bad = {
    'use.sql': 'CREATE DATABASE IF NOT EXISTS zz_probe_victim;\nUSE zz_probe_victim;\nCREATE TABLE t (id INT PRIMARY KEY);',
    'presse_papiers.sql': 'CREATE DATABASE IF NOT EXISTS demo;\nUSE demo;\n' + open(os.path.join(FIX, 'demo.sql'), encoding='utf-8').read(),
    'qualifie.sql': 'CREATE TABLE t (id INT PRIMARY KEY, u INT, FOREIGN KEY (u) REFERENCES autre_base.users(id));',
}
for name, sql in {**probe_ok, **probe_bad}.items():
    p = os.path.join(tmp, name)
    open(p, 'w', encoding='utf-8').write(sql)
    code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', p, '--out', os.path.join(tmp, name + '.json')])
    if name in probe_ok:
        ok(f'script legitime accepte : {name}', code == 0, out.strip().splitlines()[-1])
    else:
        ok(f'script dangereux refuse : {name}', code != 0 and 'script refuse' in out, out.strip().splitlines()[0][:90])
dump_sql = os.path.join(tmp, 'roundtrip.sql')
code, out = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', os.path.join(FIX, 'demo.sql'), '--out',
                 os.path.join(tmp, 'rt1.json'), '--sql-out', dump_sql])
code2, out2 = run([sys.executable, '-I', os.path.join(LIB, 'extract.py'), '--sql', dump_sql, '--out', os.path.join(tmp, 'rt2.json')])
a, b = (json.load(open(os.path.join(tmp, f), encoding='utf-8')) for f in ('rt1.json', 'rt2.json'))
ok('aller-retour : le SQL exporte (mysqldump) redonne exactement la meme structure', code == code2 == 0
   and a['tables'] == b['tables'] and a['relations'] == b['relations'], out2.strip().splitlines()[-1])

# 5. bac a sable : l'utilisateur jetable n'ecrit que dans sa base (base temoin zz_dbschema_victim)
code, out = run([sys.executable, '-I', os.path.join(HERE, 'sandbox_test.py'), LIB])
ok('bac a sable MySQL', code == 0, ' | '.join(l for l in out.splitlines() if 'ECHEC' in l) or '%d verifications' % out.count('[OK]'))

# 5b. constats de l'audit de securite (vol ou acces a des donnees)
code, out = run([sys.executable, '-I', os.path.join(HERE, 'security_test.py'), LIB, os.path.join(tmp, 'sec')])
ok('securite : non-regression de l\'audit', code == 0, ' | '.join(l for l in out.splitlines() if 'ECHEC' in l) or '%d verifications' % out.count('[OK]'))

# 6. aucune base ni utilisateur jetable restant
code, out = run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import extract; '
                 'print((extract.run("SHOW DATABASES LIKE \'zz_dbschema_%\'") + extract.run("SELECT user FROM mysql.user WHERE user LIKE \'zz_dbschema_%\'")).strip() or "aucune")', LIB])
ok('aucune base ni utilisateur zz_dbschema_ restant', out.strip() == 'aucune', out.strip())

print('\n%d echec(s)' % len(fails))
sys.exit(1 if fails else 0)
