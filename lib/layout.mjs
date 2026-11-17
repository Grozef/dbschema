// model.json -> layout.json (positions absolues). ELK layered, routage orthogonal, ports sur les lignes de colonnes.
// Passe 1 : tables + TOUTES les FK (placement, couches, ordre). Passe 2 : ports figes, FK "hub" retirees (dessinees en amorces),
// couches et ordre de la passe 1 conserves.
// Options : --mode=all|keys|names  --hub=8|off  --frames  --spacing=1  --dir=RIGHT|DOWN
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ELK from 'elkjs/lib/elk.bundled.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const CW = JSON.parse(fs.readFileSync(path.join(here, '..', 'assets', 'charwidths.json'), 'utf8'));
// Largeurs de texte par caractere et par style. o.cw = table mesuree dans Chrome par build.mjs pour les caracteres du modele ;
// a defaut, table Tahoma figee (assets/charwidths.json).
export const STYLES = { col: 'font-size:11px', colb: 'font-size:11px;font-weight:700', type: 'font-size:11px',
  bold: 'font-size:12px;font-weight:700', tag: 'font-size:10px;font-style:italic', foot: 'font-size:10.5px', card: 'font-size:10.5px;font-weight:700' };
const FALLBACK = { col: 'col', colb: 'bold', type: 'type', bold: 'bold', tag: 'col', foot: 'col', card: 'col' };
const widthFn = (cw) => (s, kind) => {
  const m = cw?.[kind] ?? CW[FALLBACK[kind]];
  return [...s].reduce((a, ch) => a + (m[ch] ?? m.__fallback), 0);
};
export const HEAD = 26, ROW = 22, FOOT = 26;
// separateur des cles internes (ports, cadres) : U+0000 est interdit dans un identifiant MySQL, donc aucune collision avec un nom
const SEP = '\u0000';

// referenced : colonnes referencees par une FK (affichees aussi en mode cles : les liens y arrivent)
export function visibleColumns(t, mode, referenced = new Set()) {
  if (mode === 'names') return [];
  if (mode === 'keys') return t.columns.filter((c) => c.pk || c.fk || referenced.has(t.name + '.' + c.name));
  return t.columns;
}
export const shortType = (c) => c.type.toUpperCase().replace(/ UNSIGNED/, '');

export async function layout(model, o = {}) {
  const wd = widthFn(o.cw);
  const mode = o.mode ?? 'all', HUB_K = o.hub ?? 8, SP = o.spacing ?? 1, DIR = o.dir ?? 'RIGHT', FRAMES = !!o.frames;

  const inDeg = {};
  for (const r of model.relations) inDeg[r.to] = (inDeg[r.to] ?? 0) + 1;
  const hubs = new Set(HUB_K === 'off' ? [] : Object.keys(inDeg).filter((t) => inDeg[t] > HUB_K));
  const rels = model.relations.map((r, i) => ({ ...r, id: 'e' + i, split: hubs.has(r.to) && r.from !== r.to }));
  const routed = rels.filter((r) => !r.split);
  const splitTag = {}; // "table.colonne" -> texte de l'etiquette dans la ligne
  for (const r of rels.filter((r) => r.split)) splitTag[r.from + '.' + r.columns[0]] = '→ ' + r.to + ' ' + r.card_parent;

  const referenced = new Set(model.relations.map((r) => r.to + '.' + r.ref_columns[0]));
  const cards = Object.create(null); // Object.create(null) : un nom de table "__proto__" reste une cle ordinaire
  for (const t of Object.values(model.tables)) {
    const cols = visibleColumns(t, mode, referenced);
    const tag = (c) => { const x = splitTag[t.name + '.' + c.name]; return x ? wd(x, 'tag') + 10 : 0; };
    const wCols = cols.length ? Math.max(...cols.map((c) => 8 + 14 + wd(c.name, c.pk ? 'colb' : 'col') + tag(c) + 14 + wd(shortType(c), 'type') + 10)) : 0;
    const hubTag = mode === 'names' ? [...new Set(rels.filter((r) => r.split && r.from === t.name).map((r) => r.to))].map((h) => '→ ' + h).join(' ') : '';
    const foot = mode === 'names' ? 0 : wd('Indexes (' + t.indexes.length + ')' + (mode === 'keys' && t.columns.length > cols.length ? ' · +' + (t.columns.length - cols.length) + ' col.' : ''), 'foot') + 18;
    const w = Math.ceil(Math.max(mode === 'names' ? 90 : 150, wCols, foot, 8 + wd(t.name, 'bold') + 16 + (hubTag ? wd(hubTag, 'tag') + 8 : 0)));
    if (hubTag) (splitTag.__head ??= {})[t.name] = hubTag;
    // mode names (pas de colonnes) : une ligne vide par lien pour accrocher les ports sans collision. Modes all et keys :
    // depart sur la ligne de la colonne FK, arrivee sur la ligne de la colonne referencee, aucune ligne ajoutee.
    const inR = routed.filter((r) => r.to === t.name && r.from !== t.name).length, outR = routed.filter((r) => r.from === t.name).length;
    const extra = mode === 'names' ? inR + outR : 0;
    const slots = cols.length + extra;
    const h = mode === 'names' ? HEAD + ROW * extra + 8 : HEAD + ROW * slots + FOOT;
    cards[t.name] = { w, h, slots, rowOf: Object.fromEntries(cols.map((c, i) => [c.name, i])) };
  }
  const portY = (t, col) => (cards[t].rowOf[col] === undefined ? HEAD / 2 : HEAD + ROW * cards[t].rowOf[col] + ROW / 2);

  const groupOf = {};
  for (const [g, ts] of Object.entries(model.groups ?? {})) for (const t of ts) groupOf[t] = g;
  const frameOf = FRAMES ? groupOf : {};

  const base = {
    'elk.algorithm': 'layered', 'elk.direction': DIR, 'elk.edgeRouting': 'ORTHOGONAL',
    'elk.hierarchyHandling': 'INCLUDE_CHILDREN', 'elk.json.shapeCoords': 'ROOT', 'elk.json.edgeCoords': 'ROOT',
    'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP', 'elk.layered.thoroughness': '60',
    'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
    'elk.spacing.nodeNode': String(70 * SP), 'elk.layered.spacing.nodeNodeBetweenLayers': String(110 * SP),
    'elk.spacing.edgeEdge': String(14 * SP), 'elk.spacing.edgeNode': String(24 * SP),
    'elk.layered.spacing.edgeEdgeBetweenLayers': String(14 * SP), 'elk.layered.spacing.edgeNodeBetweenLayers': String(50 * SP),
    'elk.spacing.edgeLabel': '4', 'elk.spacing.labelLabel': '4',
    'elk.spacing.componentComponent': String(90 * SP), 'elk.padding': '[top=40,left=40,bottom=40,right=40]',
  };
  const groupOpts = { 'elk.padding': '[top=46,left=26,bottom=26,right=26]' };

  // busOf[id] : port d'arrivee partage par toutes les FK vers la meme colonne, du meme cote, de meme cardinalite parent
  function graph(withPorts, edges, sideOf, portOrder, busOf) {
    const port = (id, s, x, y) => ({ id, x: s === 'EAST' ? x : 0, y, width: 0, height: 0, layoutOptions: { 'elk.port.side': s } });
    const mkNode = (t) => {
      const c = cards[t];
      const n = { id: t, width: c.w, height: c.h, layoutOptions: {} };
      if (withPorts) {
        n.layoutOptions['elk.portConstraints'] = 'FIXED_POS';
        n.ports = [];
        if (mode !== 'names') {
          for (const r of edges.filter((r) => r.from === t)) n.ports.push(port(r.id + ':s', sideOf[r.id].src, c.w, portY(t, r.columns[0])));
          const seen = new Set();
          for (const r of edges.filter((r) => r.to === t && !seen.has(busOf[r.id]))) {
            seen.add(busOf[r.id]);
            n.ports.push(port('b:' + busOf[r.id], sideOf[r.id].tgt, c.w, portY(t, r.ref_columns[0])));
          }
        } else for (const s of ['EAST', 'WEST']) {
          const list = portOrder[t]?.[s] ?? []; // ids suffixes :t (cibles) ou :s (sources en mode names)
          const top = 4, span = c.h - 8; // repli si plus de ports que de lignes (ne devrait pas arriver : slots = liens)
          // mode names : une ligne vide par port (depart et arrivee), repartis dans l'ordre des tables partenaires
          const free = [...Array(c.slots).keys()].map((i) => HEAD + ROW * i + ROW / 2);
          const ys = list.length && free.length >= list.length
            ? list.map((_, j) => free[list.length === 1 ? Math.floor((free.length - 1) / 2) : Math.round(j * (free.length - 1) / (list.length - 1))])
            : list.map((_, j) => top + span * (j + 1) / (list.length + 1));
          list.forEach((pid, i) => n.ports.push({ id: pid, x: s === 'EAST' ? c.w : 0, y: ys[i],
            width: 0, height: 0, layoutOptions: { 'elk.port.side': s } }));
        }
      }
      return n;
    };
    const root = { id: 'root', layoutOptions: { ...base }, children: [], edges: [] };
    const gnodes = {};
    for (const t of Object.keys(model.tables)) {
      const g = frameOf[t];
      if (g) (gnodes[g] ??= { id: SEP + 'g' + g, layoutOptions: { ...base, ...groupOpts }, children: [] }).children.push(mkNode(t));
      else root.children.push(mkNode(t));
    }
    root.children.push(...Object.values(gnodes));
    for (const r of edges) {
      if (r.from === r.to && !withPorts) continue;
      const tgt = !withPorts ? r.to : mode === 'names' ? r.id + ':t' : 'b:' + busOf[r.id];
      root.edges.push({ id: r.id, sources: [withPorts ? r.id + ':s' : r.from], targets: [tgt] });
    }
    return root;
  }
  const flat = (n, acc = []) => { for (const c of n.children ?? []) { acc.push(c); flat(c, acc); } return acc; };

  const elk = new ELK();
  const p1 = await elk.layout(graph(false, rels));
  const pos1 = Object.fromEntries(flat(p1).map((n) => [n.id, n]));
  const cx = (t) => pos1[t].x + pos1[t].width / 2, cy = (t) => pos1[t].y + pos1[t].height / 2;

  // auto-references : tracees a la main apres ELK (sa boucle de 10 px ne laisse pas la place au symbole)
  const selfLoops = routed.filter((r) => r.from === r.to);
  const elkEdges = routed.filter((r) => r.from !== r.to);
  const sideOf = {}, portOrder = {};
  for (const r of elkEdges) {
    let src, tgt;
    if (Math.abs(cx(r.to) - cx(r.from)) < 40) { src = 'EAST'; tgt = 'EAST'; }
    else if (cx(r.to) > cx(r.from)) { src = 'EAST'; tgt = 'WEST'; }
    else { src = 'WEST'; tgt = 'EAST'; }
    sideOf[r.id] = { src, tgt };
  }
  const busOf = {}, busKey = (r, side) => [r.to, r.ref_columns[0], side, r.card_parent].join(SEP);
  if (mode !== 'names') {
    // Une colonne referencee recoit au plus un port par cote. Deux cardinalites parent differentes (1 et 0..1) ne peuvent pas
    // partager un port (un seul symbole) : chacune prend alors un cote, celui de la majorite de ses liens.
    const byCol = {};
    for (const r of elkEdges) (byCol[r.to + SEP + r.ref_columns[0]] ??= []).push(r);
    for (const list of Object.values(byCol)) {
      const byCard = {};
      for (const r of list) (byCard[r.card_parent] ??= []).push(r);
      const groups = Object.values(byCard).sort((a, b) => b.length - a.length);
      if (groups.length > 2) throw new Error('plus de deux cardinalites parent sur ' + list[0].to + '.' + list[0].ref_columns[0]);
      if (groups.length === 2) {
        const pref = (g) => (g.filter((r) => sideOf[r.id].tgt === 'EAST').length * 2 >= g.length ? 'EAST' : 'WEST');
        const s0 = pref(groups[0]), s1 = s0 === 'EAST' ? 'WEST' : 'EAST';
        for (const r of groups[0]) sideOf[r.id].tgt = s0;
        for (const r of groups[1]) sideOf[r.id].tgt = s1;
      }
      for (const r of list) busOf[r.id] = busKey(r, sideOf[r.id].tgt);
    }
    // une colonne FK elle-meme referencee (cle partagee 1:1) : le depart prend le cote libre
    const busAt = new Set(elkEdges.map((r) => r.to + SEP + r.ref_columns[0] + SEP + sideOf[r.id].tgt));
    for (const r of elkEdges) {
      const k = r.from + SEP + r.columns[0] + SEP;
      if (busAt.has(k + sideOf[r.id].src)) sideOf[r.id].src = sideOf[r.id].src === 'EAST' ? 'WEST' : 'EAST';
    }
  } else {
    for (const r of elkEdges) {
      ((portOrder[r.to] ??= {})[sideOf[r.id].tgt] ??= []).push(r.id + ':t');
      ((portOrder[r.from] ??= {})[sideOf[r.id].src] ??= []).push(r.id + ':s');
    }
  }
  const byId = Object.fromEntries(routed.map((r) => [r.id, r]));
  const partnerY = (pid) => { const [id, k] = pid.split(':'); return cy(k === 't' ? byId[id].from : byId[id].to); };
  for (const t in portOrder) for (const s in portOrder[t]) portOrder[t][s].sort((a, b) => partnerY(a) - partnerY(b));

  base['elk.layered.layering.strategy'] = 'INTERACTIVE';
  base['elk.layered.crossingMinimization.strategy'] = 'INTERACTIVE';
  const g2 = graph(true, elkEdges, sideOf, portOrder, busOf);
  for (const n of flat(g2)) if (pos1[n.id]) { n.x = pos1[n.id].x; n.y = pos1[n.id].y; }
  const p2 = await elk.layout(g2);

  const out = { mode, nrel: model.relations.length, splitTag, width: p2.width, height: p2.height, hubs: [...hubs], tables: Object.create(null), groups: Object.create(null), edges: [], splits: [] };
  for (const n of flat(p2)) {
    if (n.id.startsWith(SEP + 'g')) out.groups[n.id.slice(2)] = { x: n.x, y: n.y, w: n.width, h: n.height };
    else out.tables[n.id] = { x: n.x, y: n.y, w: n.width, h: n.height, group: groupOf[n.id] ?? null, rows: Object.keys(cards[n.id].rowOf) };
  }
  const edgesOut = [];
  const collect = (n) => { for (const e of n.edges ?? []) edgesOut.push(e); for (const c of n.children ?? []) collect(c); };
  collect(p2);
  const meta = (r) => ({ id: r.id, name: r.name, from: r.from, to: r.to, columns: r.columns, ref_columns: r.ref_columns,
    card_parent: r.card_parent, card_child: r.card_child, on_delete: r.on_delete, on_update: r.on_update });
  for (const e of edgesOut) {
    const pts = [];
    for (const s of e.sections ?? []) pts.push([s.startPoint.x, s.startPoint.y], ...(s.bendPoints ?? []).map((b) => [b.x, b.y]), [s.endPoint.x, s.endPoint.y]);
    out.edges.push({ ...meta(byId[e.id]), bus: busOf[e.id] ?? e.id, points: pts, labels: [] });
  }
  // boucle d'auto-reference : sort de la ligne FK, revient sur la ligne de la colonne referencee. Cote est, sauf si un port
  // d'une autre cardinalite y occupe deja la colonne referencee (alors cote ouest).
  for (const r of selfLoops) {
    const t = out.tables[r.from];
    const taken = (s) => elkEdges.some((x) => x.to === r.to && x.ref_columns[0] === r.ref_columns[0] && sideOf[x.id].tgt === s && x.card_parent !== r.card_parent);
    const side = mode !== 'names' && taken('EAST') && !taken('WEST') ? 'WEST' : 'EAST';
    const x0 = side === 'EAST' ? t.x + t.w : t.x, x1 = x0 + (side === 'EAST' ? 60 : -60);
    const y1 = t.y + portY(r.from, r.columns[0]);
    let y2 = t.y + portY(r.from, r.ref_columns[0]);
    if (Math.abs(y2 - y1) < ROW) y2 = y1 + (y1 - t.y > t.h / 2 ? -ROW : ROW); // mode names : pas de lignes de colonnes
    out.edges.push({ ...meta(r), bus: mode !== 'names' ? busKey(r, side) : r.id, points: [[x0, y1], [x1, y1], [x1, y2], [x0, y2]], labels: [] });
    out.width = Math.max(out.width, x1 + 40);
  }
  if (!FRAMES) {
    // rangement garde seulement s'il tient mieux sur un ecran 16:10 (ELK loge parfois deja les petites composantes dans ses vides)
    const fit = (o) => Math.max(o.width, o.height * 1.6);
    const before = JSON.stringify(out), f0 = fit(out);
    packComponents(out, routed);
    if (fit(out) >= f0) Object.assign(out, JSON.parse(before));
  }
  placeLabels(out, byId, wd);

  // Amorces des liens hub : cote choisi pour ne toucher ni table, ni lien, ni autre etiquette
  const STUB = 16;
  const segs = out.edges.flatMap((e) => e.points.slice(1).map((p, k) => [e.points[k], p]));
  const boxes = [...Object.values(out.tables), ...out.edges.flatMap((e) => e.labels)];
  const hitBox = (b, r) => b.x < r.x + r.w && r.x < b.x + b.w && b.y < r.y + r.h && r.y < b.y + b.h;
  const hitSeg = (b, [a, c]) => hitBox(b, { x: Math.min(a[0], c[0]), y: Math.min(a[1], c[1]), w: Math.abs(a[0] - c[0]) + 0.1, h: Math.abs(a[1] - c[1]) + 0.1 });
  for (const r of rels.filter((r) => r.split)) {
    // mode names : une seule amorce par couple de tables (sinon amorces superposees sur l'en-tete)
    if (mode === 'names') { const prev = out.splits.find((x) => x.from === r.from && x.to === r.to); if (prev) { prev.count = (prev.count ?? 1) + 1; continue; } }
    const t = out.tables[r.from], y = t.y + portY(r.from, r.columns[0]);
    const text = splitTag[r.from + '.' + r.columns[0]];
    const cand = ['EAST', 'WEST'].map((side) => {
      const sign = side === 'EAST' ? 1 : -1, x = side === 'EAST' ? t.x + t.w : t.x;
      const box = { x: sign > 0 ? x : x - STUB, y: y - 8, w: STUB, h: 16 };
      const bad = boxes.filter((b) => b !== t && hitBox(box, b)).length + segs.filter((s) => hitSeg(box, s)).length
        + out.splits.filter((s) => hitBox(box, s.box)).length;
      return { side, x, box, bad };
    }).sort((a, b) => a.bad - b.bad);
    const best = cand[0];
    out.splits.push({ ...meta(r), side: best.side, x: best.x, y, box: best.box, text });
  }
  return out;
}

// Composantes sans lien entre elles (ELK les empile) : rangement en etageres vers un rapport 1.6. Une composante = tables
// reliees par des liens traces ; on la translate d'un bloc (tables, points, amorces), sa geometrie interne ne change pas.
function packComponents(out, routed) {
  const parent = {};
  const find = (a) => (parent[a] === a ? a : (parent[a] = find(parent[a])));
  for (const t in out.tables) parent[t] = t;
  for (const r of routed) parent[find(r.from)] = find(r.to);
  const comps = {};
  for (const t in out.tables) (comps[find(t)] ??= []).push(t);
  const list = Object.values(comps);
  if (list.length < 2) return;
  const M = 30, GAP = 90;
  const bbox = (ts) => {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const grow = (x, y) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); };
    for (const t of ts) { const r = out.tables[t]; grow(r.x - M, r.y - M); grow(r.x + r.w + M, r.y + r.h + M); }
    for (const e of out.edges) if (ts.includes(e.from)) for (const p of e.points) grow(p[0] - M, p[1] - M), grow(p[0] + M, p[1] + M);
    return { x0, y0, w: x1 - x0, h: y1 - y0 };
  };
  const items = list.map((ts) => ({ ts, b: bbox(ts) })).sort((a, b) => b.b.h - a.b.h || b.b.w - a.b.w);
  const area = items.reduce((s, i) => s + i.b.w * i.b.h, 0);
  const W = Math.max(items[0].b.w, Math.sqrt(area * 1.6));
  let x = 40, y = 40, rowH = 0, maxX = 0;
  for (const it of items) {
    if (x > 40 && x + it.b.w > W + 40) { x = 40; y += rowH + GAP; rowH = 0; }
    const dx = x - it.b.x0, dy = y - it.b.y0;
    for (const t of it.ts) { out.tables[t].x += dx; out.tables[t].y += dy; }
    for (const e of out.edges) if (it.ts.includes(e.from)) e.points = e.points.map(([px, py]) => [px + dx, py + dy]);
    for (const s of out.splits) if (it.ts.includes(s.from)) { s.x += dx; s.y += dy; s.box = { ...s.box, x: s.box.x + dx, y: s.box.y + dy }; }
    x += it.b.w + GAP; rowH = Math.max(rowH, it.b.h); maxX = Math.max(maxX, x);
  }
  out.width = maxX - GAP + 40;
  out.height = y + rowH + 40;
}

// Cardinalites : candidats autour de chaque extremite, on garde le premier qui ne touche ni table, ni lien, ni etiquette deja posee.
function placeLabels(out, byId, wd) {
  const hit = (b, r) => b.x < r.x + r.w && r.x < b.x + b.w && b.y < r.y + r.h && r.y < b.y + b.h;
  const segs = out.edges.flatMap((e) => e.points.slice(1).map((p, k) => ({ id: e.id, bus: e.bus, a: e.points[k], b: p })));
  const sb = (s) => ({ x: Math.min(s.a[0], s.b[0]) - 1, y: Math.min(s.a[1], s.b[1]) - 1, w: Math.abs(s.a[0] - s.b[0]) + 2, h: Math.abs(s.a[1] - s.b[1]) + 2 });
  const tables = Object.values(out.tables), placed = [], busDone = new Set();
  const score = (box, e) => tables.filter((t) => hit(box, t)).length * 100
    + segs.filter((s) => s.id !== e.id && s.bus !== e.bus && hit(box, sb(s))).length * 10 + placed.filter((l) => hit(box, l)).length * 10;
  for (const e of out.edges) {
    if (e.points.length < 2) continue;
    const r = byId[e.id];
    const ends = [[r.card_child, e.points[0], e.points[1]]];
    // un port partage = un seul symbole et une seule etiquette cote parent
    if (!busDone.has(e.bus)) { busDone.add(e.bus); ends.push([r.card_parent, e.points.at(-1), e.points.at(-2)]); }
    for (const [text, p, q] of ends) {
      const dx = Math.sign(q[0] - p[0]) || 1, w = wd(text, 'card') + 4, h = 13;
      const seg = Math.abs(q[0] - p[0]);
      const cands = [];
      for (const off of [18, 24, 32, 44]) {
        if (off + w > seg + 6 && off > 18) continue; // reste sur le 1er segment
        const x = dx > 0 ? p[0] + off : p[0] - off - w;
        cands.push({ x, y: p[1] - 15, w, h }, { x, y: p[1] + 3, w, h });
      }
      let best = null, bs = Infinity;
      for (const c of cands) { const sc = score(c, e); if (sc < bs) { bs = sc; best = c; } if (!sc) break; }
      const lab = { text, kind: p === e.points[0] ? 'child' : 'parent', ...best };
      e.labels.push(lab); placed.push(lab);
    }
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const [, , modelPath, outPath, ...rest] = process.argv;
  const opt = Object.fromEntries(rest.map((a) => { const [k, v] = a.replace(/^--/, '').split('='); return [k, v ?? true]; }));
  const o = { cw: opt.cw ? JSON.parse(fs.readFileSync(opt.cw, 'utf8')) : undefined, mode: opt.mode, frames: opt.frames, dir: opt.dir, spacing: opt.spacing ? Number(opt.spacing) : undefined,
    hub: opt.hub === 'off' ? 'off' : opt.hub ? Number(opt.hub) : undefined };
  const out = await layout(JSON.parse(fs.readFileSync(modelPath, 'utf8')), o);
  fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
  console.log(`mode=${out.mode} tables=${Object.keys(out.tables).length} liens_routes=${out.edges.length} liens_split=${out.splits.length} hubs=${out.hubs.join(',') || '-'} taille=${Math.round(out.width)}x${Math.round(out.height)}`);
}
