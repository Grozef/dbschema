"""laravel_migrate() sans PHP ni base : subprocess.run remplace par un faux qui joue la configuration renvoyee par le depot.
Prouve que migrate n'est lance QUE si la configuration effective vise la base et le compte jetables, en TCP local."""
import json, os, types
import pytest
import extract

DB, USER, PW = 'zz_dbschema_20260101000000ab', 'zz_dbschema_20260101000000ab', 'Zz9secret'
GOOD = {'default': 'mysql', 'mysql': {'driver': 'mysql', 'host': '127.0.0.1', 'port': '3306', 'database': DB, 'username': USER,
                                     'password': PW, 'unix_socket': '', 'url': None}}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'artisan').write_text('<?php')
    (tmp_path / 'database' / 'migrations').mkdir(parents=True)
    return tmp_path


@pytest.fixture
def fake(monkeypatch):
    """calls : commandes lancees ; cfg : JSON renvoye par php -r ; migrate_rc : code de retour de migrate."""
    state = types.SimpleNamespace(calls=[], envs=[], cfg=GOOD, raw=None, migrate_rc=0)

    def run(cmd, cwd=None, env=None, capture_output=False, text=False, **kw):
        state.calls.append(cmd)
        state.envs.append(env)
        if cmd[:2] == ['php', '-r']:
            out = state.raw if state.raw is not None else 'Laravel boot\n' + json.dumps(state.cfg)
            return types.SimpleNamespace(returncode=0, stdout=out, stderr='')
        if cmd[:2] == ['php', 'artisan']:
            return types.SimpleNamespace(returncode=state.migrate_rc, stdout='', stderr='SQLSTATE[42000] erreur' if state.migrate_rc else '')
        raise AssertionError('commande inattendue : %r' % cmd)
    monkeypatch.setattr(extract.subprocess, 'run', run)
    monkeypatch.delenv('DBSCHEMA_MYSQL_HOST', raising=False)
    monkeypatch.delenv('DBSCHEMA_MYSQL_PORT', raising=False)
    monkeypatch.setenv('DBSCHEMA_MYSQL_PASSWORD', 'mot-de-passe-root-a-ne-pas-transmettre')
    return state


def migrated(state):
    return any(c[:2] == ['php', 'artisan'] for c in state.calls)


def test_configuration_conforme_lance_migrate(repo, fake):
    extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert migrated(fake)
    assert fake.calls[-1] == ['php', 'artisan', 'migrate', '--force', '--no-interaction', '--database=mysql']


def test_environnement_minimal_et_force(repo, fake):
    extract.laravel_migrate(str(repo), DB, (USER, PW))
    env = fake.envs[0]
    assert env['DB_DATABASE'] == DB and env['DB_USERNAME'] == USER and env['DB_PASSWORD'] == PW
    assert env['DB_URL'] == '' and env['DATABASE_URL'] == '' and env['DB_SOCKET'] == '' and env['DB_HOST'] == '127.0.0.1'
    assert 'DBSCHEMA_MYSQL_PASSWORD' not in env  # aucun secret de la session ne part vers le code du depot
    assert not any(v == 'mot-de-passe-root-a-ne-pas-transmettre' for v in env.values())


def test_localhost_devient_127_0_0_1(repo, fake, monkeypatch):
    monkeypatch.setenv('DBSCHEMA_MYSQL_HOST', 'localhost')
    extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert fake.envs[0]['DB_HOST'] == '127.0.0.1' and migrated(fake)  # PDO + localhost = socket Unix


@pytest.mark.parametrize('patch,why', [
    ({'default': 'sqlite'}, 'connexion par defaut autre que mysql'),
    ({'mysql': {**GOOD['mysql'], 'database': 'prod'}}, 'autre base'),
    ({'mysql': {**GOOD['mysql'], 'username': 'root'}}, 'autre compte'),
    ({'mysql': {**GOOD['mysql'], 'host': '10.0.0.5'}}, 'autre hote'),
    ({'mysql': {**GOOD['mysql'], 'port': '3307'}}, 'autre port'),
    ({'mysql': {**GOOD['mysql'], 'url': 'mysql://root@127.0.0.1/prod'}}, 'url'),
    ({'mysql': {**GOOD['mysql'], 'unix_socket': '/var/run/mysqld/mysqld.sock'}}, 'socket'),
    ({'mysql': {**GOOD['mysql'], 'read': {'host': ['10.0.0.6']}}}, 'replica en lecture'),
    ({'mysql': {**GOOD['mysql'], 'write': {'host': ['10.0.0.7']}}}, 'ecriture ailleurs'),
], ids=lambda x: x if isinstance(x, str) else '')
def test_configuration_non_conforme_refusee_avant_migrate(repo, fake, patch, why):
    fake.cfg = {**GOOD, **patch}
    with pytest.raises(SystemExit, match='non confirmee avant migrate'):
        extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert not migrated(fake), why


def test_sortie_non_json_refusee(repo, fake):
    fake.raw = 'PHP Fatal error: Class not found\n'
    with pytest.raises(SystemExit, match='non confirmee avant migrate'):
        extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert not migrated(fake)


def test_mot_de_passe_absent_du_message_de_refus(repo, fake):
    fake.cfg = {**GOOD, 'mysql': {**GOOD['mysql'], 'database': 'prod'}}
    with pytest.raises(SystemExit) as e:
        extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert PW not in str(e.value)


def test_echec_de_migrate_remonte(repo, fake):
    fake.migrate_rc = 1
    with pytest.raises(RuntimeError, match='migrate a echoue'):
        extract.laravel_migrate(str(repo), DB, (USER, PW))


def test_config_en_cache_refusee(repo, fake):
    (repo / 'bootstrap' / 'cache').mkdir(parents=True)
    (repo / 'bootstrap' / 'cache' / 'config.php').write_text('<?php return [];')
    with pytest.raises(SystemExit, match='config Laravel en cache'):
        extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert fake.calls == []


def test_pas_d_artisan(tmp_path, fake):
    with pytest.raises(SystemExit, match='pas de fichier artisan'):
        extract.laravel_migrate(str(tmp_path), DB, (USER, PW))


def test_base_non_jetable_refusee(repo, fake):
    with pytest.raises(SystemExit, match='garde-fou'):
        extract.laravel_migrate(str(repo), 'prod', ('root', ''))
    assert fake.calls == []


def test_migration_vers_autre_connexion_refusee(repo, fake):
    (repo / 'database' / 'migrations' / 'x.php').write_text("<?php Schema::connection('legacy')->create('x');")
    with pytest.raises(SystemExit, match='autre connexion'):
        extract.laravel_migrate(str(repo), DB, (USER, PW))
    assert fake.calls == []
