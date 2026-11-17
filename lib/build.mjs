// model.json -> vues (layout) -> controles -> <nom>.html + <nom>.png (+ _build/ pour le debogage).
// Usage : node build.mjs <model.json> <dossier_sortie> <nom> [--frames] [--hub=8|off] [--title="..."]
// Code de sortie 1 si une vue echoue aux controles (rien n'est ecrit hors _build/).
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { layout, STYLES, shortType } from './layout.mjs';
import { check, BLOCKING } from './check.mjs';
import { staticPage, interactivePage } from './render.mjs';
import { renderSvg, SVG_CSS } from './svg.mjs';

const [, , modelPath, outDir, name, ...rest] = process.argv;
const opt = Object.fromEntries(rest.map((a) => { const [k, ...v] = a.replace(/^--/, '').split('='); return [k, v.length ? v.join('=') : true]; }));
const hub = opt.hub === 'off' ? 'off' : opt.hub ? Number(opt.hub) : 8;
const model = JSON.parse(fs.readFileSync(modelPath, 'utf8'));
const build = path.join(outDir, '_build');
fs.mkdirSync(build, { recursive: true });

const chrome = [process.env.DBSCHEMA_CHROME, 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', '/usr/bin/google-chrome', '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find((p) => p && fs.existsSync(p));
const fileUrl = (p) => 'file:///' + path.resolve(p).replace(/\\/g, '/');
// page -> Chrome headless -> contenu JSON du <pre id="out"> ecrit par le script de la page
function inChrome(file, html) {
  fs.writeFileSync(file, html);
  const dom = execFileSync(chrome, ['--headless=new', '--disable-gpu', '--dump-dom', fileUrl(file)], { encoding: 'utf8', maxBuffer: 1 << 28 });
  const m = dom.match(/<pre id="out">([\s\S]*?)<\/pre>/);
  return m ? JSON.parse(m[1].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&')) : null;
}

// Largeur de chaque caractere du modele, dans chaque style, mesuree par le navigateur (police reelle, alphabets non latins)
let cw;
if (chrome) {
  const chars = new Set('→ Indexes()·+col.0123456789N');
  const add = (s) => { for (const ch of String(s)) chars.add(ch); };
  for (const t of Object.values(model.tables)) { add(t.name); for (const c of t.columns) { add(c.name); add(shortType(c)); } }
  for (const r of model.relations) { add(r.to); add(r.card_parent); add(r.card_child); }
  cw = inChrome(path.join(build, 'charwidths.html'), `<!doctype html><meta charset="utf-8"><body>
<svg xmlns="http://www.w3.org/2000/svg" font-family="Tahoma, 'Segoe UI', sans-serif"><text id="t" style="white-space:pre"></text></svg>
<script>const C=${JSON.stringify([...chars])},S=${JSON.stringify(STYLES)},t=document.getElementById('t'),out={};
for(const k in S){t.setAttribute('style','white-space:pre;'+S[k]);const m=out[k]={};let mx=0;
for(const ch of C){t.textContent=ch.repeat(10);m[ch]=t.getComputedTextLength()/10;mx=Math.max(mx,m[ch])}m.__fallback=mx}
const p=document.createElement('pre');p.id='out';p.textContent=JSON.stringify(out);document.body.appendChild(p)</script>`);
  if (!cw) { console.log('ECHEC : mesure des largeurs de texte impossible (Chrome --dump-dom)'); process.exit(1); }
  fs.writeFileSync(path.join(build, 'charwidths_measured.json'), JSON.stringify(cw));
  console.log(`[texte] largeurs mesurees dans Chrome : ${chars.size} caracteres x ${Object.keys(STYLES).length} styles`);
} else console.log('[texte] ni Chrome ni Edge (DBSCHEMA_CHROME) : largeurs de la table Tahoma figee, debordement non mesure');

const specs = [
  { id: 'all', label: 'Toutes les colonnes', o: { mode: 'all', hub } },
  { id: 'keys', label: 'Clés seules', o: { mode: 'keys', hub } },
  { id: 'names', label: 'Noms seuls', o: { mode: 'names', hub } },
];
const views = [];
let failed = false;
for (const s of specs) {
  let lay = await layout(model, { ...s.o, cw }), res = check(lay), spacing = 1;
  if (!res.ok) { spacing = 1.4; lay = await layout(model, { ...s.o, cw, spacing }); res = check(lay); }
  fs.writeFileSync(path.join(build, `layout_${s.id}.json`), JSON.stringify(lay));
  fs.writeFileSync(path.join(build, `check_${s.id}.json`), JSON.stringify(res, null, 1));
  const n = (k) => res[k].length;
  console.log(`[${s.id}] ${Math.round(lay.width)}x${Math.round(lay.height)} espacement=${spacing} ` + BLOCKING.map((k) => `${k}=${n(k)}`).join(' ') + ` croisements=${res.crossings} -> ${res.ok ? 'OK' : 'ECHEC'}`);
  if (!res.ok) { failed = true; for (const k of BLOCKING) for (const x of res[k]) console.log(`   ${k}: ${x}`); }
  views.push({ id: s.id, label: s.label, layout: lay });
  // variantes de la vue principale
  if (s.id === 'all' && lay.hubs.length) specs.push({ id: 'all-full', label: 'Liens hub complets', o: { mode: 'all', hub: 'off' } });
  if (s.id === 'all' && opt.frames && Object.keys(model.groups ?? {}).length) specs.push({ id: 'all-frames', label: 'Cadres', o: { mode: 'all', hub, frames: true } });
}
if (failed) { console.log('ECHEC des controles : aucun livrable ecrit (details dans ' + build + ')'); process.exit(1); }

// Debordement de texte mesure par le navigateur (les largeurs de carte viennent d'une table de chasse Tahoma) : bloquant
if (chrome) {
  const MEASURE = `<script>const out=[];for(const S of document.querySelectorAll('svg'))for(const T of S.querySelectorAll('.tbl')){
const c=T.querySelector('.card-bg').getBBox(),right=c.x+c.width;
for(const t of T.querySelectorAll('text')){const b=t.getBBox();if(b.x+b.width>right-2||b.x<c.x+1)out.push(S.dataset.view+' '+T.dataset.table+' : "'+t.textContent+'" deborde')}
for(const r of T.querySelectorAll('.col')){const n=r.querySelector('.cn').getBBox(),y=r.querySelector('.ct').getBBox();if(n.x+n.width>y.x-4)out.push(S.dataset.view+' '+T.dataset.table+'.'+r.dataset.col+' : nom et type se touchent')}}
const p=document.createElement('pre');p.id='out';p.textContent=JSON.stringify(out);document.body.appendChild(p)</script>`;
  const over = inChrome(path.join(build, 'measure.html'), `<!doctype html><html><head><meta charset="utf-8"><style>${SVG_CSS}</style></head><body>`
    + views.map((v) => renderSvg(model, v.layout).replace('<svg ', `<svg data-view="${v.id}" `)).join('\n') + MEASURE + '</body></html>');
  if (!over) { console.log('ECHEC : mesure du texte impossible (Chrome --dump-dom)'); process.exit(1); }
  console.log(`[texte] debordements mesures dans Chrome (${views.length} vues) : ${over.length} -> ${over.length ? 'ECHEC' : 'OK'}`);
  if (over.length) { for (const x of over.slice(0, 20)) console.log('   ' + x); console.log('ECHEC : aucun livrable ecrit'); process.exit(1); }
}

const title = opt.title ?? name;
const htmlPath = path.join(outDir, name + '.html');
fs.writeFileSync(htmlPath, interactivePage(model, views, { title }));
const main = views[0].layout;
const staticPath = path.join(build, 'static_all.html');
fs.writeFileSync(staticPath, staticPage(model, main));

const pngPath = path.join(outDir, name + '.png');
if (!chrome) console.log('PNG non produit : ni Chrome ni Edge trouves (DBSCHEMA_CHROME)');
else {
  const W = Math.ceil(main.width), H = Math.ceil(main.height);
  execFileSync(chrome, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=2',
    `--window-size=${W},${H}`, '--screenshot=' + path.resolve(pngPath), fileUrl(staticPath)], { stdio: 'ignore' });
  console.log(`PNG ${pngPath} (${W * 2}x${H * 2})`);
}
console.log(`HTML ${htmlPath} (${Math.round(fs.statSync(htmlPath).size / 1024)} Ko, vues : ${views.map((v) => v.id).join(', ')})`);
