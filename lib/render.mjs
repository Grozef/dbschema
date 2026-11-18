// HTML autonome (aucune ressource externe) : vues pre-calculees (SVG) + interactions. Aussi : page statique pour le PNG.
import fs from 'node:fs';
import crypto from 'node:crypto';
import { renderSvg, SVG_CSS, groupColors } from './svg.mjs';
import { esc } from './geom.mjs';

// Script de la page : fichier a part (lisible, verifiable par node --check), insere tel quel ; la CSP n'autorise QUE lui
// (empreinte sha256), pas de 'unsafe-inline' : un script injecte par un nom de table ne s'executerait pas.
// fins de ligne ramenees a LF : le navigateur normalise CRLF -> LF avant de calculer l'empreinte d'un script ; un clone Windows
// (core.autocrlf=true) donnait un viewer.js en CRLF, donc une empreinte fausse et un script BLOQUE (relecture du 2026-11-18)
const VIEWER = fs.readFileSync(new URL('../assets/viewer.js', import.meta.url), 'utf8').replace(/\r\n?/g, '\n');
const VIEWER_SHA = 'sha256-' + crypto.createHash('sha256').update(VIEWER, 'utf8').digest('base64');

export function staticPage(model, layout) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#fff}${SVG_CSS}</style></head><body>${renderSvg(model, layout)}</body></html>`;
}

// views : [{ id, label, layout }]
export function interactivePage(model, views, { title }) {
  const colors = groupColors(model);
  const data = { tables: model.tables, relations: model.relations.map((r, i) => ({ ...r, id: 'e' + i })), groups: model.groups ?? {}, colors,
    file: title.replace(/[^\w.-]+/g, '_') }; // file : nom de l'export PNG du navigateur
  const svgs = views.map((v, i) => `<div class="view" data-view="${v.id}"${i ? ' hidden' : ''}>${renderSvg(model, v.layout)}</div>`).join('\n');
  const legend = Object.keys(data.groups).map((g) => `<button class="lg" data-group="${esc(g)}"><i style="background:${colors[g]}"></i>${esc(g)}</button>`).join('');
  const viewOpts = views.filter((v) => !v.id.endsWith('-full') && !v.id.endsWith('-frames'))
    .map((v) => `<option value="${v.id}">${esc(v.label)}</option>`).join('');
  const hasFull = views.some((v) => v.id === 'all-full'), hasFrames = views.some((v) => v.id === 'all-frames');
  return `<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src '${VIEWER_SHA}'; style-src 'unsafe-inline'; img-src blob: data:; connect-src 'none'; form-action 'none'; base-uri 'none'"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
:root{--ui:#f6f7f9;--uib:#d9dee5;--uit:#1f2328;--uim:#6a737d;--acc:#d9480f;--panel:#fff;color-scheme:light}
:root[data-theme=dark]{--ui:#1b1e24;--uib:#343a45;--uit:#e6e8ec;--uim:#98a1b0;--panel:#22262d;color-scheme:dark}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{font:13px/1.4 'Segoe UI',Tahoma,sans-serif;background:var(--ui);color:var(--uit);display:flex;flex-direction:column;overflow:hidden}
header{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:8px 14px;border-bottom:1px solid var(--uib);background:var(--ui);z-index:3}
header h1{font-size:15px;margin:0 6px 0 0}
header .stat{color:var(--uim)}
header input[type=search]{width:220px;padding:5px 8px;border:1px solid var(--uib);border-radius:6px;background:var(--panel);color:var(--uit)}
header select,header button{padding:5px 9px;border:1px solid var(--uib);border-radius:6px;background:var(--panel);color:var(--uit);cursor:pointer;font:inherit}
header label{display:flex;gap:5px;align-items:center;cursor:pointer;user-select:none}
.legend{display:flex;flex-wrap:wrap;gap:6px}.lg{display:flex;gap:5px;align-items:center;font-size:12px!important;padding:3px 8px!important}
.lg i{width:10px;height:10px;border-radius:2px;display:inline-block}.lg.on{outline:2px solid var(--acc)}
main{flex:1;position:relative;overflow:hidden;cursor:grab}main.drag{cursor:grabbing}
#stage{position:absolute;left:0;top:0;transform-origin:0 0}
aside{position:absolute;right:0;top:0;bottom:0;width:min(420px,92vw);background:var(--panel);border-left:1px solid var(--uib);overflow:auto;padding:14px 16px;z-index:4;box-shadow:-4px 0 14px #0002}
aside h2{margin:0 0 4px;font-size:16px}aside h3{margin:16px 0 6px;font-size:13px;color:var(--uim);text-transform:uppercase;letter-spacing:.05em}
aside table{border-collapse:collapse;width:100%;font-size:12px}aside td,aside th{padding:3px 6px;border-bottom:1px solid var(--uib);text-align:left;vertical-align:top}
aside .x{position:absolute;right:10px;top:8px;border:0;background:none;font-size:20px;cursor:pointer;color:var(--uim)}
aside a{color:var(--acc);cursor:pointer;text-decoration:underline}
.hint{position:absolute;left:12px;bottom:10px;color:var(--uim);font-size:12px;background:var(--ui);padding:3px 8px;border-radius:6px;border:1px solid var(--uib)}
${SVG_CSS}
:root[data-theme=dark] .erd{--bg:#16181d;--ink:#e6e8ec;--mute:#98a1b0;--line:#9aa4b2;--bd:#4a5668;--row:#22262d;--foot:#2a2f37}
:root[data-theme=dark] .erd .card{fill:#ffb37a}:root[data-theme=dark] .erd .split-tag{fill:#ffb37a}
.erd .tbl,.erd .rel{transition:opacity .12s}
.focus .erd .tbl:not(.on):not(.nb),.focus .erd .rel:not(.on),.focus .erd .grp{opacity:.15}
.erd .rel.on .ln,.erd .rel.on .mk{stroke:var(--acc);stroke-width:2.4}
.erd .tbl.on .card-bd{stroke:var(--acc);stroke-width:3}
.erd .col.hl .rowbg{fill:#ffd8a8}.erd .tbl,.erd .rel .hit{cursor:pointer}
.erd .tbl.match .card-bd{stroke:#e8590c;stroke-width:3;stroke-dasharray:6 3}
</style></head><body>
<header>
 <h1>${esc(title)}</h1>
 <span class="stat">${Object.keys(model.tables).length} tables &middot; ${model.relations.length} relations</span>
 <input type="search" id="q" placeholder="Rechercher une table ou une colonne" list="names">
 <datalist id="names">${Object.keys(model.tables).map((t) => `<option value="${esc(t)}">`).join('')}</datalist>
 <select id="mode" title="Affichage">${viewOpts}</select>
 ${hasFull ? '<label title="Dessiner en entier les liens vers les tables très référencées"><input type="checkbox" id="full"> liens hub complets</label>' : ''}
 ${hasFrames ? '<label><input type="checkbox" id="frames"> cadres par domaine</label>' : ''}
 <button id="fit" title="Ajuster à la fenêtre">Ajuster</button><button id="zin">+</button><button id="zout">&minus;</button>
 <button id="theme">Thème</button><button id="png">Export PNG</button>
 <span class="legend">${legend}</span>
</header>
<main id="main"><div id="stage">${svgs}</div>
<aside id="panel" hidden></aside>
<div class="hint">Molette : zoom &middot; glisser : déplacer &middot; survol / clic : relations d'une table &middot; Échap : tout afficher</div></main>
<script type="application/json" id="dbschema-data">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>
<script>${VIEWER}</script></body></html>`;
}
