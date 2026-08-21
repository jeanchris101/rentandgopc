/**
 * El catalogo de propiedades esta repartido en seis sitios que tienen que decir
 * lo mismo:
 *
 *   automation/data/properties.json   el dato maestro
 *   automation/data/playbooks.json    los guiones de WhatsApp
 *   api/_lib/groups-plan.js           REF_CODES (cola de grupos)
 *   automation/build_queue.py         REF_CODES (bot de la Pagina)
 *   <slug>.html                       la ficha del sitio
 *   images/...                        las fotos que salen en el post
 *
 * Agregar un listing y olvidar uno de los seis no rompe nada de golpe: el bot
 * publica sin foto, o el panel de WhatsApp deja de reconocer de donde vino el
 * lead. Esta prueba lo convierte en un fallo inmediato.
 *
 *   node --test test/catalog.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const readJson = (rel) => JSON.parse(fs.readFileSync(path.join(REPO, rel), 'utf8'));
const readText = (rel) => fs.readFileSync(path.join(REPO, rel), 'utf8');

const propertiesFile = readJson('automation/data/properties.json');
const playbooksFile = readJson('automation/data/playbooks.json');

const PROPERTIES = propertiesFile.properties.filter((p) => p && p.slug && p.active !== false);
const PLAYBOOKS = playbooksFile.playbooks.filter((p) => p && p.slug);

/**
 * REF_CODES sale del texto, no de un import: groups-plan.js es ESM en un `.js`
 * y el package.json de la raiz no dice `"type": "module"` (ver la cabecera de
 * api-routes.test.mjs). Un regex sobre el literal basta y no arrastra el
 * sandbox entero.
 */
function refCodesFrom(rel, open, close) {
  const src = readText(rel);
  const start = src.indexOf(open);
  assert.notEqual(start, -1, `${rel}: no encontre el literal REF_CODES`);
  const end = src.indexOf(close, start);
  assert.notEqual(end, -1, `${rel}: el literal REF_CODES no cierra`);
  const body = src.slice(start + open.length, end);
  const out = {};
  for (const m of body.matchAll(/['"]([a-z0-9-]+)['"]\s*:\s*['"]([A-Z0-9]+)['"]/g)) {
    out[m[1]] = m[2];
  }
  return out;
}

const REF_JS = refCodesFrom('api/_lib/groups-plan.js', 'export const REF_CODES = {', '};');
const REF_PY = refCodesFrom('automation/build_queue.py', 'REF_CODES = {', '}');

/* ------------------------------------------------------------------ *
 * Codigos de ref
 * ------------------------------------------------------------------ */

test('cada propiedad activa tiene codigo de ref en los dos generadores', () => {
  for (const prop of PROPERTIES) {
    assert.ok(REF_JS[prop.slug], `${prop.slug} falta en REF_CODES de api/_lib/groups-plan.js`);
    assert.ok(REF_PY[prop.slug], `${prop.slug} falta en REF_CODES de automation/build_queue.py`);
    assert.equal(
      REF_JS[prop.slug],
      REF_PY[prop.slug],
      `${prop.slug}: groups-plan.js dice ${REF_JS[prop.slug]} y build_queue.py dice ${REF_PY[prop.slug]}`
    );
  }
});

test('los codigos de ref no se repiten', () => {
  const seen = new Map();
  for (const [slug, code] of Object.entries(REF_JS)) {
    assert.ok(!seen.has(code), `el codigo ${code} lo usan ${seen.get(code)} y ${slug}`);
    seen.set(code, slug);
  }
});

test('el ref_code del playbook coincide con REF_CODES', () => {
  for (const pb of PLAYBOOKS) {
    assert.ok(
      PROPERTIES.some((p) => p.slug === pb.slug),
      `el playbook ${pb.slug} no corresponde a ninguna propiedad activa`
    );
    assert.equal(
      pb.ref_code,
      REF_JS[pb.slug],
      `${pb.slug}: el playbook dice ${pb.ref_code} y REF_CODES dice ${REF_JS[pb.slug]}`
    );
  }
});

test('cada propiedad activa tiene playbook', () => {
  for (const prop of PROPERTIES) {
    assert.ok(
      PLAYBOOKS.some((pb) => pb.slug === prop.slug),
      `${prop.slug} no tiene guion en playbooks.json: el panel no sabria que contestar`
    );
  }
});

/* ------------------------------------------------------------------ *
 * Fotos
 * ------------------------------------------------------------------ *
 * Si esta falla justo despues de agregar un listing, no hay ningun bug: faltan
 * por subir las fotos a images/. El mensaje dice cuales.
 */

test('todas las fotos de properties.json existen en el repo', () => {
  const missing = [];
  for (const prop of PROPERTIES) {
    const refs = [prop.hero_image, ...(prop.post_images || [])].filter(Boolean);
    for (const rel of new Set(refs)) {
      if (!fs.existsSync(path.join(REPO, rel))) missing.push(`${prop.slug} -> ${rel}`);
    }
  }
  assert.deepEqual(
    missing,
    [],
    `Faltan fotos por subir. El sitio aguanta (la ficha descarta sola la lamina que no existe),\n` +
      `pero el bot de Facebook no puede publicar sin imagen: esta propiedad no debe entrar en la\n` +
      `cola de grupos hasta que esten.\n  ${missing.join('\n  ')}\n`
  );
});

test('el hero_image tambien esta en post_images', () => {
  for (const prop of PROPERTIES) {
    if (!prop.hero_image || !Array.isArray(prop.post_images) || !prop.post_images.length) continue;
    assert.ok(
      prop.post_images.includes(prop.hero_image),
      `${prop.slug}: hero_image (${prop.hero_image}) no esta en post_images, asi que la foto principal nunca sale en un post`
    );
  }
});

test('todas las fotos de las fichas del sitio existen', () => {
  const missing = [];
  for (const prop of PROPERTIES) {
    const page = `${prop.slug}.html`;
    if (!fs.existsSync(path.join(REPO, page))) continue; // lo cubre la prueba de abajo
    const html = readText(page);
    for (const m of html.matchAll(/<img[^>]+src="(images\/[^"]+)"/g)) {
      if (!fs.existsSync(path.join(REPO, m[1]))) missing.push(`${page} -> ${m[1]}`);
    }
  }
  assert.deepEqual(missing, [], `Fotos rotas en las fichas:\n  ${missing.join('\n  ')}\n`);
});

/* ------------------------------------------------------------------ *
 * Sitio
 * ------------------------------------------------------------------ */

test('cada propiedad activa tiene ficha y esta enlazada desde index.html', () => {
  const index = readText('index.html');
  for (const prop of PROPERTIES) {
    const page = `${prop.slug}.html`;
    assert.ok(fs.existsSync(path.join(REPO, page)), `falta la ficha ${page}`);
    assert.ok(index.includes(`href="${page}"`), `index.html no enlaza a ${page}`);
  }
});

/**
 * Las fichas escriben el metro cuadrado como `m<sup>2</sup>` o `&sup2;` y
 * properties.json como `m2`. Comparar en crudo daria un falso positivo en los
 * dos terrenos, asi que se normaliza el superindice antes de comparar.
 */
function flatten(text) {
  return String(text).replace(/&sup2;|²/g, '2').replace(/\s+/g, ' ');
}

test('el precio de la ficha coincide con properties.json', () => {
  for (const prop of PROPERTIES) {
    const page = `${prop.slug}.html`;
    if (!fs.existsSync(path.join(REPO, page)) || !prop.price_display) continue;
    assert.ok(
      flatten(readText(page)).includes(flatten(prop.price_display)),
      `${page} no muestra ${prop.price_display}: la ficha y el bot dirian precios distintos`
    );
  }
});

test('los links de wa.me de cada ficha llevan el ref de esa propiedad', () => {
  for (const prop of PROPERTIES) {
    const page = `${prop.slug}.html`;
    if (!fs.existsSync(path.join(REPO, page))) continue;
    const html = readText(page);
    const refs = [...html.matchAll(/RG-([A-Z0-9]{2,6})-([FGPWID][A-Z0-9]{1,5})/g)];
    assert.ok(refs.length > 0, `${page} no tiene ningun link de WhatsApp con ref`);
    for (const m of refs) {
      assert.equal(
        m[1],
        REF_JS[prop.slug],
        `${page}: el ref ${m[0]} usa el codigo ${m[1]}, pero esta propiedad es ${REF_JS[prop.slug]}`
      );
    }
  }
});
