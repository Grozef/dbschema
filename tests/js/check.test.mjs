// Chaque mutation d'un layout valide doit faire echouer check() (repris de check_mutations.mjs, sur la fixture edge-cases).
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { layout } from '../../lib/layout.mjs';
import { check, BLOCKING } from '../../lib/check.mjs';
import { loadModel } from './helpers.mjs';

let ALL, NAMES;
const clone = (x) => structuredClone(x);
before(async () => {
  const m = loadModel('edge.model.json');
  ALL = await layout(m, { mode: 'all' });
  NAMES = await layout(m, { mode: 'names' });
});

test('layout de reference valide', () => {
  const r = check(clone(ALL));
  assert.ok(r.ok, JSON.stringify(r).slice(0, 400));
  for (const k of BLOCKING) assert.equal(r[k].length, 0, k);
});

// [mutation, controle qui DOIT la detecter] : chaque controle bloquant a au moins une mutation (test de couverture plus bas)
const M = {
  "arrivee decalee d'une ligne": [(l) => { l.edges[0].points.at(-1)[1] += 22; l.edges[0].points.at(-2)[1] += 22; }, 'wrongAnchor'],
  "depart decale d'une ligne": [(l) => { l.edges[0].points[0][1] += 22; l.edges[0].points[1][1] += 22; }, 'wrongAnchor'],
  "amorce hub decalee d'une ligne": [(l) => { l.splits[0].y += 22; l.splits[0].box.y += 22; }, 'wrongAnchor'],
  'lien supprime': [(l) => { l.edges.pop(); }, 'incomplete'],
  'cardinalites parent/enfant inversees': [(l) => { const e = l.edges[0]; for (const x of e.labels) x.text = x.kind === 'child' ? e.card_parent === e.card_child ? 'X' : e.card_parent : e.card_child; }, 'incomplete'],
  'etiquettes retirees': [(l) => { for (const e of l.edges) e.labels = []; }, 'incomplete'],
  'etiquette enfant deplacee loin de son extremite': [(l) => { Object.assign(l.edges[0].labels.find((x) => x.kind === 'child'), { x: 5, y: l.height - 20 }); }, 'incomplete'],
  'etiquette hors du dessin': [(l) => { Object.assign(l.edges[0].labels[0], { x: -30, y: -20 }); }, 'outOfBounds'],
  "detour par l'interieur de la table source": [(l) => {
    const t0 = l.tables[l.edges[0].from], p = l.edges.find((e) => e.from === l.edges[0].from).points;
    p.splice(1, 0, [t0.x + t0.w / 2, p[0][1]], [p[0][0], p[0][1]]);
  }, 'edgeThroughTable'],
  "etiquette enfant sur le tronc d'un autre lien du meme port": [(l) => {
    const multi = l.edges.find((e) => l.edges.some((f) => f !== e && f.bus === e.bus));
    const o = l.edges.find((x) => x.bus === multi.bus && x.id !== multi.id);
    const [a, b] = o.points.slice(-2), lab = multi.labels.find((x) => x.kind === 'child');
    Object.assign(lab, { x: Math.min(a[0], b[0]) + 2, y: a[1] - 6 });
  }, 'labelHidden'],
  'table deplacee sur une autre': [(l) => { const [a, b] = Object.values(l.tables); Object.assign(b, { x: a.x + 5, y: a.y + 5 }); }, 'overlapTables'],
  'segment confondu avec un autre lien': [(l) => { const [e, f] = l.edges.filter((x) => x.bus !== l.edges[0].bus || x === l.edges[0]); f.points = clone(e.points); }, 'sharedSegments'],
  'table hors du dessin': [(l) => { Object.values(l.tables)[0].x = l.width + 50; }, 'outOfBounds'],
  "etiquette sous une table tierce": [(l) => {
    const lab = l.edges[0].labels[0], t = Object.values(l.tables).find((x) => x !== l.tables[l.edges[0].from] && x !== l.tables[l.edges[0].to]);
    Object.assign(lab, { x: t.x + 20, y: t.y + 30 });
  }, 'labelHidden'],
};

test('chaque controle bloquant est vise par au moins une mutation', () => {
  assert.deepEqual([...new Set(Object.values(M).map(([, k]) => k))].sort(), [...BLOCKING].sort());
});

for (const [name, [f, key]] of Object.entries(M)) {
  test(`mutation detectee par ${key} : ${name}`, () => {
    const l = clone(ALL);
    f(l);
    const r = check(l);
    assert.equal(r.ok, false);
    assert.ok(r[key].length > 0, `${key} vide ; controles declenches : ${BLOCKING.filter((k) => r[k].length).join(',')}`);
  });
}

test("mutation detectee : vue names, arrivee sur la mauvaise table", () => {
  const n = clone(NAMES), e = n.edges[0];
  e.to = Object.keys(n.tables).find((t) => t !== e.to && t !== e.from);
  assert.equal(check(n).ok, false);
});
