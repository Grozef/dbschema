"""read_model sur des lignes information_schema injectees : cardinalites, FK composite, auto-reference, FK externe, noms piégés,
valeurs par defaut MariaDB. Aucune base."""
import pytest
import extract

DB = 'zz_dbschema_unit'


def col(t, n, nullable=False, key='', default=None, typ='int'):
    return {'table': t, 'name': n, 'pos': 1, 'type': typ, 'nullable': nullable, 'default': default, 'key': key, 'extra': '', 'comment': ''}


def fk(name, t, c, rt, rc, seq=1, schema=DB):
    return {'name': name, 'table': t, 'column': c, 'seq': seq, 'ref_schema': schema, 'ref_table': rt, 'ref_column': rc,
            'on_update': 'RESTRICT', 'on_delete': 'CASCADE'}


def idx(t, name, c, unique=True, seq=1):
    return {'table': t, 'index': name, 'unique': unique, 'seq': seq, 'column': c}


TABLES = ['p', 'mand', 'opt', 'one', 'one_opt', 'comp', 'selfr', 'ext']
COLS = [col('p', 'id', key='PRI'), col('p', 'a', key='PRI'),
        col('mand', 'id', key='PRI'), col('mand', 'p_id'),
        col('opt', 'id', key='PRI'), col('opt', 'p_id', nullable=True),
        col('one', 'id', key='PRI'), col('one', 'p_id', key='UNI'),
        col('one_opt', 'id', key='PRI'), col('one_opt', 'p_id', nullable=True, key='UNI'),
        col('comp', 'id', key='PRI'), col('comp', 'x'), col('comp', 'y'),
        col('selfr', 'id', key='PRI'), col('selfr', 'parent_id', nullable=True),
        col('ext', 'id', key='PRI'), col('ext', 'u_id', default="'abc'")]
STATS = [idx(t, 'PRIMARY', 'id') for t in TABLES] + [idx('p', 'PRIMARY', 'a', seq=2), idx('one', 'u1', 'p_id'), idx('one_opt', 'u2', 'p_id')]
KCU = [fk('f_mand', 'mand', 'p_id', 'p', 'id'), fk('f_opt', 'opt', 'p_id', 'p', 'id'), fk('f_one', 'one', 'p_id', 'p', 'id'),
       fk('f_one_opt', 'one_opt', 'p_id', 'p', 'id'), fk('f_comp', 'comp', 'x', 'p', 'id'), fk('f_comp', 'comp', 'y', 'p', 'a', seq=2),
       fk('f_self', 'selfr', 'parent_id', 'selfr', 'id'), fk('f_ext', 'ext', 'u_id', 'users', 'id', schema='autre_base')]


def fake_rows(tables=TABLES, cols=COLS, stats=STATS, kcu=KCU):
    def rows(select, db):
        if 'KEY_COLUMN_USAGE' in select:
            return [dict(x) for x in kcu]
        if 'STATISTICS' in select:
            return [dict(x) for x in stats]
        if 'information_schema.COLUMNS' in select:
            return [dict(x) for x in cols]
        return [{'name': t, 'comment': ''} for t in tables]
    return rows


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(extract, 'rows', fake_rows())
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4)))
    return extract.read_model(DB)


@pytest.mark.parametrize('table,parent,child', [('mand', '1', '0..N'), ('opt', '0..1', '0..N'), ('one', '1', '0..1'),
                                                ('one_opt', '0..1', '0..1'), ('comp', '1', '0..N'), ('selfr', '0..1', '0..N')])
def test_cardinalites(model, table, parent, child):
    r = next(r for r in model['relations'] if r['from'] == table)
    assert (r['card_parent'], r['card_child']) == (parent, child)


def test_fk_composite(model):
    r = next(r for r in model['relations'] if r['from'] == 'comp')
    assert r['columns'] == ['x', 'y'] and r['ref_columns'] == ['id', 'a']


def test_auto_reference(model):
    r = next(r for r in model['relations'] if r['from'] == 'selfr')
    assert r['to'] == 'selfr'


def test_fk_externe_non_dessinee(model):
    assert not any(r['from'] == 'ext' for r in model['relations'])
    assert model['external_fks'] == ['ext.u_id -> autre_base.users']


def test_drapeaux_colonnes(model):
    c = {x['name']: x for x in model['tables']['one']['columns']}
    assert c['id']['pk'] and c['p_id']['fk'] and c['p_id']['unique'] and not c['id']['fk']


def test_mysql_garde_default_brut(model):
    assert {x['name']: x for x in model['tables']['ext']['columns']}['u_id']['default'] == "'abc'"


def test_mariadb_default_normalise(monkeypatch):
    monkeypatch.setattr(extract, 'rows', fake_rows())
    monkeypatch.setattr(extract, 'server', lambda: ('mariadb', (11, 4)))
    m = extract.read_model(DB)
    assert {x['name']: x for x in m['tables']['ext']['columns']}['u_id']['default'] == 'abc'


@pytest.mark.parametrize('bad', ['a\nb', 'a\tb', 'a\x00b', 'a b', 'a\x85b'])
def test_nom_avec_caractere_de_controle_refuse(monkeypatch, bad):
    monkeypatch.setattr(extract, 'rows', fake_rows(tables=['p', bad], cols=COLS[:2]))
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4)))
    with pytest.raises(SystemExit, match='caracteres de controle'):
        extract.read_model(DB)
