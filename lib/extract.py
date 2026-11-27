"""Structure d'une base MySQL -> model.json, lue dans information_schema (jamais de parsing SQL a la main).

  --sql FICHIER : execute le script dans une base jetable zz_dbschema_<ts>, lit, exporte le SQL (mysqldump), supprime la base.
  --db NOM      : lecture seule d'une base existante (structure + mysqldump --no-data, aucune ecriture).
  --laravel DIR : php artisan migrate vers une base jetable zz_dbschema_<ts>. EXECUTE LE CODE PHP DU DEPOT avec les droits de
                  l'utilisateur : exige --trust-repo (depot de confiance uniquement). Environnement minimal (aucun secret transmis),
                  configuration effective lue en JSON AVANT migrate ; tables du framework exclues (--keep-framework).
Options : --out model.json  --sql-out schema.sql  --groups groups.json
          --cards cards.json : cardinalites declarees, que le schema ne peut pas exprimer (ex. 1..N : "au moins un enfant").
                     {"table_enfant.colonne_fk": {"child": "1..N"}} ; "parent" : 1 | 0..1, "child" : 0..1 | 0..N | 1 | 1..N.
Binaire : DBSCHEMA_MYSQL_BIN (dossier contenant mysql), sinon l'unique MySQL/MariaDB de Laragon, XAMPP, WAMP ou MAMP (plusieurs :
refus), sinon le PATH. Serveur : DBSCHEMA_MYSQL_HOST (127.0.0.1) et DBSCHEMA_MYSQL_PORT (3306), en TCP ; --sql et --laravel : hote local
seulement. Utilisateur root sans mot de passe par defaut ; DBSCHEMA_MYSQL_USER / DBSCHEMA_MYSQL_PASSWORD pour changer. Les identifiants
passent par un fichier d'options temporaire (--defaults-file : ni ligne de commande, ni my.ini du serveur, local-infile=0).
"""
import argparse, functools, glob, json, os, re, secrets, shutil, subprocess, sys, tempfile, time

PREFIX = 'zz_dbschema_'
FRAMEWORK = {'migrations', 'password_reset_tokens', 'password_resets', 'sessions', 'cache', 'cache_locks', 'jobs',
             'job_batches', 'failed_jobs', 'personal_access_tokens'}
# installations connues (Laragon, XAMPP, WAMP, MAMP) ; ailleurs (Linux, Homebrew, Docker) : le PATH
STACKS = [r'C:\laragon\bin\mysql\mysql-*\bin', r'C:\laragon\bin\mysql\mariadb-*\bin', r'C:\xampp\mysql\bin',
          r'C:\wamp64\bin\mysql\*\bin', r'C:\wamp64\bin\mariadb\*\bin', r'C:\wamp\bin\mysql\*\bin', r'C:\wamp\bin\mariadb\*\bin',
          '/Applications/MAMP/Library/bin']
ALIAS = {'mysql': 'mariadb', 'mysqldump': 'mariadb-dump'}  # MariaDB 11 : noms mysql* absents ou obsoletes
EXE = '.exe' if os.name == 'nt' else ''
LOCAL = ('127.0.0.1', 'localhost', '::1')


def mysql_bin(name):
    names = (name, ALIAS[name])
    found = lambda d: next((os.path.join(d, n + EXE) for n in names if os.path.isfile(os.path.join(d, n + EXE))), None)
    base = os.environ.get('DBSCHEMA_MYSQL_BIN')
    if base:
        exe = found(base)
        if not exe:
            sys.exit('binaire absent : %s dans %s' % (' ou '.join(names), base))
        return exe
    cands = sorted({d for p in STACKS for d in glob.glob(p) if found(d)})
    if len(cands) > 1:
        sys.exit('plusieurs MySQL/MariaDB installes (%s) : choisir avec DBSCHEMA_MYSQL_BIN' % ', '.join(cands))
    if cands:
        return found(cands[0])
    on_path = shutil.which(name) or shutil.which(ALIAS[name])
    if not on_path:
        sys.exit('MySQL/MariaDB introuvable (%s) : definir DBSCHEMA_MYSQL_BIN' % ' ou '.join(names))
    return on_path


def conn():
    host, port = os.environ.get('DBSCHEMA_MYSQL_HOST', '127.0.0.1'), os.environ.get('DBSCHEMA_MYSQL_PORT', '3306')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,255}', host) or not re.fullmatch(r'[0-9]{1,5}', port) or not 0 < int(port) < 65536:
        sys.exit('DBSCHEMA_MYSQL_HOST / DBSCHEMA_MYSQL_PORT invalides : %r %r' % (host, port))
    return host, port


def client(name, cred=None, extra=()):
    """Lance un client MySQL avec un fichier d'options temporaire (1er argument --defaults-file : aucun my.ini lu, mot de passe
    absent de la ligne de commande et de la liste des processus). Renvoie (commande, chemin a supprimer)."""
    exe = mysql_bin(name)  # AVANT le fichier : un refus (binaire absent, plusieurs versions) ne laisse aucun mot de passe sur disque
    host, port = conn()
    user, pw = cred if cred else (os.environ.get('DBSCHEMA_MYSQL_USER', 'root'), os.environ.get('DBSCHEMA_MYSQL_PASSWORD', ''))
    if any(c in v for v in (user, pw) for c in '\r\n'):
        sys.exit('DBSCHEMA_MYSQL_USER / DBSCHEMA_MYSQL_PASSWORD : retour a la ligne refuse')
    q = lambda v: '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'  # valeur entre guillemets : # et \ litteraux
    fd, path = tempfile.mkstemp(prefix='dbschema_', suffix='.cnf')
    lines = ['[client]', 'user=' + q(user), 'host=' + q(host), 'port=' + port, 'protocol=TCP',
             'default-character-set=utf8mb4'] + (['password=' + q(pw)] if pw else [])
    if name == 'mysql':
        lines.append('local-infile=0')
    lines += list(extra)  # options propres au client (fichier UTF-8 : les noms non ASCII y passent intacts, pas la ligne de commande)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return [exe, '--defaults-file=' + path], path


def run(sql, db=None, stdin=None, binary=False, cred=None):
    cmd, cnf = client('mysql', cred)
    cmd += ['-B', '-N', '--raw'] + (['--binary-mode'] if binary else [])
    if db:
        cmd.append(db)
    if sql is not None:
        cmd += ['-e', sql]
    try:
        r = subprocess.run(cmd, input=stdin, capture_output=True)
    finally:
        os.remove(cnf)
    if r.returncode:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace').strip())
    return r.stdout.decode('utf-8')


@functools.lru_cache(None)
def server():
    """('mariadb' | 'mysql', (majeure, mineure), noms sensibles a la casse ?) : VERSION() et @@lower_case_table_names."""
    v, lctn = (run('SELECT VERSION(), @@lower_case_table_names').strip().split('\t') + ['1'])[:2]
    m = re.match(r'(\d+)\.(\d+)', v)
    return ('mariadb' if 'mariadb' in v.lower() else 'mysql', (int(m.group(1)), int(m.group(2))) if m else (0, 0), lctn.strip() == '0')


def maria_default(d):
    """MariaDB ecrit COLUMN_DEFAULT en SQL : 'texte' entre quotes, NULL en toutes lettres ; MySQL donne la valeur brute."""
    if d == 'NULL':
        return None
    if d and len(d) >= 2 and d[0] == d[-1] == "'":
        return d[1:-1].replace("''", "'")
    return d


DBNAME = re.compile(r'^[\w$-]{1,64}\Z')  # \Z et non $ : $ accepte un \n final
CTRL = re.compile('[\x00-\x1f\x7f\x85\u2028\u2029]')


def jetable(db):
    """Garde-fou des ecritures : base et compte zz_dbschema_* seulement. Pas d'assert (retire par python -O)."""
    if not (db.startswith(PREFIX) and DBNAME.match(db)):
        sys.exit('garde-fou : %r n\'est pas une base jetable %s*' % (db, PREFIX))


def rows(select, db):
    if not DBNAME.match(db):
        sys.exit('nom de base refuse : %r (lettres, chiffres, _ $ - seulement)' % db)
    out = run(select.replace('{DB}', db))
    return [json.loads(l) for l in out.split('\n') if l.strip()]


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

    ctrl = [n for t in tables for n in [t['name']]] + [c['name'] for c in cols] + [s['index'] for s in stats] + [k['name'] for k in kcu]
    bad = sorted({repr(n) for n in ctrl if CTRL.search(n or '')})
    if bad:
        sys.exit('noms refuses (caracteres de controle : retour a la ligne, tabulation...) : ' + ', '.join(bad[:10]))
    if server()[0] == 'mariadb':
        for c in cols:
            c['default'] = maria_default(c['default'])
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
        # FK vers une autre base : rien a dessiner ici. Serveur sensible a la casse (Linux, lower_case_table_names=0) : « Shop »
        # et « shop » sont deux bases (verifie sur MySQL 8.4 : la FK passait pour interne, vers une table absente -> crash ELK).
        # Serveur insensible (Windows : 1 ; macOS : 2, ou InnoDB range les noms references en minuscules) : la table referencee est
        # retrouvee sans tenir compte de la casse et prend le nom du modele (sinon une FK interne passait pour externe).
        sensitive = server()[2]
        same = k['ref_schema'] == db if sensitive else k['ref_schema'].lower() == db.lower()
        to = k['ref_table'] if sensitive else next((t for t in model['tables'] if t.lower() == k['ref_table'].lower()), None)
        if not same or to not in model['tables']:
            model['external_fks'].append('%s.%s -> %s.%s' % (k['table'], k['column'], k['ref_schema'], k['ref_table']))
            continue
        f = fks.setdefault((k['table'], k['name']), {'name': k['name'], 'from': k['table'], 'to': to,
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
                     r'INSERT\s+INTO|LOCK\s+TABLES|UNLOCK\s+TABLES|START\s+TRANSACTION\b|'
                     # seuls : BEGIN NOT ATOMIC (MariaDB) ouvrirait un bloc compose qui execute n'importe quoi
                     r'(BEGIN|COMMIT|ROLLBACK)(\s+WORK)?\s*\Z)', re.I)
# tables qui lisent ou ecrivent HORS de la base jetable : moteurs relais (autre serveur, fichiers), chemins de stockage.
# Teste sur le texte NETTOYE (chaines -> '' ou "") : un moteur ecrit en chaine (ENGINE='FEDERATED') ou entre backticks est
# refuse d'office ; CONNECTION refuse avec ou sans = (grammaire : CONNECTION [=] 'texte'). Releve par la relecture du 2026-11-18.
# (?<![@.]) : @engine, @connection (variables) et t.engine ne sont pas des options de table.
# _utf8mb4'...', N'...' et ` FEDERATED` : refuses par MySQL 8.4 (2026-11-18), MariaDB non verifie -> refuses ici aussi
STORAGE_BAD = re.compile(r"(?<![@.])\bENGINE\s*=?\s*(`?\s*(FEDERATED|FEDERATEDX|CONNECT|SPIDER|S3|OQGRAPH)\b|(_\w+\s*|N)?(''|\"\"))|"
                         r"(?<![@.])\bCONNECTION\s*(=|''|\"\")|\b(DATA|INDEX)\s+DIRECTORY\b|\bFILE_NAME\s*=", re.I)
ID = r'[\w$\u0080-￿]'
# nom qualifie base.table : identifiant (avec au moins un caractere non numerique, pour ne pas prendre 1.5) ou `...` ou "..."
QUALIFIED = re.compile(r'(`[^`]*`|""|(?<!%s)%s*[^\W\d]%s*)\s*\.\s*(`|"|%s)' % (ID, ID, ID, ID))
TOKENS = re.compile(r"""'(?:[^'\\]|\\.|'')*'|"(?:[^"\\]|\\.|"")*"|`(?:[^`]|``)*`|/\*M?!\d*(.*?)\*/|/\*.*?\*/|(?:--(?=[\x00-\x20]|\Z)|#)[^\n]*""", re.S)
# -- suivi d'un blanc OU de tout caractere de controle (\v, \f, \x01... : MySQL les traite comme le blanc requis) ou de la fin :
# le caractere est REGARDE, pas consomme. Consomme, un "--" en fin de ligne avalait la ligne suivante (vue comme commentaire
# par le filtre, executee par MySQL : "--\nUSE prod;" passait le filtre ; trouve le 2026-11-18, \v et \f par la relecture)
SET_BAD = re.compile(r'\bSET\s+(GLOBAL|PERSIST|PERSIST_ONLY|PASSWORD|ROLE|DEFAULT\s+ROLE|RESOURCE\s+GROUP)\b|@@(GLOBAL|PERSIST)', re.I)
# modes qui changent la lecture des chaines et des guillemets : cherches dans le texte BRUT (la valeur est une chaine)
MODES_BAD = re.compile(r'\b(ANSI_QUOTES|NO_BACKSLASH_ESCAPES)\b|sql_mode\s*=[^;]*\bANSI\b|\b(big5|cp932|gbk|gb18030|sjis)\b', re.I)


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
        if t.startswith(('/*!', '/*M!')):  # /*M! : commentaire executable de MariaDB
            # MySQL accepte un commentaire IMBRIQUE dans un commentaire executable (/*! SET /**/ GLOBAL x=1 */ s'execute en
            # entier, verifie sur 8.4) : le contenu ne s'arrete pas au 1er */. Lecture ambigue -> refus (trouve par le fuzz).
            # Idem pour une chaine ouverte : le serveur lit la chaine, donc un */ qu'elle contient ne ferme pas le commentaire.
            body = m.group(1)
            if t.startswith('/*M!') and re.fullmatch(r'\s*\\-\s*enable the sandbox mode\s*', body):
                return ' '  # 1re ligne de mariadb-dump : passe le client en mode restreint (inoffensif)
            if '/*' in body or any(body.count(q) % 2 for q in '\'"`'):
                sys.exit('script refuse : commentaire executable ambigu (commentaire imbrique ou chaine ouverte) : ' + t[:60])
            return ' ' + clean_sql(body) + ' '
        return ' '
    return TOKENS.sub(repl, sql)


def check_script(sql):
    """Premier filtre, lisible : refuse USE, CREATE/DROP/ALTER DATABASE, noms base.table, SET GLOBAL/PERSIST/PASSWORD,
    modes SQL qui changent la lecture des chaines, commandes du client mysql, et toute instruction hors liste blanche."""
    s = clean_sql(sql)
    bad = []
    if MODES_BAD.search(sql):
        bad.append('mode SQL ou jeu de caracteres refuse (ANSI_QUOTES, NO_BACKSLASH_ESCAPES, ANSI, gbk/big5/sjis/cp932/gb18030) : '
                   + MODES_BAD.search(sql).group(0)[:40])
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
        elif STORAGE_BAD.search(st):
            bad.append('stockage hors de la base (moteur relais, CONNECTION, DATA/INDEX DIRECTORY ; une colonne nommee engine ou '
                       'connection affectee par = est aussi refusee : la renommer ou l\'ecrire entre backticks) : '
                       + STORAGE_BAD.search(st).group(0)[:40])
        elif QUALIFIED.search(st_q):
            bad.append('nom prefixe par une base : ' + QUALIFIED.search(st_q).group(0) + ' dans ' + st[:50])
    if bad:
        sys.exit('script refuse (il pourrait ecrire hors de la base jetable) :\n  ' + '\n  '.join(bad[:10])
                 + '\nRetirer ces lignes (CREATE DATABASE / USE / base.table ...) puis relancer.')


HOST = re.compile(r'[A-Za-z0-9_.:%-]{1,255}')  # hotes de mysql.user (suppression des comptes zz_dbschema_ seulement)
SEEN = re.compile(r'[A-Za-z0-9.:-]{1,255}')  # hote client vu par le serveur : ni % ni _ (jokers d'un compte MySQL)


def sandbox_hosts():
    """127.0.0.1, localhost et l'hote client tel que le serveur le voit (Docker : 172.17.0.1 ...)."""
    seen = run("SELECT SUBSTRING_INDEX(USER(),'@',-1)").strip()
    return sorted({'127.0.0.1', 'localhost'} | ({seen} if SEEN.fullmatch(seen) else set()))


def sandbox_open(db):
    """Base jetable + utilisateur jetable du meme nom, qui n'a de droits QUE sur cette base (ni FILE, ni SUPER, ni autre base).
    C'est la frontiere de droits ; le filtre check_script n'est qu'un premier refus lisible."""
    jetable(db)
    pw = 'Zz9' + secrets.token_urlsafe(18)
    esc_db = db.replace('_', '\\_')  # GRANT : _ est un joker dans un nom de base
    run('CREATE DATABASE `%s` CHARACTER SET utf8mb4' % db)
    for h in sandbox_hosts():
        run(None, stdin=("CREATE USER '%s'@'%s' IDENTIFIED BY '%s';" % (db, h, pw)).encode())
        run("GRANT ALL PRIVILEGES ON `%s`.* TO '%s'@'%s'" % (esc_db, db, h))
    return (db, pw)


def sandbox_close(db):
    jetable(db)
    errs = []
    try:  # tous les hotes du compte, tels qu'enregistres
        q = "SELECT host FROM mysql.user WHERE user='%s'" % db  # nosec B608 : db valide par jetable()
        hosts = [h for h in run(q).splitlines() if HOST.fullmatch(h)]  # \r\n sous Windows
    except RuntimeError as e:
        errs.append(str(e))
        hosts = ['127.0.0.1', 'localhost']
    for sql in ["DROP USER IF EXISTS '%s'@'%s'" % (db, h) for h in hosts] + ['DROP DATABASE IF EXISTS `%s`' % db]:
        try:
            run(sql)
        except RuntimeError as e:
            errs.append(str(e))
    if errs:
        print('ATTENTION nettoyage incomplet de %s : %s' % (db, errs), file=sys.stderr)


def cleanup_stale(max_age=3600):
    """Un arret brutal (processus tue) saute le finally : comptes et bases zz_dbschema_<horodatage> de plus d'une heure supprimes."""
    names = set(run("SELECT user FROM mysql.user WHERE user LIKE 'zz\\_dbschema\\_%'").split()) | \
        set(run("SHOW DATABASES LIKE 'zz\\_dbschema\\_%'").split())
    for n in sorted(names):
        m = re.fullmatch(re.escape(PREFIX) + r'(\d{14})[0-9a-f]*', n)
        try:
            old = m and time.time() - time.mktime(time.strptime(m.group(1), '%Y%m%d%H%M%S')) > max_age
        except ValueError:
            continue
        if old:
            print('nettoyage d\'un reste d\'execution interrompue : ' + n, file=sys.stderr)
            sandbox_close(n)


def non_tables(db):
    """Vues, routines, evenements, triggers : ['vue <nom>', ...]. Lus en JSON : un nom avec retour a la ligne reste entier
    (en texte brut il etait coupe, la vue echappait a l'exclusion de dump()). Appele aussi pour --db : nom valide par rows()."""
    return ['%s %s' % (x[0], x[1]) for x in rows(  # nosec B608 : {DB} valide par DBNAME dans rows()
        "SELECT JSON_ARRAY(kind, name) FROM ("
        "SELECT 'vue' kind, TABLE_NAME name FROM information_schema.VIEWS WHERE TABLE_SCHEMA='{DB}' UNION ALL "
        "SELECT 'routine', ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='{DB}' UNION ALL "
        "SELECT 'evenement', EVENT_NAME FROM information_schema.EVENTS WHERE EVENT_SCHEMA='{DB}' UNION ALL "
        "SELECT 'trigger', TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='{DB}') x", db)]


def snapshot():
    """Tables de toutes les bases hors zz_dbschema_ (creation, suppression, derniere modification) : detection d'une ecriture
    hors base jetable. Ne voit ni les changements de droits ni les variables serveur : ceux-la sont refuses en amont."""
    fresh = 'SET SESSION information_schema_stats_expiry=0; ' if server()[0] == 'mysql' and server()[1] >= (8, 0) else ''  # cache MySQL 8 seulement
    out = run(fresh + "SELECT JSON_ARRAY(CONCAT(TABLE_SCHEMA,"  # nosec B608 : texte fixe, aucune donnee interpolee
              "'.',TABLE_NAME),IFNULL(CREATE_TIME,''),IFNULL(UPDATE_TIME,'')) FROM information_schema.TABLES "
              "WHERE TABLE_SCHEMA NOT LIKE 'zz\\_dbschema\\_%' AND TABLE_SCHEMA NOT IN "
              "('information_schema','performance_schema','mysql','sys')")
    return {t: (c, u) for t, c, u in (json.loads(x) for x in out.split('\n') if x.strip())}


def snapshot_diff(before, after):
    """(structure, contenu) : tables creees, supprimees ou recreees (CREATE_TIME) = ecart bloquant ; UPDATE_TIME seul =
    ecriture de donnees, souvent une autre application du poste (avertissement, pas d'echec)."""
    struct = sorted(['+ ' + t for t in after.keys() - before.keys()] + ['- ' + t for t in before.keys() - after.keys()]
                    + ['~ ' + t for t in before.keys() & after.keys() if before[t][0] != after[t][0]])
    data = sorted(t for t in before.keys() & after.keys() if before[t][0] == after[t][0] and before[t][1] != after[t][1])
    return struct, data


def dump_version(out, exe):
    """('mariadb' | 'mysql', version majeure) d'apres la sortie --version. 5.7 : 'Ver 10.13 Distrib 5.7.x' ; 8+ : 'Ver 8.4.3' ;
    MariaDB : '... Distrib 10.6.x-MariaDB' ou 'mariadb-dump from 11.4.4-MariaDB'."""
    m = re.search(r'Distrib (\d+)', out) or re.search(r'(?:Ver|from) (\d+)', out)
    return ('mariadb' if 'mariadb' in (out + os.path.basename(exe)).lower() else 'mysql', int(m.group(1)) if m else 0)


def dump_client(exe):
    return dump_version(subprocess.run([exe, '--no-defaults', '--version'], capture_output=True, text=True).stdout, exe)


def dump(db, path):
    # vues exclues (tables seules) ; leurs noms passent par le fichier d'options, en UTF-8
    views = [x.split(' ', 1)[1] for x in non_tables(db) if x.startswith('vue ')]
    bad = [repr(v) for v in views if CTRL.search(v)]
    if bad:  # une vue que l'on ne peut pas nommer dans ignore-table finirait dans le SQL exporte
        sys.exit('noms de vues refuses (caracteres de controle) : ' + ', '.join(bad[:10]))
    ign =['[mysqldump]'] + ['ignore-table="%s.%s"' % (db, v.replace('\\', '\\\\').replace('"', '\\"')) for v in views]
    # --skip-lock-tables : ni droit LOCK TABLES ni verrou ; --no-tablespaces : pas de droit PROCESS (MySQL 8.0.21+) -> un compte
    # en SELECT seul suffit pour --db (serveur distant)
    opts = ['--no-data', '--skip-comments', '--skip-add-drop-table', '--skip-triggers', '--skip-lock-tables', '--no-tablespaces']
    flavor, major = dump_client(mysql_bin('mysqldump'))
    if flavor == 'mysql':  # options inconnues du mysqldump de MariaDB
        opts.append('--set-gtid-purged=OFF')
        if major >= 8 and not (server()[0] == 'mysql' and server()[1] >= (8, 0)):
            opts.append('--column-statistics=0')  # COLUMN_STATISTICS absent de MariaDB et MySQL 5.7
    cmd, cnf = client('mysqldump', extra=ign)
    try:
        r = subprocess.run(cmd + opts + [db], capture_output=True)
    finally:
        os.remove(cnf)
    if r.returncode:
        raise RuntimeError(r.stderr.decode('utf-8', 'replace'))
    # ni volumes (AUTO_INCREMENT=N, ligne des options de table seulement) dans un SQL destine a etre partage
    out = re.sub(rb'(?m)^(\) [^\n]*?) AUTO_INCREMENT=\d+', rb'\1', r.stdout)
    open(path, 'wb').write(out)


CONN = re.compile(r"""(?:Schema|DB)::connection\(\s*([^)]*)\)|->connection\(\s*([^)]*)\)|\$connection\s*=\s*([^;]+);""")
# toujours suspects dans une migration : autre connexion par methode, configuration modifiee, USE, nom base.table en chaine
CONN_ANY = re.compile(r"""function\s+getConnection(?:Name)?\s*\(|->\s*(?:connection|\{\s*['"]connection['"]\s*\})\s*(?:\?\?|\.)?=(?!=)|->setConnection\(|setDefaultConnection\(|DB::(?:purge|reconnect|disconnect|connectUsing|build|extend)\(|config\s*\(\s*\[|config\s*\(\s*\)\s*->\s*set\(|Config::set\(|::on\(|new\s+\\?PDO\b|['"]\s*USE\s+[`\w]|DB::table\(\s*['"][\w$]+\.""", re.I)
# motifs qui ne relevent QUE de getConnection() (ex. laravel/telescope) : la connexion est resolue au demarrage de Laravel
GETCONN = re.compile(r"""^(?:function\s+getConnection\s*\(|(?:Schema|DB)::connection\(\s*\$this->getConnection\(\))$""", re.I)
# CONN s'arrete au 1er ')' : dans ces fichiers, chaque appel connection( doit etre EXACTEMENT connection($this->getConnection())
CALL = re.compile(r"""(?:(?:Schema|DB)::|->)connection\s*\(""", re.I)
EXACT = re.compile(r"""(?:(?:Schema|DB)::|->)connection\s*\(\s*\$this->getConnection\(\)\s*\)""", re.I)


def foreign_connections(repo):
    """Migrations (repo et vendor) qui visent une autre connexion que 'mysql' : elles ecriraient hors de la base jetable."""
    bad = []
    # Dossiers migrations en toute casse et sur tout OS (loadMigrationsFrom(__DIR__.'/Migrations')), sauf le code du
    # framework (vendor/laravel/framework/src/Illuminate) : sous Windows et macOS l'ancien glob prenait
    # Illuminate/Database/Migrations/ (Migrator, getConnection) pour des migrations et refusait tout Laravel neuf (2026-11-27).
    files = []
    for d, _, names in os.walk(repo, followlinks=True):
        parts = [p.lower() for p in os.path.relpath(d, repo).split(os.sep)]
        if 'migrations' in parts and parts[:5] != ['vendor', 'laravel', 'framework', 'src', 'illuminate']:
            files += [os.path.join(d, n) for n in names if n.lower().endswith('.php')]
    for f in files:
        for m in CONN.finditer(open(f, encoding='utf-8', errors='replace').read()):
            val = next(g for g in m.groups() if g is not None).strip()
            if val[:1] not in '\'"' or val.strip('\'"') != 'mysql':
                bad.append('%s : %s' % (os.path.relpath(f, repo), m.group(0)[:70]))
        for m in CONN_ANY.finditer(open(f, encoding='utf-8', errors='replace').read()):
            bad.append('%s : %s' % (os.path.relpath(f, repo), m.group(0)[:70]))
    return bad


def laravel_migrate(repo, db, cred):
    """migrate vers `db` uniquement. Toute incertitude sur la base cible = arret."""
    jetable(db)
    if not os.path.exists(os.path.join(repo, 'artisan')):
        sys.exit('pas de fichier artisan dans ' + repo)
    if os.path.exists(os.path.join(repo, 'bootstrap', 'cache', 'config.php')):
        sys.exit('config Laravel en cache (bootstrap/cache/config.php) : les variables DB_* seraient ignorees. Refus.')
    other = [e.split(' : ', 1) for e in foreign_connections(repo)]
    hard = {f for f, motif in other if not GETCONN.match(motif)}
    for f in {f for f, _ in other} - hard:
        t = open(os.path.join(repo, f), encoding='utf-8', errors='replace').read()
        if len(CALL.findall(t)) != len(EXACT.findall(t)):
            hard.add(f)
    if hard:
        sys.exit('migrations vers une autre connexion que mysql (elles ecriraient hors de la base jetable). Refus :\n  '
                 + '\n  '.join([f + ' : ' + motif for f, motif in other if f in hard][:10]))
    # fichiers dont tous les motifs relevent de getConnection() : valeur demandee a Laravel, mysql ou null (defaut) exige
    resolve = sorted({f for f, _ in other})
    user = cred[0]  # utilisateur jetable : aucun droit hors de la base jetable
    # DB_URL / DATABASE_URL vides : une URL dans .env ecraserait base et utilisateur (ConfigurationUrlParser)
    # environnement MINIMAL : le code du depot ne recoit ni DBSCHEMA_MYSQL_PASSWORD ni aucun jeton de la session
    keep = ('PATH', 'PATHEXT', 'SYSTEMROOT', 'SystemRoot', 'WINDIR', 'COMSPEC', 'ComSpec', 'TEMP', 'TMP', 'HOME', 'USERPROFILE',
            'APPDATA', 'LOCALAPPDATA', 'COMPOSER_HOME', 'LANG')
    env = {k: os.environ[k] for k in keep if k in os.environ}
    host, port = conn()
    host = '127.0.0.1' if host == 'localhost' else host  # PDO + localhost = socket Unix, pas le serveur joint en TCP par le skill
    env.update(DB_CONNECTION='mysql', DB_HOST=host, DB_PORT=port, DB_DATABASE=db, DB_URL='', DATABASE_URL='', DB_SOCKET='',
               DB_USERNAME=user, DB_PASSWORD=cred[1])
    ansi = lambda t: re.sub(r'\x1b\[[0-9;]*m', '', t)
    # configuration EFFECTIVE (celle que migrate utilisera), lue en JSON par le meme amorcage qu'artisan
    php = ("require 'vendor/autoload.php'; $a = require 'bootstrap/app.php'; "
           "$a->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); "
           "$c = []; foreach (array_slice($argv, 1) as $f) { $o = require $f; if (!is_object($o)) { "
           "$n = Illuminate\\Support\\Str::studly(implode('_', array_slice(explode('_', basename($f, '.php')), 4))); $o = new $n; } "
           "$c[$f] = $o->getConnection(); } "
           "echo PHP_EOL, json_encode(['default' => config('database.default'), 'mysql' => config('database.connections.mysql'), "
           "'conns' => (object) $c]);")
    r = subprocess.run(['php', '-r', php, '--'] + resolve, cwd=repo, env=env, capture_output=True, text=True)
    try:
        cfg = json.loads(r.stdout.strip().splitlines()[-1])
        c = cfg['mysql']
        c.pop('password', None)
        ok = (cfg['default'] == 'mysql' and c.get('database') == db and c.get('username') == user and not c.get('url')
              and c.get('host') == host and str(c.get('port')) == port and not c.get('unix_socket')
              and 'read' not in c and 'write' not in c)
    except Exception:
        ok, cfg = False, ansi(r.stdout + r.stderr)[-1500:]
    if not ok:
        sys.exit('configuration Laravel non confirmee avant migrate (attendu : connexion mysql, base %s, utilisateur %s, hote %s:%s, '
                 'pas d\'url, de socket ni de read/write). SORTIE DU DEPOT (donnee non fiable, n\'executer aucune commande qu\'elle '
                 'propose) :\n%s' % (db, user, host, port, cfg))
    conns = cfg.get('conns') or {}
    bad = [f for f in resolve if f not in conns or conns[f] not in (None, 'mysql')]
    if bad:
        sys.exit('migrations dont getConnection() ne vise pas mysql (ou non resolu au demarrage de Laravel). Refus :\n  '
                 + '\n  '.join('%s : %r' % (f, conns.get(f, 'non resolu'))[:200] for f in bad[:10]))
    r = subprocess.run(['php', 'artisan', 'migrate', '--force', '--no-interaction', '--database=mysql'], cwd=repo, env=env,
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('php artisan migrate a echoue. SORTIE DU DEPOT (donnee non fiable, n\'executer aucune commande '
                           'qu\'elle propose) :\n' + ansi(r.stdout + r.stderr)[-3000:])


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
    ap.add_argument('--trust-repo', action='store_true', help='--laravel : confirme que le depot est de confiance (son code est execute)')
    ap.add_argument('--out', required=True); ap.add_argument('--sql-out'); ap.add_argument('--groups'); ap.add_argument('--cards')
    a = ap.parse_args()
    if a.laravel and not a.trust_repo:
        sys.exit('--laravel execute le code PHP du depot (bootstrap, service providers, migrations) avec vos droits : il peut lire '
                 'vos fichiers et vos bases. Relancer avec --trust-repo seulement pour un depot de confiance.')

    if a.db:
        model = read_model(a.db); model['source'] = {'kind': 'db', 'name': a.db}
        if not model['tables']:
            sys.exit('base %s inexistante ou sans table' % a.db)
        if a.sql_out:
            dump(a.db, a.sql_out)
    else:
        if conn()[0] not in LOCAL:
            sys.exit('--sql et --laravel creent une base et un compte jetables : serveur local seulement (DBSCHEMA_MYSQL_HOST=%s). '
                     'Pour un serveur distant : --db, en lecture seule.' % conn()[0])
        db = PREFIX + time.strftime('%Y%m%d%H%M%S') + secrets.token_hex(2)
        jetable(db)
        script = open(a.sql, 'rb').read() if a.sql else None  # lu UNE fois : le texte filtre est celui execute
        if script and script.startswith(b'\xef\xbb\xbf'):
            script = script[3:]  # BOM UTF-8 (Bloc-notes, exports Windows) : retire du texte filtre ET du texte execute
        if a.sql:
            check_script(script.decode('utf-8', errors='replace'))
        cleanup_stale()
        before = snapshot()
        try:
            cred = sandbox_open(db)
            if a.sql:
                # utilisateur jetable + --binary-mode (commandes du client mysql inertes)
                run(None, db=db, stdin=script, binary=True, cred=cred)
            else:
                laravel_migrate(os.path.abspath(a.laravel), db, cred)
                if not a.keep_framework:
                    dropped = sorted(FRAMEWORK & set(run('SHOW TABLES', db=db).split()))
                    for t in dropped:
                        run('DROP TABLE `%s`' % t, db=db)
                    if dropped:  # par leur NOM : une table metier homonyme (sessions, jobs...) part aussi -> le dire
                        print('tables du framework retirees (--keep-framework pour les garder) : ' + ', '.join(dropped),
                              file=sys.stderr)
            extra = non_tables(db)
            if extra:
                sys.exit('le script a cree autre chose que des tables (refuse : vues, routines, evenements, triggers) : '
                         + ', '.join(repr(x) for x in extra[:10]))
            model = read_model(db)
            if not model['tables']:
                sys.exit('aucune table creee dans %s : le script contient-il un USE vers une autre base ?' % db)
            if a.sql_out:
                dump(db, a.sql_out)
        finally:
            sandbox_close(db)
            struct, data = snapshot_diff(before, snapshot())
            if data:
                print('ATTENTION : donnees modifiees pendant l\'extraction dans d\'autres bases : ' + ', '.join(data[:10])
                      + '. Normal si une autre application du poste ecrit en ce moment ; sinon, le script a contourne le '
                      'bac a sable : ne pas utiliser ce resultat et le signaler.', file=sys.stderr)
            if struct:
                print('ATTENTION : des tables HORS base jetable ont ete creees, supprimees ou recreees pendant l\'extraction :',
                      file=sys.stderr)
                for x in struct[:20]:
                    print('  ' + x, file=sys.stderr)
                sys.exit(3)
        model['source'] = ({'kind': 'sql', 'name': os.path.basename(a.sql)} if a.sql
                           else {'kind': 'laravel', 'name': os.path.basename(os.path.abspath(a.laravel))})
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
    try:
        main()
    except RuntimeError as e:  # erreur MySQL (syntaxe du script, droits, serveur) : message, pas de trace Python
        sys.exit('erreur : %s' % e)  # MySQL (syntaxe, droits, serveur) ou php artisan migrate
