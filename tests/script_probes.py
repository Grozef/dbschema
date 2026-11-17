"""Filtre check_script seul (aucune base) : scripts dangereux refuses, scripts legitimes acceptes.
Usage : python -I script_probes.py <dossier lib>"""
import os, sys
sys.path.insert(0, sys.argv[1])
import extract

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
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
}
GOOD = {
    'defaut decimal et chaine a point': "CREATE TABLE t (id INT PRIMARY KEY, r DECIMAL(5,2) DEFAULT 1.5, n VARCHAR(20) DEFAULT 'a.b');",
    'SET @@SESSION (mysqldump GTID)': "SET @@SESSION.SQL_LOG_BIN= 0; CREATE TABLE t (id INT);",
    'mysqldump classique': "/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */; SET NAMES utf8mb4; CREATE TABLE `t` (`id` int);",
    'demo.sql': open(os.path.join(FIX, 'demo.sql'), encoding='utf-8').read(),
    'edge-cases.sql': open(os.path.join(FIX, 'edge-cases.sql'), encoding='utf-8').read(),
}
fails = 0
for name, sql in {**BAD, **GOOD}.items():
    try:
        extract.check_script(sql); refused = False
    except SystemExit:
        refused = True
    good = refused == (name in BAD)
    fails += not good
    print(('[OK] ' if good else '[ECHEC] ') + ('refuse : ' if refused else 'accepte : ') + name)
print('%d echec(s)' % fails)
sys.exit(1 if fails else 0)
