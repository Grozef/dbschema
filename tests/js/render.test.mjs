// renderSvg / interactivePage : tout texte du schema est echappe, la page n'a ni ressource externe ni <script> refermable.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { layout } from '../../lib/layout.mjs';
import { renderSvg } from '../../lib/svg.mjs';
import { interactivePage, staticPage } from '../../lib/render.mjs';
import { mini } from './helpers.mjs';

const EVIL_T = '<img src=x onerror=alert(1)>', EVIL_C = '"><svg onload=alert(2)>', EVIL_S = '</script><script>alert(3)</script>';

async function evil() {
  const m = mini({ [EVIL_T]: [EVIL_C], child: ['p_id'] }, [['child', 'p_id', EVIL_T, 'id']], { ['G<b>' + EVIL_S]: [EVIL_T] });
  m.tables[EVIL_T].comment = EVIL_S + ' javascript:alert(4)';
  m.tables[EVIL_T].columns[1].comment = EVIL_S;
  m.tables[EVIL_T].columns[1].default = EVIL_S;
  m.tables[EVIL_T].columns[1].type = "enum('<x>','</script>')";
  return { m, lay: await layout(m) };
}

test('SVG : noms, groupes et types echappes', async () => {
  const { m, lay } = await evil();
  const svg = renderSvg(m, lay);
  for (const raw of [EVIL_T, EVIL_C, '<b>', '<script>', '</script>', "'<x>'"]) assert.ok(!svg.includes(raw), raw);
  assert.ok(svg.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(svg.includes('&quot;&gt;&lt;svg onload=alert(2)&gt;'));
});

test('page interactive : CSP stricte, aucune ressource externe', async () => {
  const { m, lay } = await evil();
  const html = interactivePage(m, [{ id: 'all', label: 'Toutes', layout: lay }], { title: EVIL_S });
  const csp = html.match(/Content-Security-Policy" content="([^"]+)"/)[1];
  for (const d of ["default-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'"]) assert.ok(csp.includes(d), d);
  assert.ok(!/\b(src|href)=["']?(https?:)?\/\//i.test(html), 'ressource externe');
});

test("CSP : script autorise par son empreinte, pas de 'unsafe-inline' pour les scripts", async () => {
  const { m, lay } = await evil();
  const html = interactivePage(m, [{ id: 'all', label: 'Toutes', layout: lay }], { title: EVIL_S });
  const csp = html.match(/Content-Security-Policy" content="([^"]+)"/)[1];
  const scriptSrc = csp.split(';').map((d) => d.trim()).find((d) => d.startsWith('script-src'));
  assert.ok(!scriptSrc.includes('unsafe-inline'), scriptSrc);
  const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const sha = 'sha256-' + createHash('sha256').update(code, 'utf8').digest('base64');
  assert.equal(scriptSrc, `script-src '${sha}'`);
  // le navigateur calcule l'empreinte APRES normalisation CRLF -> LF : le texte insere ne doit contenir aucun CR
  assert.ok(!code.includes('\r'), 'CR dans le script insere : empreinte fausse dans le navigateur (clone Windows autocrlf)');
  assert.equal(code, readFileSync(new URL('../../assets/viewer.js', import.meta.url), 'utf8').replace(/\r\n?/g, '\n'));
});

test('page interactive : 1 script executable + 1 bloc de donnees, jamais refermes par une donnee', async () => {
  const { m, lay } = await evil();
  const html = interactivePage(m, [{ id: 'all', label: 'Toutes', layout: lay }], { title: EVIL_S });
  assert.equal((html.match(/<script/gi) || []).length, 2);
  assert.equal((html.match(/<\/script/gi) || []).length, 2);
  assert.ok(!html.includes('alert(3)</script>'));
  // les donnees embarquees se relisent a l'identique (JSON.parse du bloc application/json dans la page)
  const raw = html.match(/<script type="application\/json" id="dbschema-data">([\s\S]*?)<\/script>/)[1];
  assert.ok(!raw.includes('<'));
  const D = JSON.parse(raw);
  assert.ok(Object.hasOwn(D.tables, EVIL_T));
  assert.equal(D.tables[EVIL_T].comment, EVIL_S + ' javascript:alert(4)');
  assert.equal(D.file, '_script_script_alert_3_script_'); // titre '</script><script>alert(3)</script>', [^\w.-]+ -> _
});

test('page statique (PNG) : meme echappement', async () => {
  const { m, lay } = await evil();
  const html = staticPage(m, lay);
  assert.ok(!html.includes(EVIL_T) && !html.includes('<script'));
});
