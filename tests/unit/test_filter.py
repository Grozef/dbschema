"""Filtre check_script (aucune base) : scripts dangereux refuses, scripts legitimes acceptes, lecture des jetons."""
import os
import pytest
import extract

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fixtures')

BAD = {
    'diese dans une chaine': "CREATE TABLE t (id INT); INSERT INTO t VALUES ('#'); DROP DATABASE prod; CREATE DATABASE x;",
    'tiret-tiret dans une chaine': "INSERT INTO t VALUES ('-- '); DROP DATABASE prod;",
    'commentaire ouvert dans une chaine': "INSERT INTO t VALUES ('/*'); DROP DATABASE prod; USE mysql; INSERT INTO t VALUES ('*/');",
    'ANSI_QUOTES': "SET sql_mode='ANSI_QUOTES'; DROP TABLE \"prod\".\"users\";",
    'NO_BACKSLASH_ESCAPES': "SET sql_mode='NO_BACKSLASH_ESCAPES'; INSERT INTO t VALUES ('\\'); DROP DATABASE prod; -- ');",
    'base commencant par un chiffre': "DROP TABLE 2024db.users;",
    'base accentuee': "DROP TABLE été.users;",
    'SET GLOBAL': "SET GLOBAL general_log_file='/var/www/shell.php'; SET GLOBAL general_log=1;",
    'SET PASSWORD root': "SET PASSWORD FOR root@localhost = 'x';",
    'SET PERSIST': "SET PERSIST max_connections=1;",
    'commande client \\u': "CREATE TABLE t (id INT) \\u prod\nDROP TABLE users;",
    'commande client \\!': "CREATE TABLE t (id INT);\n\\! calc\n",
    'USE': "USE prod; CREATE TABLE t (id INT);",
    'CREATE DATABASE': "CREATE DATABASE IF NOT EXISTS x;",
    'FK vers une autre base': "CREATE TABLE t (id INT PRIMARY KEY, u INT, FOREIGN KEY (u) REFERENCES autre.users(id));",
    'commentaire executable': "/*!40101 USE prod */; CREATE TABLE t (id INT);",
    # cas limites de jetons
    'commentaire executable sans version': "/*! USE prod */; CREATE TABLE t (id INT);",
    'chaine a quote doublee puis USE': "INSERT INTO t VALUES ('it''s'); USE prod;",
    'quote echappee puis base.table': "INSERT INTO t VALUES ('a\\''); DROP TABLE prod.users;",
    'nom qualifie entre backticks': "DROP TABLE `prod`.`users`;",
    'espaces autour du point': "DROP TABLE prod . users;",
    'GRANT hors liste blanche': "GRANT ALL ON *.* TO x;",
    'CREATE VIEW hors liste blanche': "CREATE VIEW v AS SELECT 1;",
    'LOAD DATA hors liste blanche': "LOAD DATA LOCAL INFILE '/etc/passwd' INTO TABLE t;",
    'SELECT INTO OUTFILE hors liste blanche': "SELECT 1 INTO OUTFILE '/tmp/x';",
    'SET NAMES gbk': "SET NAMES gbk; INSERT INTO t VALUES ('\xbf\\\\'); CREATE VIEW v AS SELECT 1; -- ');",
    'SET @@GLOBAL': "SET @@GLOBAL.read_only=1;",
    # trouve par le fuzz : MySQL execute tout le commentaire executable malgre le /**/ imbrique
    'commentaire imbrique dans un executable': "/*! SET /**/ GLOBAL general_log=1 */; CREATE TABLE t (id INT);",
    'imbrique avec version': "/*!40101 USE /* x */ prod */; CREATE TABLE t (id INT);",
    # relecture : chaine ouverte dans un commentaire executable, commentaire executable MariaDB
    'chaine ouverte dans un executable': "/*! SET @a='*/' ; USE prod; -- '*/",
    'executable MariaDB /*M!': '/*M!100100 USE prod */; CREATE TABLE t (id INT);',
}
GOOD = {
    'defaut decimal et chaine a point': "CREATE TABLE t (id INT PRIMARY KEY, r DECIMAL(5,2) DEFAULT 1.5, n VARCHAR(20) DEFAULT 'a.b');",
    'SET @@SESSION (mysqldump GTID)': "SET @@SESSION.SQL_LOG_BIN= 0; CREATE TABLE t (id INT);",
    'mysqldump classique': "/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */; SET NAMES utf8mb4; CREATE TABLE `t` (`id` int);",
    'demo.sql': open(os.path.join(FIX, 'demo.sql'), encoding='utf-8').read(),
    'edge-cases.sql': open(os.path.join(FIX, 'edge-cases.sql'), encoding='utf-8').read(),
    # cas limites de jetons
    'USE dans une chaine': "CREATE TABLE t (v VARCHAR(20)); INSERT INTO t VALUES ('USE prod');",
    'base.table dans une chaine doublee': 'CREATE TABLE t (v VARCHAR(20)); INSERT INTO t VALUES ("a"".b");',
    'base.table dans un commentaire': "CREATE TABLE t (id INT); -- voir prod.users\n",
    'diese en fin de fichier': "CREATE TABLE t (id INT); # fin",
    'commentaire bloc': "/* DROP DATABASE prod; prod.users */ CREATE TABLE t (id INT);",
    'nombre decimal': "CREATE TABLE t (r DECIMAL(5,2) DEFAULT 0.25);",
    'en-tete mariadb-dump (mode restreint)': '/*M!999999\\- enable the sandbox mode */ \nCREATE TABLE t (id INT);',
    'executable MariaDB inoffensif': '/*M!100100 SET @x=1 */; CREATE TABLE t (id INT);',
}


def refused(sql):
    try:
        extract.check_script(sql)
        return False
    except SystemExit:
        return True


@pytest.mark.parametrize('name', BAD)
def test_refuse(name):
    assert refused(BAD[name]), name


@pytest.mark.parametrize('name', GOOD)
def test_accepte(name):
    assert not refused(GOOD[name]), name


def test_clean_sql_chaines_et_commentaires():
    s = extract.clean_sql("INSERT INTO t VALUES ('a.b', \"c.d\"); /* x.y */ -- z.w\n/*!40101 SET a=1 */")
    assert 'a.b' not in s and 'c.d' not in s and 'x.y' not in s and 'z.w' not in s
    assert 'SET a=1' in s  # le contenu d'un commentaire executable est garde (MySQL l'execute)
