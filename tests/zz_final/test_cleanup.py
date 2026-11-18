"""Dernier dossier collecte (zz_) : apres tous les tests, aucune base ni compte zz_dbschema_ ne doit rester sur le serveur."""
import pytest


@pytest.mark.functional
@pytest.mark.perf  # le job CI perf (-m perf) cree aussi des bases jetables : meme verification finale
def test_aucune_base_ni_compte_restant(db):
    left = (db.run("SHOW DATABASES LIKE 'zz\\_dbschema\\_%'") + db.run("SELECT user FROM mysql.user WHERE user LIKE 'zz\\_dbschema\\_%'")).split()
    assert left == [], left
