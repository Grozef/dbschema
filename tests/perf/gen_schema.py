"""Schema SQL synthetique et deterministe (graine fixe) : N tables de 3 a 12 colonnes, 0 a 3 FK vers des tables anterieures,
2 tables hub (users, products) tres referencees. Usage : python gen_schema.py N > schema.sql"""
import random, sys

TYPES = ['INT', 'VARCHAR(80)', 'DECIMAL(10,2)', 'DATE', 'TIMESTAMP NULL', 'TINYINT(1) NOT NULL DEFAULT 0', 'TEXT', 'CHAR(2)']


def generate(n, seed=42):
    rng = random.Random(seed)
    out = ['CREATE TABLE users (id BIGINT UNSIGNED PRIMARY KEY, email VARCHAR(190) NOT NULL UNIQUE);',
           'CREATE TABLE products (id BIGINT UNSIGNED PRIMARY KEY, name VARCHAR(120) NOT NULL);']
    names = ['users', 'products']
    for i in range(n - 2):
        t = 't%03d_%s' % (i, rng.choice(['order', 'item', 'event', 'log', 'tag', 'note', 'stock', 'price']))
        cols = ['id BIGINT UNSIGNED PRIMARY KEY']
        cols += ['c%d %s' % (k, rng.choice(TYPES)) for k in range(rng.randint(2, 9))]
        fks = []
        targets = rng.sample(names, min(len(names), rng.randint(0, 3)))
        if rng.random() < .25 and 'users' not in targets:
            targets.append('users')
        for k, ref in enumerate(targets):
            nullable = rng.random() < .4
            cols.append('%s_id%d BIGINT UNSIGNED%s' % (ref, k, '' if nullable else ' NOT NULL'))
            fks.append('FOREIGN KEY (%s_id%d) REFERENCES %s(id)' % (ref, k, ref))
        out.append('CREATE TABLE %s (%s);' % (t, ', '.join(cols + fks)))
        names.append(t)
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    sys.stdout.write(generate(int(sys.argv[1])))
