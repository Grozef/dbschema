// Points d'entree en ligne de commande de layout.mjs et check.mjs, et rendu SVG des cadres et des amorces hub.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { layout } from '../../lib/layout.mjs';
import { renderSvg } from '../../lib/svg.mjs';
import { FIX, loadModel } from './helpers.mjs';

const LIB = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'lib');
const node = (...args) => spawnSync(process.execPath, args, { encoding: 'utf8' });

test('layout.mjs puis check.mjs en ligne de commande : OK, puis ECHEC (code 1) sur un layout casse', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dbschema-cli-'));
  const out = path.join(dir, 'lay.json');
  const r1 = node(path.join(LIB, 'layout.mjs'), path.join(FIX, 'edge.model.json'), out, '--mode=names', '--hub=3');
  assert.equal(r1.status, 0, r1.stderr);
  assert.match(r1.stdout, /mode=names tables=26 /);
  const r2 = node(path.join(LIB, 'check.mjs'), out, '--details');
  assert.equal(r2.status, 0, r2.stdout);
  assert.match(r2.stdout, /-> OK/);
  const lay = JSON.parse(fs.readFileSync(out, 'utf8'));
  lay.edges.pop();
  fs.writeFileSync(out, JSON.stringify(lay));
  const r3 = node(path.join(LIB, 'check.mjs'), out, '--details');
  assert.equal(r3.status, 1);
  assert.match(r3.stdout, /ECHEC/);
  assert.match(r3.stdout, /\[incomplete\]/);
});

test('SVG : cadres par domaine et amorces hub dessines', async () => {
  const m = loadModel('demo.model.json');
  const lay = await layout(m, { frames: true, hub: 3 });
  assert.ok(lay.splits.length > 0 && Object.keys(lay.groups).length > 0);
  const svg = renderSvg(m, lay);
  assert.equal((svg.match(/<g class="grp"/g) || []).length, Object.keys(lay.groups).length);
  assert.equal((svg.match(/<g class="rel split"/g) || []).length, lay.splits.length);
});
