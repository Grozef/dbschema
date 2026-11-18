import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
export const loadModel = (name) => JSON.parse(fs.readFileSync(path.join(FIX, name), 'utf8'));

const col = (name, o = {}) => ({ name, type: 'int', nullable: false, default: null, extra: '', comment: '', pk: false, fk: false, unique: false, ...o });

// modele minimal : tables = { nom: [colonnes] }, rels = [[de, colonne, vers, colonne_ref, card_parent]]
export function mini(tables, rels = [], groups = {}) {
  const m = { tables: {}, relations: [], groups, external_fks: [] };
  for (const [t, cols] of Object.entries(tables)) {
    m.tables[t] = { name: t, comment: '', indexes: [{ name: 'PRIMARY', unique: true, columns: ['id'] }],
      columns: [col('id', { pk: true }), ...cols.map((c) => col(c))] };
  }
  rels.forEach(([from, c, to, rc, parent = '1'], i) => {
    m.tables[from].columns.find((x) => x.name === c).fk = true;
    m.relations.push({ name: 'fk' + i, from, to, columns: [c], ref_columns: [rc], card_parent: parent, card_child: '0..N',
      on_update: 'RESTRICT', on_delete: 'CASCADE' });
  });
  return m;
}
