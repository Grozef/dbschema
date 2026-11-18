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
    # revue du 2026-11-18 : tables qui lisent ou ecrivent hors de la base jetable
    'ENGINE=FEDERATED + CONNECTION': "CREATE TABLE t (id INT) ENGINE=FEDERATED CONNECTION='mysql://root@127.0.0.1:3306/prod/users';",
    'ENGINE FEDERATED sans =': "CREATE TABLE t (id INT) ENGINE FEDERATED;",
    'ENGINE=CONNECT + FILE_NAME (MariaDB)': "CREATE TABLE t (l VARCHAR(200)) ENGINE=CONNECT TABLE_TYPE=DOS FILE_NAME='/etc/passwd';",
    'ENGINE=SPIDER (MariaDB)': "CREATE TABLE t (id INT) ENGINE=SPIDER COMMENT='wrapper \"mysql\", srv \"prod\"';",
    'DATA DIRECTORY': "CREATE TABLE t (id INT) DATA DIRECTORY='/tmp/x';",
    'INDEX DIRECTORY': "CREATE TABLE t (id INT) INDEX DIRECTORY='/tmp/x';",
    'ALTER vers FEDERATED': "CREATE TABLE t (id INT); ALTER TABLE t ENGINE=FEDERATED;",
    # -- nu en fin de ligne : MySQL execute la ligne suivante (verifie : "--\nSELECT 42;" rend 42), le filtre l'avalait
    '-- nu puis USE': "--\nUSE prod;\nCREATE TABLE t (id INT);",
    '-- nu (CRLF) puis DROP DATABASE': "--\r\nDROP DATABASE prod;\nCREATE TABLE t (id INT);",
    '-- nu en fin de fichier precede': "CREATE TABLE t (id INT); --\nDROP TABLE prod.users;",
    # relecture du 2026-11-18 : moteur en chaine ou en backticks, CONNECTION sans =, -- suivi d'un caractere de controle,
    # bloc compose MariaDB
    'ENGINE en chaine + CONNECTION sans =': "CREATE TABLE t (id int) ENGINE='FEDERATED' CONNECTION 'mysql://root@127.0.0.1/prod/u';",
    'ENGINE entre guillemets doubles': 'CREATE TABLE t (id int) ENGINE="FEDERATED";',
    'ENGINE entre backticks': 'CREATE TABLE t (id int) ENGINE=`FEDERATED`;',
    'ALTER vers CONNECT en chaine': "CREATE TABLE t (id int); ALTER TABLE t ENGINE='CONNECT';",
    'CONNECTION sans = sur InnoDB': "CREATE TABLE t (id int) ENGINE=InnoDB CONNECTION 'x';",
    '-- puis tabulation verticale': "CREATE TABLE t (a INT) --\x0b '\n; USE prod; -- '\n",
    '-- puis saut de page': "CREATE TABLE t (a INT) --\x0c '\n; USE prod; -- '\n",
    '-- puis caractere de controle': "CREATE TABLE t (a INT) --\x01 '\n; USE prod; -- '\n",
    'BEGIN NOT ATOMIC (bloc compose MariaDB)': 'BEGIN NOT ATOMIC END;',
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
    # revue du 2026-11-18 : exports reels promis par le README, moteurs locaux, colonne nommee engine
    'export phpMyAdmin (START TRANSACTION, COMMIT)': open(os.path.join(FIX, 'phpmyadmin.sql'), encoding='utf-8').read(),
    'export Adminer': open(os.path.join(FIX, 'adminer.sql'), encoding='utf-8').read(),
    'moteurs locaux': "CREATE TABLE a (id INT) ENGINE=InnoDB; CREATE TABLE b (id INT) ENGINE=MyISAM; CREATE TABLE c (id INT) ENGINE = MEMORY;",
    'colonne nommee engine ou connection': "CREATE TABLE t (`engine` VARCHAR(20), connection_id INT, data_dir VARCHAR(5));",
    'BEGIN / ROLLBACK': "BEGIN; CREATE TABLE t (id INT); ROLLBACK;",
    'BEGIN WORK / COMMIT WORK': "BEGIN WORK; CREATE TABLE t (id INT); COMMIT WORK;",
    'moteur InnoDB entre backticks': "CREATE TABLE t (id INT) ENGINE=`InnoDB`;",
    # 2e relecture : variables et colonnes entre backticks ne sont pas des options de table
    'variables @connection et @engine': "SET @connection = 1; SET @engine = 'x'; CREATE TABLE t (id INT);",
    'colonnes engine/connection affectees entre backticks': "CREATE TABLE t (`engine` VARCHAR(9), `connection` INT); "
                                                            "INSERT INTO t SET `engine`='x', `connection`=1;",
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
