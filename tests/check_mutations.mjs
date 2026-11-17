// Chaque mutation d'un layout valide doit faire echouer check(). Usage : node check_mutations.mjs <layout_all.json> <layout_names.json>
import fs from 'node:fs';
import { check } from '../lib/check.mjs';

const load = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const [all, names] = process.argv.slice(2);
const base = load(all);
const multi = base.edges.find((e) => base.edges.some((f) => f !== e && f.bus === e.bus));
const t0 = base.tables[base.edges[0].from];
const M = {
  'arrivee decalee d\'une ligne': (l) => { l.edges[0].points.at(-1)[1] += 22; l.edges[0].points.at(-2)[1] += 22; },
  'depart decale d\'une ligne': (l) => { l.edges[0].points[0][1] += 22; l.edges[0].points[1][1] += 22; },
  'amorce hub decalee d\'une ligne': (l) => { l.splits[0].y += 22; l.splits[0].box.y += 22; },
  'lien supprime': (l) => { l.edges.pop(); },
  'cardinalites parent/enfant inversees': (l) => { const e = l.edges[0]; for (const x of e.labels) x.text = x.kind === 'child' ? e.card_parent === e.card_child ? 'X' : e.card_parent : e.card_child; },
  'etiquettes retirees': (l) => { for (const e of l.edges) e.labels = []; },
  'etiquette enfant deplacee loin de son extremite': (l) => { Object.assign(l.edges[0].labels.find((x) => x.kind === 'child'), { x: 5, y: l.height - 20 }); },
  'etiquette hors du dessin': (l) => { Object.assign(l.edges[0].labels[0], { x: -30, y: -20 }); },
  'detour par l\'interieur de la table source': (l) => { const p = l.edges.find((e) => e.from === base.edges[0].from).points; p.splice(1, 0, [t0.x + t0.w / 2, p[0][1]], [p[0][0], p[0][1]]); },
  'etiquette enfant sur le tronc d\'un autre lien du meme port': (l) => {
    const e = l.edges.find((x) => x.id === multi.id), o = l.edges.find((x) => x.bus === multi.bus && x.id !== multi.id);
    const [a, b] = o.points.slice(-2), lab = e.labels.find((x) => x.kind === 'child');
    Object.assign(lab, { x: Math.min(a[0], b[0]) + 2, y: a[1] - 6 });
  },
};
let bad = 0;
const r0 = check(load(all));
console.log((r0.ok ? '[OK] ' : '[ECHEC] ') + 'layout de reference valide');
if (!r0.ok) bad++;
for (const [name, f] of Object.entries(M)) {
  const l = load(all); f(l);
  const r = check(l);
  console.log((r.ok ? '[ECHEC] non detecte : ' : '[OK] detecte : ') + name);
  if (r.ok) bad++;
}
const n = load(names); const e = n.edges[0]; const other = Object.keys(n.tables).find((t) => t !== e.to && t !== e.from);
e.to = other; // le lien pretend arriver sur une autre table
const rn = check(n);
console.log((rn.ok ? '[ECHEC] non detecte : ' : '[OK] detecte : ') + 'vue names : arrivee sur la mauvaise table');
if (rn.ok) bad++;
process.exit(bad ? 1 : 0);
