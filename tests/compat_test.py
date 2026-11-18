"""Compatibilite : la suite complete contre MariaDB 11.4, MySQL 5.7 et MySQL 8.4 en conteneurs jetables, puis un run Linux
(python3, clients MariaDB, sans Chrome) contre MariaDB. Rien ne touche au MySQL local : ports 339x sur 127.0.0.1, conteneurs
supprimes a la fin. Usage : python -I compat_test.py <dossier temporaire>   (Docker absent : SKIP, code 0)"""
import os, secrets, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
LIB = os.path.join(SKILL, 'lib')
tmp = sys.argv[1]
MATRIX = [('mariadb:11.4', 3391, 'MARIADB_ROOT_PASSWORD'), ('mysql:5.7', 3392, 'MYSQL_ROOT_PASSWORD'),
          ('mysql:8.4', 3393, 'MYSQL_ROOT_PASSWORD')]
LINUX = 'node:24-bookworm'
fails, names = [], []


def ok(name, cond, detail=''):
    print(('[OK] ' if cond else '[ECHEC] ') + name + (f'  ({detail})' if detail != '' else ''), flush=True)
    if not cond:
        fails.append(name)


def docker(*a, check=True):
    r = subprocess.run(['docker', *a], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and r.returncode:
        raise RuntimeError('docker %s : %s' % (a[0], r.stderr.strip()[-300:]))
    return r


if subprocess.run(['docker', 'version'], capture_output=True).returncode:
    print('SKIP : Docker ne repond pas (demarrer Docker Desktop ou le service docker)')
    sys.exit(0)

pw = 'Cpt' + secrets.token_hex(12)
env_for = lambda port: {**os.environ, 'DBSCHEMA_MYSQL_PORT': str(port), 'DBSCHEMA_MYSQL_PASSWORD': pw}


def wait_ready(port, timeout=240):
    probe = [sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import extract; print(extract.run("SELECT VERSION()"))', LIB]
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = subprocess.run(probe, capture_output=True, text=True, env=env_for(port))
        if r.returncode == 0:
            return r.stdout.strip()
        time.sleep(3)
    return None


ready = {}
try:
    for image, port, var in MATRIX:
        name = 'dbschema_compat_' + image.replace(':', '_').replace('.', '')
        names.append(name)
        docker('rm', '-f', name, check=False)
        docker('run', '-d', '--rm', '--name', name, '-e', var + '=' + pw, '-p', '127.0.0.1:%d:3306' % port, image)
        version = wait_ready(port)
        ok(image + ' : serveur pret', version is not None, version)
        if not version:
            continue
        ready[image] = name
        r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'run_tests.py'), os.path.join(tmp, name)], capture_output=True,
                           text=True, encoding='utf-8', errors='replace', env=env_for(port))
        bad = [l for l in r.stdout.splitlines() if l.startswith('[ECHEC]')]
        ok(image + ' : suite complete', r.returncode == 0, ' | '.join(bad)[:1500] or '%d verifications' % r.stdout.count('[OK]'))

    # Linux : le conteneur partage le reseau de MariaDB (127.0.0.1:3306 = MariaDB), skill monte en lecture seule
    maria = ready.get('mariadb:11.4')
    if not maria:
        raise RuntimeError('MariaDB non pret : run Linux impossible')
    linux = 'dbschema_compat_linux'
    names.append(linux)
    script = ('set -e; apt-get update -qq >/dev/null; apt-get install -y -qq python3 mariadb-client >/dev/null; '
              'bash /skill/dbschema.sh all --sql /skill/tests/fixtures/demo.sql --groups /skill/tests/fixtures/demo.groups.json '
              '--frames --out /tmp/o --name DEMO; ls /tmp/o; '
              'echo "RESTE:$(mariadb -h127.0.0.1 -uroot -N -e "SELECT COUNT(*) FROM mysql.user WHERE user LIKE \'zz%\'")"')
    r = docker('run', '--rm', '--name', linux, '--network', 'container:' + maria, '-e', 'DBSCHEMA_MYSQL_PASSWORD=' + pw, '-e', 'MYSQL_PWD=' + pw,
               '-v', SKILL + ':/skill:ro', LINUX, 'bash', '-c', script, check=False)
    out = r.stdout + r.stderr
    tail = r.stdout.strip()[-600:] + ' | ' + r.stderr.strip()[-300:]
    ok('Linux (python3, client MariaDB) : extraction 19 tables / 31 FK', 'tables=19' in out and 'relations=31' in out, tail)
    ok('Linux : 5 vues controlees OK (avec --frames)', out.count('-> OK') == 5 and r.returncode == 0, tail)
    ok('Linux sans Chrome : PNG annonce absent, HTML et SQL produits', 'PNG non produit' in out and 'DEMO.html' in out and 'DEMO.sql' in out)
    ok('Linux : aucun compte zz_dbschema_ restant', 'RESTE:0' in out, out.strip()[-200:])
finally:
    for n in names:
        docker('rm', '-f', n, check=False)
    left = docker('ps', '-a', '--filter', 'name=dbschema_compat', '--format', '{{.Names}}', check=False).stdout.strip()
    ok('conteneurs supprimes', left == '', left)

print('\n%d echec(s)' % len(fails))
sys.exit(1 if fails else 0)
