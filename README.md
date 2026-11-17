# dbschema

Skill [Claude Code](https://docs.claude.com/en/docs/claude-code) qui dessine le schéma d'une base MySQL dans le style de MySQL Workbench, mais avec une vraie mise en page :
- les tables sont séparées ;
- les liens sont orthogonaux, partent de la colonne FK et arrivent sur la colonne référencée ;
- les cardinalités sont en pattes d'oie avec leur texte (`1`, `0..1`, `0..N`, `1..N`) ;
- aucun chevauchement : c'est vérifié avant chaque livraison.

![Schéma de démonstration : librairie en ligne, 19 tables](examples/librairie.png)

Exemple interactif : [`examples/librairie.html`](examples/librairie.html) (à télécharger et ouvrir localement).

## Ce que ça produit

| Fichier | Contenu |
|---|---|
| `<NOM>.html` | Page autonome, sans ressource externe. Vues : toutes les colonnes, clés seules, noms seuls, liens complets vers les tables très référencées, cadres par domaine. Zoom, déplacement, recherche, surbrillance au survol, panneau de détail (colonnes, index, FK), légende des domaines, thème clair ou sombre, export PNG. |
| `<NOM>.png` | Vue complète en double résolution. |
| `<NOM>.sql` | `mysqldump --no-data` de la structure, donc un SQL déjà exécuté une fois. |
| `<NOM>_workbench_layout.py` | Script à lancer dans MySQL Workbench (*Scripting > Run Workbench Script File...*) pour placer les tables d'un diagramme existant. |
| `<NOM>_layout.mwb` | Avec `--mwb modele.mwb` : copie du modèle Workbench avec les tables placées. La source n'est pas modifiée. |

Sources acceptées :
- un script SQL (`--sql`) ;
- les migrations d'un projet Laravel (`--laravel`) ;
- une base MySQL existante, en lecture seule (`--db`).

## Installation

Prérequis :
- Node 18 ou plus ;
- Python 3.10 ou plus ;
- un serveur MySQL 8 local, avec ses clients `mysql` et `mysqldump` ;
- Google Chrome ou Edge, pour le PNG et la mesure des textes ;
- Playwright pour Python, seulement pour les tests d'interface.

```bash
git clone https://github.com/Grozef/dbschema.git ~/.claude/skills/dbschema
cd ~/.claude/skills/dbschema && npm ci --ignore-scripts
```

Variables d'environnement facultatives :

| Variable | Rôle | Défaut |
|---|---|---|
| `DBSCHEMA_MYSQL_BIN` | Dossier qui contient `mysql` | Laragon, sinon le `PATH` |
| `DBSCHEMA_MYSQL_USER` | Utilisateur MySQL | `root` |
| `DBSCHEMA_MYSQL_PASSWORD` | Mot de passe MySQL | aucun |
| `DBSCHEMA_CHROME` | Chemin du navigateur | Chrome ou Edge détecté |

## Utilisation

Dans Claude Code : `/dbschema mon_schema.sql`, ou une demande comme « dessine le schéma de la base ». En ligne de commande :

```bash
bash ~/.claude/skills/dbschema/dbschema.sh all --sql schema.sql --out sortie --name MON_SCHEMA \
  [--groups domaines.json] [--cards cardinalites.json] [--frames] [--hub 8|off] [--mwb modele.mwb]
```

Options :
- `--groups` : `{"DOMAINE": ["table", ...]}`. Chaque domaine a sa couleur et apparaît dans la légende ; `--frames` ajoute une vue où chaque domaine est encadré.
- `--cards` : cardinalités que le schéma ne peut pas exprimer, par exemple `{"orders.customer_id": {"child": "1..N"}}`.
- `--hub K` : une table référencée par plus de K clés étrangères (8 par défaut) a ses liens dessinés en amorces étiquetées (`→ users`). C'est l'équivalent du *split* de Workbench.

## Sécurité

**`--laravel` exécute le code PHP du dépôt** (bootstrap, service providers, migrations) avec vos droits : ne l'utilisez que sur un dépôt de confiance. Le skill refuse sans `--trust-repo`. Le code reçoit un environnement réduit (sans mot de passe ni jeton de votre session), mais ce n'est pas une barrière : il tourne sous votre compte et peut lire ce que vous pouvez lire.

**Les livrables décrivent votre base** : structure complète, commentaires, valeurs par défaut et ENUM, noms d'index et de contraintes. Relisez-les avant de les publier. Le SQL exporté ne contient que les tables : ni vues, ni triggers, ni routines, ni compteurs `AUTO_INCREMENT=N`. Un script `--sql` qui crée autre chose que des tables est refusé.

`--sql` et `--laravel` exécutent du code fourni par l'utilisateur. Garde-fous :
- **Base et utilisateur jetables.** Le script s'exécute dans une base `zz_dbschema_<horodatage>`, avec un utilisateur MySQL du même nom qui n'a de droits que sur cette base. Les deux sont supprimés à la fin, même en cas d'erreur ; si le processus est tué, au lancement suivant (après une heure).
- **Filtre avant exécution.** Un premier filtre refuse, avec un message lisible : `USE`, `CREATE/DROP DATABASE`, les noms `base.table`, `SET GLOBAL`, les modes SQL qui changent la lecture des chaînes, et les commandes du client `mysql`. Le client tourne en `--binary-mode`.
- **Laravel.** `DB_URL` est neutralisé. La configuration effective est lue avant `migrate`, et les migrations qui changent de connexion sont refusées.
- **Identifiants.** Ils passent par un fichier d'options temporaire, jamais par la ligne de commande. Le `my.ini` du serveur est ignoré et `local-infile` est désactivé.
- **Noms piégés.** Un nom de table ou de colonne qui contient un caractère de contrôle est refusé : il pourrait injecter du code dans le script Workbench généré.
- **Relevé avant/après.** Les tables des autres bases sont relevées avant et après : un écart arrête tout.

Limites : voir la section *Limites connues* de [`SKILL.md`](SKILL.md).

## Mise en page et contrôles

La mise en page utilise [elkjs](https://github.com/kieler/elkjs) (algorithme *layered*, routage orthogonal) en deux passes, avec des ports fixés sur les lignes de colonnes. Plusieurs FK vers une même colonne arrivent sur un port commun.

Chaque vue passe des contrôles bloquants avant d'être livrée :
- aucune table ne se superpose à une autre ;
- aucun lien ne traverse une table, et deux liens ne se superposent pas ;
- aucune étiquette n'est masquée ;
- chaque lien est accroché à la bonne colonne, à ses deux extrémités ;
- chaque relation est dessinée, avec ses cardinalités ;
- aucun texte ne déborde de sa carte (mesuré dans Chrome).

## Tests

```bash
bash dbschema.sh test
python tests/ui_test.py <fichier.html> <dossier_captures>
python tests/overflow_test.py <fichier.html>
```

La suite couvre :
- les cardinalités des cas limites ;
- tous les contrôles, y compris des mutations qui doivent les faire échouer ;
- les scripts SQL dangereux, qui doivent être refusés ;
- l'isolation de l'utilisateur jetable, vérifiée contre une base témoin ;
- l'aller-retour SQL → schéma → SQL.

`ui_test.py` teste les interactions de la page HTML ; `overflow_test.py` vérifie qu'aucun texte ne déborde. La suite principale crée et supprime des bases et un utilisateur `zz_dbschema_*` : à lancer sur un serveur de développement.

## Licence

MIT, voir [`LICENSE`](LICENSE). elkjs, installé par `npm ci`, est distribué sous EPL-2.0. Ce projet n'est affilié ni à Oracle ni à MySQL Workbench.
