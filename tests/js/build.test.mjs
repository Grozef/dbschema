// build.mjs en sous-processus (sa couverture est alors mesuree par node --test --experimental-test-coverage), sans navigateur :
// vues controlees, HTML ecrit, pas de PNG ; --hub=off ; --title ; modele qui ne passe pas les controles -> code 1, rien ecrit.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FIX } from './helpers.mjs';

const BUILD = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'lib', 'build.mjs');
const build = (model, out, ...args) => spawnSync(process.execPath, [BUILD, model, out, 'T', ...args],
  { encoding: 'utf8', env: { ...process.env, DBSCHEMA_CHROME: 'none' } });

test('build sans navigateur : vues OK, HTML ecrit avec le titre, pas de PNG, --hub=off', () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'dbschema-build-'));
  const r = build(path.join(FIX, 'edge.model.json'), out, '--hub=off', '--title=Mon <titre>');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /\[all\] .* -> OK/);
  assert.doesNotMatch(r.stdout, /\[all-full\]/); // hub off : pas de vue "liens hub complets"
  assert.match(r.stdout, /PNG non produit/);
  const html = fs.readFileSync(path.join(out, 'T.html'), 'utf8');
  assert.match(html, /<title>Mon &lt;titre&gt;<\/title>/);
  assert.ok(!fs.existsSync(path.join(out, 'T.png')));
});

// Constat : c'est ELK qui leve (« Referenced shape does not exist »), pas un controle de build.mjs ; le modele vient
// normalement d'extract.py et ne peut pas contenir de relation vers une table absente. Seule garantie testee : rien n'est livre.
test('modele incoherent (relation vers une table absente) : echec, aucun livrable', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dbschema-build-'));
  const m = JSON.parse(fs.readFileSync(path.join(FIX, 'edge.model.json'), 'utf8'));
  m.relations[0].to = 'table_absente'; // relation vers une table inconnue : le lien n'est ni trace ni controlable
  const mp = path.join(dir, 'm.json');
  fs.writeFileSync(mp, JSON.stringify(m));
  const r = build(mp, path.join(dir, 'out'));
  assert.notEqual(r.status, 0);
  assert.ok(!fs.existsSync(path.join(dir, 'out', 'T.html')));
});

test('build avec navigateur : largeurs mesurees, debordement mesure, PNG ecrit (saute sans navigateur)', (t) => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'dbschema-build-'));
  const env = { ...process.env };
  if (env.DBSCHEMA_CHROME === 'none') delete env.DBSCHEMA_CHROME;
  const r = spawnSync(process.execPath, [BUILD, path.join(FIX, 'edge.model.json'), out, 'T'], { encoding: 'utf8', env });
  if (/ni Chrome, Edge ni Chromium/.test(r.stdout)) return t.skip('aucun navigateur sur ce poste');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /\[texte\] largeurs mesurees dans Chrome/);
  assert.match(r.stdout, /\[texte\] debordements mesures dans Chrome \(\d vues\) : 0 -> OK/);
  const png = fs.readFileSync(path.join(out, 'T.png'));
  assert.equal(png.subarray(1, 4).toString(), 'PNG');
});
