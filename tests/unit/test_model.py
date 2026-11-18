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
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4), False))
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
    monkeypatch.setattr(extract, 'server', lambda: ('mariadb', (11, 4), False))
    m = extract.read_model(DB)
    assert {x['name']: x for x in m['tables']['ext']['columns']}['u_id']['default'] == 'abc'


@pytest.mark.parametrize('bad', ['a\nb', 'a\tb', 'a\x00b', 'a b', 'a\x85b'])
def test_nom_avec_caractere_de_controle_refuse(monkeypatch, bad):
    monkeypatch.setattr(extract, 'rows', fake_rows(tables=['p', bad], cols=COLS[:2]))
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4), False))
    with pytest.raises(SystemExit, match='caracteres de controle'):
        extract.read_model(DB)


def test_casse_sensible_base_homonyme_est_externe(monkeypatch):
    """Linux (lower_case_table_names=0), verifie sur MySQL 8.4 : « Zz_dbschema_unit » est une AUTRE base que « zz_dbschema_unit ».
    La table cible « p » existe aussi dans la base lue : seule la comparaison exacte du schema rend la FK externe."""
    monkeypatch.setattr(extract, 'rows', fake_rows(kcu=KCU + [fk('f_case', 'ext', 'u_id', 'p', 'id', schema='Zz_dbschema_unit')]))
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4), True))
    m = extract.read_model(DB)
    assert 'ext.u_id -> Zz_dbschema_unit.p' in m['external_fks']
    assert not any(r['name'] == 'f_case' for r in m['relations'])


def test_casse_insensible_meme_base_est_interne(monkeypatch):
    """Windows / macOS : la meme base ecrite autrement est la meme ; FK interne."""
    monkeypatch.setattr(extract, 'rows', fake_rows(kcu=KCU + [fk('f_case', 'ext', 'u_id', 'p', 'id', schema='Zz_dbschema_unit')]))
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4), False))
    m = extract.read_model(DB)
    assert any(r['name'] == 'f_case' and r['to'] == 'p' for r in m['relations'])


def test_macos_reference_en_minuscules_vers_table_en_casse_mixte(monkeypatch):
    """lower_case_table_names=2 (macOS) : InnoDB range le nom reference en minuscules (« users ») alors que la table s'appelle
    « Users » : la FK reste interne et pointe vers le nom du modele (relecture du 2026-11-18 ; d'apres la doc, non execute)."""
    tables = TABLES + ['Users']
    cols = COLS + [col('Users', 'id', key='PRI')]
    kcu = KCU + [fk('f_mac', 'ext', 'u_id', 'users', 'id')]
    monkeypatch.setattr(extract, 'rows', fake_rows(tables=tables, cols=cols, kcu=kcu))
    monkeypatch.setattr(extract, 'server', lambda: ('mysql', (8, 4), False))
    m = extract.read_model(DB)
    assert any(r['name'] == 'f_mac' and r['to'] == 'Users' for r in m['relations']), m['external_fks']


def test_reference_vers_table_absente_jamais_dessinee(monkeypatch):
    """Garde : une table referencee absente du modele ne produit jamais de relation (sinon crash d'ELK au build)."""
    monkeypatch.setattr(extract, 'rows', fake_rows(kcu=KCU + [fk('f_abs', 'ext', 'u_id', 'absente', 'id')]))
    for sensible in (True, False):
        monkeypatch.setattr(extract, 'server', lambda s=sensible: ('mysql', (8, 4), s))
        m = extract.read_model(DB)
        assert all(r['to'] in m['tables'] for r in m['relations'])
        assert 'ext.u_id -> %s.absente' % DB in m['external_fks']
