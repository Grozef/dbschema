"""Mise en page + controles + sorties sur les cas limites extraits (build.mjs)."""
import os


def test_build_edge_controles_ok(edge):
    assert edge['code'] == 0, edge['build'][-800:]
    for v in ('all', 'keys', 'names', 'all-full'):
        assert any(l.startswith('[%s]' % v) and l.endswith('-> OK') for l in edge['build'].splitlines()), v


def test_hub_et_amorces(edge):
    lay = edge['lay']('all')
    assert lay['hubs'] == ['hub'] and len(lay['splits']) == 9


def test_auto_reference_tracee(edge):
    s = [e for e in edge['lay']('all')['edges'] if e['from'] == e['to'] == 'self_ref']
    assert len(s) == 1 and len(s[0]['points']) >= 2


def test_un_port_par_cardinalite_parent(edge):
    """parent.id recoit des FK de cardinalite 1 et 0..1 : un port de chaque cote."""
    lay = edge['lay']('all')
    px = lay['tables']['parent']['x']
    sides = {(e['card_parent'], 'E' if abs(e['points'][-1][0] - px) > 1 else 'W') for e in lay['edges'] if e['to'] == 'parent'}
    assert len(sides) == 2 and len({s for _, s in sides}) == 2, sorted(sides)


def test_mode_cles_colonne_referencee_visible(edge):
    assert 'iso' in edge['lay']('keys')['tables']['country']['rows']


def test_sorties_html_png(edge, chrome):
    for f in ('EDGE.html', 'EDGE.png'):
        p = edge['dir'] / 'out' / f
        assert p.exists() and p.stat().st_size > 1000, f


def test_texte_mesure_sans_debordement(edge, chrome):
    lines = [l for l in edge['build'].splitlines() if l.startswith('[texte]')]
    assert any('debordements mesures' in l and ': 0 -> OK' in l for l in lines), lines
