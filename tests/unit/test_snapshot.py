"""Releve avant/apres : creation, suppression ou recreation d'une table hors base jetable = bloquant ; donnees seules = note
(une autre application du poste peut ecrire pendant l'extraction ; revue du 2026-11-18)."""
import extract

T0 = {'shop.users': ('2026-01-01 10:00:00', '2026-11-18 09:00:00'), 'shop.orders': ('2026-01-01 10:00:00', '')}


def test_identique():
    assert extract.snapshot_diff(T0, dict(T0)) == ([], [])


def test_ecriture_de_donnees_seule_non_bloquante():
    after = {**T0, 'shop.users': ('2026-01-01 10:00:00', '2026-11-18 09:05:00')}
    assert extract.snapshot_diff(T0, after) == ([], ['shop.users'])


def test_table_creee_supprimee_recreee_bloquantes():
    after = {'shop.users': ('2026-11-18 09:05:00', ''), 'prod.evil': ('2026-11-18 09:05:00', '')}
    struct, data = extract.snapshot_diff(T0, after)
    assert struct == ['+ prod.evil', '- shop.orders', '~ shop.users'] and data == []


def test_sandbox_close_repli_si_mysql_user_illisible(monkeypatch, capsys):
    """Lecture de mysql.user refusee : on supprime au moins 127.0.0.1 et localhost, puis la base, et on le signale."""
    sent = []

    def run(sql, **kw):
        sent.append(sql)
        if sql.startswith('SELECT host'):
            raise RuntimeError('SELECT command denied to user')
        return ''
    monkeypatch.setattr(extract, 'run', run)
    extract.sandbox_close('zz_dbschema_20260101000000ab')
    assert sent[1:] == ["DROP USER IF EXISTS 'zz_dbschema_20260101000000ab'@'127.0.0.1'",
                        "DROP USER IF EXISTS 'zz_dbschema_20260101000000ab'@'localhost'",
                        'DROP DATABASE IF EXISTS `zz_dbschema_20260101000000ab`']
    assert 'nettoyage incomplet' in capsys.readouterr().err
