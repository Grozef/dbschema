"""dbschema.sh : arguments pieges refuses (code 2) avant toute extraction ni ecriture."""
import os
import pytest
from conftest import FIX, ROOT, run


@pytest.mark.parametrize('args,msg', [
    (['--name', '../x'], '--name'), (['--name', '.cache'], '--name'), (['--name', 'a/b'], '--name'), (['--name', 'a b'], '--name'),
    (['--name', '$(id)'], '--name'), (['--name', 'X', '--hub', '1;id'], '--hub'), (['--name', 'X', '--hub', '-1'], '--hub'),
    (['--name', 'X', '--evil'], 'option inconnue'), (['--name', 'X', '--frames', '--hub=3'], 'option inconnue'),
], ids=['parent', 'cache', 'slash', 'espace', 'subst', 'hub_injection', 'hub_negatif', 'option', 'option_egal'])
def test_argument_refuse(bash, tmp_path, args, msg):
    out_dir = tmp_path / 'out'
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--sql', os.path.join(FIX, 'edge-cases.sql'), '--out', str(out_dir), *args])
    assert code == 2 and msg in out, out[-300:]
    assert not out_dir.exists()  # rien d'ecrit
    assert not (tmp_path / 'x').exists()


def test_deux_sources_refusees(bash, tmp_path):
    """Avant : la derniere gagnait en silence (--sql a.sql --db prod lisait prod). Revue du 2026-11-18."""
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--sql', os.path.join(FIX, 'edge-cases.sql'), '--db', 'prod',
                     '--out', str(tmp_path / 'o'), '--name', 'X'])
    assert code == 2 and 'une seule source' in out, out[-300:]
    assert not (tmp_path / 'o').exists()


def test_keep_framework_transmis(bash, tmp_path):
    """--keep-framework est accepte par le point d'entree et transmis (l'extraction s'arrete ensuite : pas de depot Laravel)."""
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--laravel', str(tmp_path), '--trust-repo', '--keep-framework',
                     '--out', str(tmp_path / 'o'), '--name', 'X'])
    assert 'option inconnue' not in out and ('pas de fichier artisan' in out or 'serveur local' in out), out[-300:]


def test_source_manquante(bash, tmp_path):
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'all', '--out', str(tmp_path), '--name', 'X'])
    assert code == 2 and 'source manquante' in out


def test_commande_inconnue(bash):
    code, out = run([bash, os.path.join(ROOT, 'dbschema.sh'), 'rm', '-rf'])
    assert code == 2 and 'Usage' in out
