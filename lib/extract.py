"""Structure d'une base MySQL -> model.json, lue dans information_schema (jamais de parsing SQL a la main).

  --sql FICHIER : execute le script dans une base jetable zz_dbschema_<ts>, lit, exporte le SQL (mysqldump), supprime la base.
  --db NOM      : lecture seule d'une base existante (structure + mysqldump --no-data, aucune ecriture).
  --laravel DIR : php artisan migrate vers une base jetable zz_dbschema_<ts> (DB_* forces par l'environnement, configuration
                  effective lue en JSON par php -r AVANT migrate ; refus si la config est en cache) ; tables du framework exclues (--keep-framework).
Options : --out model.json  --sql-out schema.sql  --groups groups.json
          --cards cards.json : cardinalites declarees, que le schema ne peut pas exprimer (ex. 1..N : "au moins un enfant").
                     {"table_enfant.colonne_fk": {"child": "1..N"}} ; "parent" : 1 | 0..1, "child" : 0..1 | 0..N | 1 | 1..N.
Binaire : DBSCHEMA_MYSQL_BIN (dossier contenant mysql.exe), sinon le dernier MySQL de Laragon. Utilisateur root sans mot de passe
par defaut (poste Laragon) ; DBSCHEMA_MYSQL_USER / DBSCHEMA_MYSQL_PASSWORD pour changer.
"""
import argparse, glob, json, os, re, secrets, shutil, subprocess, sys, time

PREFIX = 'zz_dbschema_'
FRAMEWORK = {'migrations', 'password_reset_tokens', 'password_resets', 'sessions', 'cache', 'cache_locks', 'jobs',
             'job_batches', 'failed_jobs', 'personal_access_tokens'}


def mysql_bin(name):
    base = os.environ.get('DBSCHEMA_MYSQL_BIN')
    if not base:
        cands = sorted(glob.glob(r'C:\laragon\bin\mysql\mysql-*\bin'))  # Laragon (Windows), sinon le PATH
        on_path = shutil.which(name)
        if not cands and not on_path:
            sys.exit('MySQL introuvable : definir DBSCHEMA_MYSQL_BIN')
        if not cands:
            return on_path
        base = cands[-1]
    exe = os.path.join(base, name + ('.exe' if os.name == 'nt' else ''))
    if not os.path.exists(exe):
        sys.exit('binaire absent : ' + exe)
    return exe


def auth(cred=None):
    if cred:  # utilisateur jetable du bac a sable
        return ['-u', cred[0], '-p' + cred[1], '-h', '127.0.0.1']
    a = ['-u', os.environ.get('DBSCHEMA_MYSQL_USER', 'root'), '-h', '127.0.0.1']
    if os.environ.get('DBSCHEMA_MYSQL_PASSWORD'):
        a.append('-p' + os.environ['DBSCHEMA_MYSQL_PASSWORD'])
    return a


def run(sql, db=None, stdin=None, binary=False, cred=None):
    cmd = [mysql_bin('mysql')] + auth(cred) + ['--default-character-set=utf8mb4', '-B', '-N', '--raw'] + (['--binary-mode'] if binary else [])
    if db:
        cmd.append(db)
    if sql is not None:
        cmd += ['-e', sql]
    r = subprocess.run(cmd, input=stdin, capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace').strip())
    return r.stdout.decode('utf-8')


DBNAME = re.compile(r'^[\w$-]{1,64}$')


def rows(select, db):
    if not DBNAME.match(db):
        sys.exit('nom de base refuse : %r (lettres, chiffres, _ $ - seulement)' % db)
    out = run(select.replace('{DB}', db))
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def read_model(db):
    tables = rows("""SELECT JSON_OBJECT('name',TABLE_NAME,'comment',TABLE_COMMENT) FROM information_schema.TABLES
                     WHERE TABLE_SCHEMA='{DB}' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME""", db)
    cols = rows("""SELECT JSON_OBJECT('table',TABLE_NAME,'name',COLUMN_NAME,'pos',ORDINAL_POSITION,'type',COLUMN_TYPE,
                     'nullable',IS_NULLABLE='YES','default',COLUMN_DEFAULT,'key',COLUMN_KEY,'extra',EXTRA,'comment',COLUMN_COMMENT)
                   FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='{DB}' ORDER BY TABLE_NAME,ORDINAL_POSITION""", db)
    stats = rows("""SELECT JSON_OBJECT('table',TABLE_NAME,'index',INDEX_NAME,'unique',NON_UNIQUE=0,'seq',SEQ_IN_INDEX,'column',COLUMN_NAME)
                    FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='{DB}' ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX""", db)
    kcu = rows("""SELECT JSON_OBJECT('name',k.CONSTRAINT_NAME,'table',k.TABLE_NAME,'column',k.COLUMN_NAME,'seq',k.ORDINAL_POSITION,
                    'ref_schema',k.REFERENCED_TABLE_SCHEMA,'ref_table',k.REFERENCED_TABLE_NAME,'ref_column',k.REFERENCED_COLUMN_NAME,'on_update',r.UPDATE_RULE,'on_delete',r.DELETE_RULE)
                  FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r
                    ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME AND r.TABLE_NAME=k.TABLE_NAME
                  WHERE k.TABLE_SCHEMA='{DB}' AND k.REFERENCED_TABLE_NAME IS NOT NULL
                  ORDER BY k.TABLE_NAME,k.CONSTRAINT_NAME,k.ORDINAL_POSITION""", db)

    model = {'tables': {}, 'relations': [], 'external_fks': []}
    for t in tables:
        model['tables'][t['name']] = {'name': t['name'], 'comment': t['comment'], 'columns': [], 'indexes': []}
    for c in cols:
        if c['table'] in model['tables']:
            model['tables'][c['table']]['columns'].append(
                {k: c[k] for k in ('name', 'type', 'nullable', 'default', 'extra', 'comment')} |
                {'pk': c['key'] == 'PRI', 'fk': False, 'unique': False})
    idx = {}
    for s in stats:
        idx.setdefault((s['table'], s['index']), {'name': s['index'], 'unique': bool(s['unique']), 'columns': []})['columns'].append(s['column'])
    for (t, _), i in idx.items():
        if t in model['tables']:
            model['tables'][t]['indexes'].append(i)
            if i['unique'] and len(i['columns']) == 1 and i['name'] != 'PRIMARY':
                for c in model['tables'][t]['columns']:
                    if c['name'] == i['columns'][0]:
                        c['unique'] = True
    fks = {}
    for k in kcu:
        if k['ref_schema'].lower() != db.lower():  # FK vers une autre base : rien a dessiner ici (sinon confondue avec une table homonyme)
            model['external_fks'].append('%s.%s -> %s.%s' % (k['table'], k['column'], k['ref_schema'], k['ref_table']))
            continue
        f = fks.setdefault((k['table'], k['name']), {'name': k['name'], 'from': k['table'], 'to': k['ref_table'],
                                                     'columns': [], 'ref_columns': [], 'on_update': k['on_update'], 'on_delete': k['on_delete']})
        f['columns'].append(k['column']); f['ref_columns'].append(k['ref_column'])
    for (t, _), f in fks.items():
        tcols = {c['name']: c for c in model['tables'][t]['columns']}
        for cn in f['columns']:
            tcols[cn]['fk'] = True
        mandatory = all(not tcols[cn]['nullable'] for cn in f['columns'])
        # Cote enfant <= 1 si un index UNIQUE (PK comprise) est inclus dans les colonnes de la FK
        one_child = any(i['unique'] and set(i['columns']) <= set(f['columns']) for i in model['tables'][t]['indexes'])
        f['card_parent'] = '1' if mandatory else '0..1'
        f['card_child'] = '0..1' if one_child else '0..N'
        model['relations'].append(f)
    return model


ALLOWED = re.compile(r'(CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|CREATE\s+(UNIQUE\s+|FULLTEXT\s+|SPATIAL\s+)?INDEX|SET\s|'
                     r'INSERT\s+INTO|LOCK\s+TABLES|UNLOCK\s+TABLES)', re.I)
ID = r'[\w$\u0080-￿]'
# nom qualifie base.table : identifiant (avec au moins un caractere non numerique, pour ne pas prendre 1.5) ou `...` ou "..."
QUALIFIED = re.compile(r'(`[^`]*`|""|(?<!%s)%s*[^\W\d]%s*)\s*\.\s*(`|"|%s)' % (ID, ID, ID, ID))
TOKENS = re.compile(r"""'(?:[^'\\]|\\.|'')*'|"(?:[^"\\]|\\.|"")*"|`(?:[^`]|``)*`|/\*!\d*(.*?)\*/|/\*.*?\*/|(?:--[ \t\r\n]|#)[^\n]*""", re.S)
SET_BAD = re.compile(r'\bSET\s+(GLOBAL|PERSIST|PERSIST_ONLY|PASSWORD|ROLE|DEFAULT\s+ROLE|RESOURCE\s+GROUP)\b|@@(GLOBAL|PERSIST)', re.I)
# modes qui changent la lecture des chaines et des guillemets : cherches dans le texte BRUT (la valeur est une chaine)
MODES_BAD = re.compile(r'\b(ANSI_QUOTES|NO_BACKSLASH_ESCAPES)\b|sql_mode\s*=[^;]*\bANSI\b', re.I)


def clean_sql(sql):
    """Chaines -> '' ou "", commentaires -> espace, /*!NNNNN ... */ -> son contenu (execute par MySQL), en UN passage."""
    def repl(m):
        t = m.group(0)
        if t[0] == "'":
            return "''"
        if t[0] == '"':
            return '""'
        if t[0] == '`':
            return t
        if t.startswith('/*!'):
            return ' ' + clean_sql(m.group(1)) + ' '
        return ' '
    return TOKENS.sub(repl, sql)


def check_script(sql):
    """Premier filtre, lisible : refuse USE, CREATE/DROP/ALTER DATABASE, noms base.table, SET GLOBAL/PERSIST/PASSWORD,
    modes SQL qui changent la lecture des chaines, commandes du client mysql, et toute instruction hors liste blanche."""
    s = clean_sql(sql)
    bad = []
    if MODES_BAD.search(sql):
        bad.append('mode SQL refuse (ANSI_QUOTES, NO_BACKSLASH_ESCAPES, ANSI) : ' + MODES_BAD.search(sql).group(0)[:40])
    if re.search(r'\\[A-Za-z!.?#]', s):
        bad.append('commande du client mysql (\\u, \\!, \\. ...) : ' + re.search(r'\\[A-Za-z!.?#].{0,30}', s).group(0))
    for st in (x.strip() for x in s.split(';')):
        if not st:
            continue
        st_q = re.sub(r'@@\w+\.', '@@', st)  # @@SESSION.var n'est pas un nom base.table
        if not ALLOWED.match(st):
            bad.append('instruction non autorisee : ' + st[:60])
        elif SET_BAD.search(st):
            bad.append('SET refuse : ' + st[:60])
        elif QUALIFIED.search(st_q):
            bad.append('nom prefixe par une base : ' + QUALIFIED.search(st_q).group(0) + ' dans ' + st[:50])
    if bad:
        sys.exit('script refuse (il pourrait ecrire hors de la base jetable) :\n  ' + '\n  '.join(bad[:10])
                 + '\nRetirer ces lignes (CREATE DATABASE / USE / base.table ...) puis relancer.')


HOSTS = ('127.0.0.1', 'localhost')


def sandbox_open(db):
    """Base jetable + utilisateur jetable du meme nom, qui n'a de droits QUE sur cette base (ni FILE, ni SUPER, ni autre base).
    C'est la frontiere de droits ; le filtre check_script n'est qu'un premier refus lisible."""
    assert db.startswith(PREFIX) and DBNAME.match(db)
    pw = 'Zz9' + secrets.token_urlsafe(18)
    esc_db = db.replace('_', '\\_')  # GRANT : _ est un joker dans un nom de base
    run('CREATE DATABASE `%s` CHARACTER SET utf8mb4' % db)
    for h in HOSTS:
        run("CREATE USER '%s'@'%s' IDENTIFIED BY '%s'" % (db, h, pw))
        run("GRANT ALL PRIVILEGES ON `%s`.* TO '%s'@'%s'" % (esc_db, db, h))
    return (db, pw)


def sandbox_close(db):
    errs = []
    for sql in ["DROP USER IF EXISTS '%s'@'%s'" % (db, h) for h in HOSTS] + ['DROP DATABASE IF EXISTS `%s`' % db]:
        try:
            run(sql)
        except RuntimeError as e:
            errs.append(str(e))
    if errs:
        print('ATTENTION nettoyage incomplet de %s : %s' % (db, errs), file=sys.stderr)


def snapshot():
    """Tables de toutes les bases hors zz_dbschema_ (creation, suppression, derniere modification) : detection d'une ecriture
    hors base jetable. Ne voit ni les changements de droits ni les variables serveur : ceux-la sont refuses en amont."""
    out = run("SET SESSION information_schema_stats_expiry=0; "
              "SELECT CONCAT(TABLE_SCHEMA,'.',TABLE_NAME,'|',IFNULL(CREATE_TIME,''),'|',IFNULL(UPDATE_TIME,'')) FROM information_schema.TABLES "
              "WHERE TABLE_SCHEMA NOT LIKE 'zz\\_dbschema\\_%' AND TABLE_SCHEMA NOT IN "
              "('information_schema','performance_schema','mysql','sys')")
    return set(out.split('\n')) - {''}


def dump(db, path):
    r = subprocess.run([mysql_bin('mysqldump')] + auth() + ['--no-data', '--skip-comments', '--skip-add-drop-table',
                        '--default-character-set=utf8mb4', db], capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace'))
    open(path, 'wb').write(r.stdout)


CONN = re.compile(r"""(?:Schema|DB)::connection\(\s*([^)]*)\)|->connection\(\s*([^)]*)\)|\$connection\s*=\s*([^;]+);""")
# toujours suspects dans une migration : autre connexion par methode, configuration modifiee, USE, nom base.table en chaine
CONN_ANY = re.compile(r"""function\s+getConnection(?:Name)?\s*\(|->setConnection\(|setDefaultConnection\(|DB::(?:purge|reconnect|disconnect|connectUsing|build|extend)\(|config\s*\(\s*\[|config\s*\(\s*\)\s*->\s*set\(|Config::set\(|::on\(|new\s+\\?PDO\b|['"]\s*USE\s+[`\w]|DB::table\(\s*['"][\w$]+\.""", re.I)


def foreign_connections(repo):
    """Migrations (repo et vendor) qui visent une autre connexion que 'mysql' : elles ecriraient hors de la base jetable."""
    bad = []
    for f in glob.glob(os.path.join(repo, '**', 'migrations', '**', '*.php'), recursive=True):
        for m in CONN.finditer(open(f, encoding='utf-8', errors='replace').read()):
            val = next(g for g in m.groups() if g is not None).strip()
            if val[:1] not in '\'"' or val.strip('\'"') != 'mysql':
                bad.append('%s : %s' % (os.path.relpath(f, repo), m.group(0)[:70]))
        for m in CONN_ANY.finditer(open(f, encoding='utf-8', errors='replace').read()):
            bad.append('%s : %s' % (os.path.relpath(f, repo), m.group(0)[:70]))
    return bad


def laravel_migrate(repo, db, cred):
    """migrate vers `db` uniquement. Toute incertitude sur la base cible = arret."""
    assert db.startswith(PREFIX)
    if not os.path.exists(os.path.join(repo, 'artisan')):
        sys.exit('pas de fichier artisan dans ' + repo)
    if os.path.exists(os.path.join(repo, 'bootstrap', 'cache', 'config.php')):
        sys.exit('config Laravel en cache (bootstrap/cache/config.php) : les variables DB_* seraient ignorees. Refus.')
    other = foreign_connections(repo)
    if other:
        sys.exit('migrations vers une autre connexion que mysql (elles ecriraient hors de la base jetable). Refus :\n  '
                 + '\n  '.join(other[:10]))
    user = cred[0]  # utilisateur jetable : aucun droit hors de la base jetable
    # DB_URL / DATABASE_URL vides : une URL dans .env ecraserait base et utilisateur (ConfigurationUrlParser)
    env = dict(os.environ, DB_CONNECTION='mysql', DB_HOST='127.0.0.1', DB_PORT='3306', DB_DATABASE=db, DB_URL='', DATABASE_URL='',
               DB_USERNAME=user, DB_PASSWORD=cred[1])
    ansi = lambda t: re.sub(r'\x1b\[[0-9;]*m', '', t)
    # configuration EFFECTIVE (celle que migrate utilisera), lue en JSON par le meme amorcage qu'artisan
    php = ("require 'vendor/autoload.php'; $a = require 'bootstrap/app.php'; "
           "$a->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); "
           "echo PHP_EOL, json_encode(['default' => config('database.default'), 'mysql' => config('database.connections.mysql')]);")
    r = subprocess.run(['php', '-r', php], cwd=repo, env=env, capture_output=True, text=True)
    try:
        cfg = json.loads(r.stdout.strip().splitlines()[-1])
        c = cfg['mysql']
        c.pop('password', None)
        ok = (cfg['default'] == 'mysql' and c.get('database') == db and c.get('username') == user and not c.get('url')
              and c.get('host') in ('127.0.0.1', 'localhost') and 'read' not in c and 'write' not in c)
    except Exception:
        ok, cfg = False, ansi(r.stdout + r.stderr)[-1500:]
    if not ok:
        sys.exit('configuration Laravel non confirmee avant migrate (attendu : connexion mysql, base %s, utilisateur %s, '
                 'pas d\'url ni de read/write) :\n%s' % (db, user, cfg))
    r = subprocess.run(['php', 'artisan', 'migrate', '--force', '--no-interaction', '--database=mysql'], cwd=repo, env=env,
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('php artisan migrate a echoue :\n' + ansi(r.stdout + r.stderr)[-3000:])


def declare_cards(model, decl):
    allowed = {'parent': {'1', '0..1'}, 'child': {'0..1', '0..N', '1', '1..N'}}
    def find(key):
        hits = [r for r in model['relations'] if r['name'] == key or r['from'] + '.' + r['columns'][0] == key]
        if len(hits) != 1:
            sys.exit('--cards : %s designe %d FK (cle attendue : nom de contrainte ou table_enfant.colonne_fk, sans ambiguite)'
                     % (key, len(hits)))
        return hits[0]
    for key, d in decl.items():
        if not isinstance(d, dict) or not d:
            sys.exit('--cards %s : valeur attendue {"child": "...", "parent": "..."}' % key)
        r = find(key)
        for side, v in d.items():
            if side not in allowed or v not in allowed[side]:
                sys.exit('--cards %s : %s=%s invalide (parent : 1 | 0..1 ; child : 0..1 | 0..N | 1 | 1..N)' % (key, side, v))
            r['card_' + side] = v
        r['declared'] = sorted(d)


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--sql'); src.add_argument('--db'); src.add_argument('--laravel')
    ap.add_argument('--keep-framework', action='store_true')
    ap.add_argument('--out', required=True); ap.add_argument('--sql-out'); ap.add_argument('--groups'); ap.add_argument('--cards')
    a = ap.parse_args()

    if a.db:
        model = read_model(a.db); model['source'] = {'kind': 'db', 'name': a.db}
        if not model['tables']:
            sys.exit('base %s inexistante ou sans table' % a.db)
        if a.sql_out:
            dump(a.db, a.sql_out)
    else:
        db = PREFIX + time.strftime('%Y%m%d%H%M%S') + secrets.token_hex(2)
        assert db.startswith(PREFIX)
        if a.sql:
            check_script(open(a.sql, encoding='utf-8', errors='replace').read())
        before = snapshot()
        try:
            cred = sandbox_open(db)
            if a.sql:
                # utilisateur jetable + --binary-mode (commandes du client mysql inertes)
                run(None, db=db, stdin=open(a.sql, 'rb').read(), binary=True, cred=cred)
            else:
                laravel_migrate(os.path.abspath(a.laravel), db, cred)
                if not a.keep_framework:
                    for t in FRAMEWORK:
                        run('DROP TABLE IF EXISTS `%s`' % t, db=db)
            model = read_model(db)
            if not model['tables']:
                sys.exit('aucune table creee dans %s : le script contient-il un USE vers une autre base ?' % db)
            if a.sql_out:
                dump(db, a.sql_out)
        finally:
            sandbox_close(db)
            after = snapshot()
            if after != before:
                print('ATTENTION : des tables HORS base jetable ont change pendant l\'extraction :', file=sys.stderr)
                for x in sorted(after ^ before)[:20]:
                    print('  ' + ('+ ' if x in after else '- ') + x, file=sys.stderr)
                sys.exit(3)
        model['source'] = ({'kind': 'sql', 'name': os.path.basename(a.sql)} if a.sql
                           else {'kind': 'laravel', 'name': os.path.abspath(a.laravel)})
    model['groups'] = json.load(open(a.groups, encoding='utf-8')) if a.groups else {}
    unknown = [t for ts in model['groups'].values() for t in ts if t not in model['tables']]
    if unknown:
        sys.exit('groupes : tables inconnues ' + ', '.join(unknown))
    if a.cards:
        declare_cards(model, json.load(open(a.cards, encoding='utf-8')))
    for x in model['external_fks']:
        print('FK vers une autre base, non dessinee : ' + x, file=sys.stderr)
    json.dump(model, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('tables=%d colonnes=%d relations=%d groupes=%d' % (len(model['tables']), sum(len(t['columns']) for t in model['tables'].values()),
                                                             len(model['relations']), len(model['groups'])))


if __name__ == '__main__':
    main()
