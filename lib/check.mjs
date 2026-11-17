// Controles geometriques et semantiques de layout.json. Code de sortie 1 si un controle bloquant echoue.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const BLOCKING = ['overlapTables', 'edgeThroughTable', 'sharedSegments', 'labelHidden', 'wrongAnchor', 'outOfBounds', 'incomplete'];

export function check(layout) {
  const T = Object.entries(layout.tables);
  const inter = (a, b, pad = 0) => a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad;
  const res = { crossings: 0, length: 0, bends: 0 };
  for (const k of BLOCKING) res[k] = [];
  const HEAD = 26, ROW = 22, names = layout.mode === 'names';
  const rowY = (t, col) => { const r = layout.tables[t], i = r.rows.indexOf(col); return i < 0 ? null : r.y + HEAD + ROW * i + ROW / 2; };
  const onBorder = (t, x) => { const r = layout.tables[t]; return Math.abs(x - r.x) < 0.5 || Math.abs(x - r.x - r.w) < 0.5; };

  // completude : chaque relation est un lien trace ou une amorce (mode names : une amorce peut en compter plusieurs)
  const drawn = layout.edges.length + layout.splits.reduce((a, s) => a + (s.count ?? 1), 0);
  if (layout.nrel !== undefined && drawn !== layout.nrel) res.incomplete.push(`${drawn} liens dessines pour ${layout.nrel} relations`);

  // extremites. Modes all/keys : depart sur la ligne de la colonne FK, arrivee sur la ligne de la colonne referencee, au bord.
  // Mode names : au bord de la bonne table, a l'interieur de sa hauteur.
  const anchorOk = (t, col, [x, y]) => {
    if (!layout.tables[t] || !onBorder(t, x)) return false;
    if (names) { const r = layout.tables[t]; return y > r.y && y < r.y + r.h; }
    const ry = rowY(t, col);
    return ry !== null && Math.abs(y - ry) < 0.5;
  };
  for (const e of layout.edges) {
    if (!anchorOk(e.from, e.columns[0], e.points[0])) res.wrongAnchor.push(`${e.id} depart hors de ${e.from}.${e.columns[0]}`);
    if (!anchorOk(e.to, e.ref_columns[0], e.points.at(-1))) res.wrongAnchor.push(`${e.id} arrivee hors de ${e.to}.${e.ref_columns[0]}`);
  }
  for (const s of layout.splits) if (!anchorOk(s.from, s.columns[0], [s.x, s.y])) res.wrongAnchor.push(`${s.id} amorce hors de ${s.from}.${s.columns[0]}`);

  // etiquettes de cardinalite : une cote enfant par lien, une cote parent par port d'arrivee, texte = cardinalite du lien
  const parentOf = {};
  for (const e of layout.edges) {
    const child = e.labels.filter((l) => l.kind === 'child'), parent = e.labels.filter((l) => l.kind === 'parent');
    const near = (l, [x, y]) => Math.hypot(Math.max(l.x - x, 0, x - l.x - l.w), Math.max(l.y - y, 0, y - l.y - l.h)) <= 60;
    for (const l of child) if (!near(l, e.points[0])) res.incomplete.push(`${e.id} etiquette enfant loin de son extremite`);
    for (const l of parent) if (!near(l, e.points.at(-1))) res.incomplete.push(`${e.id} etiquette parent loin de son extremite`);
    if (child.length !== 1 || child[0].text !== e.card_child) res.incomplete.push(`${e.id} etiquette enfant absente ou fausse`);
    for (const l of parent) {
      if (l.text !== e.card_parent) res.incomplete.push(`${e.id} etiquette parent fausse`);
      parentOf[e.bus ?? e.id] = (parentOf[e.bus ?? e.id] ?? 0) + 1;
    }
  }
  for (const b of new Set(layout.edges.map((e) => e.bus ?? e.id))) if (parentOf[b] !== 1) res.incomplete.push(`port ${b} : ${parentOf[b] ?? 0} etiquette(s) parent`);

  // tout dans le cadre du dessin : tables, points des liens, etiquettes, amorces
  const inside = (b) => b.x >= 0 && b.y >= 0 && b.x + (b.w ?? 0) <= layout.width && b.y + (b.h ?? 0) <= layout.height;
  for (const [n, r] of T) if (!inside(r)) res.outOfBounds.push(`table ${n}`);
  for (const e of layout.edges) {
    if (e.points.some(([x, y]) => !inside({ x, y }))) res.outOfBounds.push(`${e.id} trace`);
    for (const l of e.labels) if (!inside(l)) res.outOfBounds.push(`${e.id} etiquette "${l.text}"`);
  }
  for (const s of layout.splits) if (!inside(s.box)) res.outOfBounds.push(`${s.id} amorce`);

  for (let i = 0; i < T.length; i++) for (let j = i + 1; j < T.length; j++)
    if (inter(T[i][1], T[j][1], 10)) res.overlapTables.push(`${T[i][0]} / ${T[j][0]}`);

  const segs = [];
  for (const e of layout.edges) {
    for (let k = 0; k + 1 < e.points.length; k++) segs.push({ e, bus: e.bus ?? e.id, a: e.points[k], b: e.points[k + 1] });
    res.bends += Math.max(0, e.points.length - 2);
  }
  for (const s of layout.splits) {
    const sign = s.side === 'EAST' ? 1 : -1;
    segs.push({ e: { id: s.id, from: s.from, to: s.from }, bus: s.id, a: [s.x, s.y], b: [s.x + sign * 16, s.y] });
  }
  const segBox = (s) => ({ x: Math.min(s.a[0], s.b[0]), y: Math.min(s.a[1], s.b[1]), w: Math.abs(s.a[0] - s.b[0]), h: Math.abs(s.a[1] - s.b[1]) });
  for (const s of segs) {
    res.length += Math.hypot(s.a[0] - s.b[0], s.a[1] - s.b[1]);
    for (const [n, r] of T) {
      // tables tierces : bord compris ; tables du lien : l'interieur seulement (le lien part et arrive sur le bord)
      const m = n === s.e.from || n === s.e.to ? 2 : 1;
      if (inter(segBox(s), { x: r.x + m, y: r.y + m, w: r.w - 2 * m, h: r.h - 2 * m })) res.edgeThroughTable.push(`${s.e.id} (${s.e.from}->${s.e.to}) traverse ${n}`);
    }
  }
  const cross = new Set(); // un croisement = un point, meme si plusieurs liens d'un port partage s'y superposent
  const horiz = (s) => Math.abs(s.a[1] - s.b[1]) < 0.5, vert = (s) => Math.abs(s.a[0] - s.b[0]) < 0.5;
  for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) {
    const p = segs[i], q = segs[j];
    if (p.e.id === q.e.id || p.bus === q.bus) continue; // meme port d'arrivee : le tronc commun est voulu
    const P = segBox(p), Q = segBox(q);
    if (horiz(p) && horiz(q) && Math.abs(p.a[1] - q.a[1]) < 3) {
      const ov = Math.min(P.x + P.w, Q.x + Q.w) - Math.max(P.x, Q.x);
      if (ov > 4) res.sharedSegments.push(`${p.e.id}/${q.e.id} y=${Math.round(p.a[1])}`);
    } else if (vert(p) && vert(q) && Math.abs(p.a[0] - q.a[0]) < 3) {
      const ov = Math.min(P.y + P.h, Q.y + Q.h) - Math.max(P.y, Q.y);
      if (ov > 4) res.sharedSegments.push(`${p.e.id}/${q.e.id} x=${Math.round(p.a[0])}`);
    } else if ((horiz(p) && vert(q)) || (vert(p) && horiz(q))) {
      const H = horiz(p) ? P : Q, V = horiz(p) ? Q : P;
      if (V.x > H.x + 1 && V.x < H.x + H.w - 1 && H.y > V.y + 1 && H.y < V.y + V.h - 1) cross.add(Math.round(V.x) + ',' + Math.round(H.y));
    }
  }
  res.crossings = cross.size;
  const labels = [];
  for (const e of layout.edges) for (const l of e.labels) labels.push({ id: e.id, bus: e.bus ?? e.id, kind: l.kind, x: l.x, y: l.y, w: l.w, h: l.h, t: l.text });
  for (let i = 0; i < labels.length; i++) {
    const L = labels[i];
    for (const [n, r] of T) if (inter(L, r, -1)) res.labelHidden.push(`${L.id} "${L.t}" sur table ${n}`);
    for (let j = i + 1; j < labels.length; j++) if (inter(L, labels[j], -1)) res.labelHidden.push(`${L.id} "${L.t}" sur etiquette ${labels[j].id}`);
    // l'etiquette parent est posee sur le tronc commun de son port : seuls les liens de ce port sont admis dessous
    for (const s of segs) if (s.e.id !== L.id && !(L.kind === 'parent' && s.bus === L.bus) && inter(L, segBox(s), -1)) { res.labelHidden.push(`${L.id} "${L.t}" sur lien ${s.e.id}`); break; }
  }
  res.ok = BLOCKING.every((k) => !res[k].length);
  return res;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const r = check(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
  console.log(BLOCKING.map((k) => `${k}=${r[k].length}`).join(' ') + ` croisements=${r.crossings} longueur=${Math.round(r.length)} coudes=${r.bends} -> ${r.ok ? 'OK' : 'ECHEC'}`);
  if (process.argv.includes('--details')) for (const k of BLOCKING) for (const x of r[k]) console.log(`  [${k}] ${x}`);
  process.exit(r.ok ? 0 : 1);
}
