/**
 * Lo que un comprador ve antes de abrir la pagina: el titulo en Google, la
 * miniatura al compartir por WhatsApp, y en que dominio aterriza.
 *
 * Todo esto se rompe en silencio. Una og:image apuntando a un 404 no da error
 * en ningun lado: simplemente el link que mandas por WhatsApp sale sin foto, y
 * nadie se entera hasta que un lead no entra. Paso de verdad con la ficha de
 * US$310,000.
 *
 *   node --test test/seo.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASE = 'https://www.rentandgopc.com';

const readText = (rel) => fs.readFileSync(path.join(REPO, rel), 'utf8');
const existe = (rel) => fs.existsSync(path.join(REPO, rel));

/** Las que puede ver un comprador. El resto son paneles con contrasena. */
const PUBLICAS = [
  'index.html',
  'costa-bavaro-garden.html',
  'cocotal-2bdr-furnished.html',
  'cocotal-2bdr.html',
  'paseo-cocotal.html',
  'karen-los-corales.html',
  'land-autovia-este.html',
  'land-cepm-vistacana.html',
  'neighborhoods.html',
  'blog.html',
  'buying-guide-2026.html',
  'roi-calculator.html',
  'confotur-calculator.html',
  'cost-of-living.html',
  'guide-download.html',
  'try-before-you-buy.html',
  'guest-investor.html',
  'blog-roi-calculator.html',
];

const PANELES = [
  'admin.html', 'airbnb-dashboard.html', 'calendar.html', 'group-assist.html',
  'group-queue.html', 'group-research.html', 'hub.html', 'market-intel.html',
  'post-generator.html', 'response-bank.html', 'status.html', 'strategy.html',
  'whatsapp.html',
];

/* ------------------------------------------------------------------ *
 * Cabeceras
 * ------------------------------------------------------------------ */

test('cada pagina publica tiene titulo y descripcion', () => {
  for (const p of PUBLICAS) {
    const html = readText(p);
    const titulo = /<title>([^<]+)<\/title>/.exec(html);
    assert.ok(titulo && titulo[1].trim(), `${p} no tiene <title>`);
    assert.ok(
      /<meta name="description" content="[^"]{40,}"/.test(html),
      `${p} no tiene meta description util (minimo 40 caracteres)`
    );
  }
});

/**
 * El mismo HTML se sirve en rentandgopc.com, www.rentandgopc.com y en el
 * dominio de Vercel. Sin canonical, Google reparte la autoridad entre los tres
 * y elige el que quiera.
 */
test('cada pagina publica declara su canonical en el dominio con www', () => {
  for (const p of PUBLICAS) {
    const m = /<link rel="canonical" href="([^"]+)"/.exec(readText(p));
    assert.ok(m, `${p} no tiene <link rel="canonical">`);
    const esperado = p === 'index.html' ? `${BASE}/` : `${BASE}/${p}`;
    assert.equal(m[1], esperado, `${p}: canonical apunta a ${m[1]}`);
  }
});

/**
 * Esta es la que importa de verdad: todo el embudo son links de wa.me y de
 * Facebook. Un link sin miniatura convierte muchisimo peor.
 */
test('cada og:image apunta a un archivo que existe', () => {
  const rotas = [];
  for (const p of [...PUBLICAS, ...PANELES].filter(existe)) {
    for (const m of readText(p).matchAll(/<meta property="og:image" content="([^"]+)"/g)) {
      const rel = m[1].replace(`${BASE}/`, '');
      if (!existe(rel)) rotas.push(`${p} -> ${m[1]}`);
    }
  }
  assert.deepEqual(rotas, [], `og:image rota (el link sale sin foto):\n  ${rotas.join('\n  ')}\n`);
});

test('cada pagina publica tiene og:image', () => {
  for (const p of PUBLICAS) {
    assert.ok(
      /<meta property="og:image"/.test(readText(p)),
      `${p} no tiene og:image: al compartirla no sale miniatura`
    );
  }
});

/* ------------------------------------------------------------------ *
 * Indexacion
 * ------------------------------------------------------------------ */

test('robots.txt existe y deja los paneles fuera del indice', () => {
  assert.ok(existe('robots.txt'), 'falta robots.txt');
  const robots = readText('robots.txt');
  for (const panel of PANELES) {
    assert.ok(robots.includes(`Disallow: /${panel}`), `robots.txt no bloquea ${panel}`);
  }
  assert.ok(robots.includes('Disallow: /api/'), 'robots.txt no bloquea /api/');
  assert.ok(robots.includes(`Sitemap: ${BASE}/sitemap.xml`), 'robots.txt no declara el sitemap');
});

test('el sitemap lista exactamente las paginas publicas', () => {
  assert.ok(existe('sitemap.xml'), 'falta sitemap.xml');
  const xml = readText('sitemap.xml');
  const enElSitemap = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);

  for (const p of PUBLICAS) {
    const esperado = p === 'index.html' ? `${BASE}/` : `${BASE}/${p}`;
    assert.ok(enElSitemap.includes(esperado), `el sitemap no lista ${p}`);
  }
  for (const panel of PANELES) {
    assert.ok(
      !enElSitemap.some((u) => u.endsWith(panel)),
      `el sitemap lista ${panel}, que es un panel interno`
    );
  }
});

/* ------------------------------------------------------------------ *
 * Dominio
 * ------------------------------------------------------------------ */

test('nada apunta al dominio viejo de Vercel', () => {
  const culpables = [];
  const archivos = [...PUBLICAS, ...PANELES, 'llms.txt', 'robots.txt', 'sitemap.xml'].filter(existe);
  for (const f of archivos) {
    if (readText(f).includes('puntacana-properties.vercel.app')) culpables.push(f);
  }
  assert.deepEqual(
    culpables,
    [],
    `siguen apuntando a puntacana-properties.vercel.app: ${culpables.join(', ')}`
  );
});
