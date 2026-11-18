// layout() + check() sur des modeles minimaux et sur les fixtures (sans base ni navigateur : table de chasse Tahoma figee).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { layout, visibleColumns, shortType } from '../../lib/layout.mjs';
import { check } from '../../lib/check.mjs';
import { mini, loadModel } from './helpers.mjs';

const ok = (lay) => { const r = check(lay); assert.ok(r.ok, JSON.stringify(r).slice(0, 600)); return r; };

test('une table seule', async () => {
  const lay = await layout(mini({ a: ['x'] }));
  assert.deepEqual(Object.keys(lay.tables), ['a']);
  assert.equal(lay.edges.length, 0);
  ok(lay);
});

test('deux tables liees : un lien, deux etiquettes', async () => {
  const lay = await layout(mini({ p: [], c: ['p_id'] }, [['c', 'p_id', 'p', 'id']]));
  assert.equal(lay.edges.length, 1);
  assert.deepEqual(lay.edges[0].labels.map((l) => l.text).sort(), ['0..N', '1']);
  ok(lay);
});

test('auto-reference tracee', async () => {
  const lay = await layout(mini({ t: ['parent_id'] }, [['t', 'parent_id', 't', 'id', '0..1']]));
  assert.equal(lay.edges.length, 1);
  assert.ok(lay.edges[0].points.length >= 2);
  ok(lay);
});

test('hub au-dela de K : liens en amorces, hub off : liens complets', async () => {
  const tables = { h: [] }, rels = [];
  for (let i = 0; i < 4; i++) { tables['t' + i] = ['h_id']; rels.push(['t' + i, 'h_id', 'h', 'id']); }
  const m = mini(tables, rels);
  const split = await layout(m, { hub: 3 });
  assert.deepEqual(split.hubs, ['h']);
  assert.equal(split.splits.length, 4);
  ok(split);
  const full = await layout(m, { hub: 'off' });
  assert.equal(full.splits.length, 0);
  assert.equal(full.edges.length, 4);
  ok(full);
});

test('mode names : table vers 3 hubs, amorces sans superposition (bug a 250 tables)', async () => {
  const tables = { h1: [], h2: [], h3: [] }, rels = [];
  for (const t of ['x', 'y']) { tables[t] = ['a', 'b', 'c']; ['h1', 'h2', 'h3'].forEach((h, k) => rels.push([t, 'abc'[k], h, 'id'])); }
  const lay = await layout(mini(tables, rels), { mode: 'names', hub: 1 });
  assert.deepEqual(lay.hubs.sort(), ['h1', 'h2', 'h3']);
  const x = lay.splits.filter((s) => s.from === 'x');
  assert.equal(new Set(x.map((s) => s.side)).size, x.length);  // au plus une amorce par cote
  ok(lay);
});

for (const mode of ['all', 'keys', 'names']) {
  test(`fixture edge-cases, mode ${mode} : controles OK`, async () => ok(await layout(loadModel('edge.model.json'), { mode })));
  test(`fixture demo, mode ${mode} : controles OK`, async () => ok(await layout(loadModel('demo.model.json'), { mode })));
}

test('fixture demo avec cadres par domaine : controles OK', async () => ok(await layout(loadModel('demo.model.json'), { mode: 'all', frames: true })));

test('mise en page deterministe', async () => {
  const m = loadModel('demo.model.json');
  assert.deepEqual(await layout(m), await layout(m));
});

for (const mode of ['all', 'keys', 'names']) {
  test(`table, hub et groupe nommes __proto__ : cles ordinaires (mode ${mode})`, async () => {
    // le modele arrive par JSON.parse (cle propre "__proto__"), comme model.json ; bug reel : crash du mode names
    const tables = { zzproto: [] }, rels = [];
    for (let i = 0; i < 3; i++) { tables['c' + i] = ['p_id']; rels.push(['c' + i, 'p_id', 'zzproto', 'id']); }
    const m = JSON.parse(JSON.stringify(mini(tables, rels, { zzproto: ['zzproto', 'c0'] })).replaceAll('"zzproto"', '"__proto__"'));
    for (const hub of [2, 'off']) {
      const lay = await layout(m, { mode, hub, frames: true });
      assert.ok(Object.keys(lay.tables).includes('__proto__'));
      if (hub === 2) assert.deepEqual(lay.hubs, ['__proto__']);
      ok(lay);
    }
  });
}

test('visibleColumns : mode cles garde PK, FK et colonnes referencees', () => {
  const t = { columns: [{ name: 'id', pk: true }, { name: 'p_id', fk: true }, { name: 'iso' }, { name: 'libre' }] };
  assert.deepEqual(visibleColumns(t, 'keys', new Set(['x.iso'])).map((c) => c.name), ['id', 'p_id']);
  assert.equal(visibleColumns(t, 'all').length, 4);
  assert.equal(visibleColumns(t, 'names').length, 0);
});

for (const col of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) {
  for (const mode of ['all', 'names']) {
    test(`colonne FK "${col}" (hub + auto-reference), mode ${mode} : controles OK (revue du 2026-11-18)`, async () => {
      const tables = { h: [] }, rels = [];
      for (let i = 0; i < 3; i++) { tables['t' + i] = [col]; rels.push(['t' + i, col, 'h', 'id']); }
      tables.s = [col];
      rels.push(['s', col, 's', 'id', '0..1']);
      ok(await layout(JSON.parse(JSON.stringify(mini(tables, rels))), { mode, hub: 2 }));
    });
  }
}

test('colonnes au nom numerique (2, 10) : ordre des lignes conserve, controles OK (N3, revue du 2026-11-18)', async () => {
  const lay = await layout(mini({ p: [], c: ['note', '10', '2'] }, [['c', '2', 'p', 'id']]));
  assert.deepEqual(lay.tables.c.rows, ['id', 'note', '10', '2']);
  ok(lay);
});

test('ENUM tres long : type affiche tronque, carte de largeur bornee (revue du 2026-11-18)', async () => {
  const m = mini({ t: ['etat'] });
  m.tables.t.columns[1].type = 'enum(' + Array.from({ length: 40 }, (_, i) => `'valeur_numero_${i}'`).join(',') + ')';
  const st = shortType(m.tables.t.columns[1]);
  assert.equal(st.length, 40);
  assert.ok(st.endsWith('…'));
  const lay = await layout(m);
  assert.ok(lay.tables.t.w < 450, lay.tables.t.w);
  ok(lay);
});

test("shortType : coupe par caracteres, jamais au milieu d'un emoji", () => {
  const st = shortType({ type: "enum('" + '😀'.repeat(60) + "')" });
  assert.equal([...st].length, 40);
  assert.ok(!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/.test(st), 'paire de substitution coupee');
});

test('shortType : majuscules, sans UNSIGNED', () => {
  assert.equal(shortType({ type: 'int unsigned' }), 'INT');
  assert.equal(shortType({ type: 'varchar(20)' }), 'VARCHAR(20)');
});
