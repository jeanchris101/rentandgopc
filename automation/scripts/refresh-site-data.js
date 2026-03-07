#!/usr/bin/env node
/**
 * refresh-site-data.js
 *
 * Reads latest data from automation/data/*.json and updates
 * hardcoded values in market-intel.html and roi-calculator.html.
 *
 * Run: node automation/scripts/refresh-site-data.js
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const DATA_DIR = path.join(ROOT, 'automation', 'data');
const CONFIG_PATH = path.join(ROOT, 'automation', 'config.json');

function loadJSON(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch (e) {
    console.log(`Skipping ${path.basename(filePath)}: ${e.message}`);
    return null;
  }
}

function updateMarketIntel(zones) {
  const filePath = path.join(ROOT, 'market-intel.html');
  let html = fs.readFileSync(filePath, 'utf-8');
  let changed = false;

  for (const zone of zones) {
    // Match zone block by id, update adrLow/adrHigh/occLow/occHigh
    const idPattern = new RegExp(
      `(id:'${zone.id}'[^}]*?adrLow:)\\d+(,\\s*adrHigh:)\\d+(,\\s*occLow:)\\d+(,\\s*occHigh:)\\d+`
    );
    const match = html.match(idPattern);
    if (match) {
      const replacement = `${match[1]}${zone.adr_low}${match[2]}${zone.adr_high}${match[3]}${zone.occ_low}${match[4]}${zone.occ_high}`;
      if (html !== html.replace(idPattern, replacement)) {
        html = html.replace(idPattern, replacement);
        changed = true;
        console.log(`Updated ${zone.id}: ADR $${zone.adr_low}-$${zone.adr_high}, Occ ${zone.occ_low}-${zone.occ_high}%`);
      }
    }
  }

  if (changed) {
    fs.writeFileSync(filePath, html, 'utf-8');
    console.log('market-intel.html updated.');
  } else {
    console.log('market-intel.html: no changes needed.');
  }
  return changed;
}

function updateROICalculator(stats) {
  const filePath = path.join(ROOT, 'roi-calculator.html');
  let html = fs.readFileSync(filePath, 'utf-8');
  let changed = false;
  const original = html;

  // Update default price slider value
  if (stats.median_property_price) {
    const priceVal = stats.median_property_price;
    html = html.replace(
      /(id="price"[^>]*value=")(\d+)(")/g,
      `$1${priceVal}$3`
    );
    html = html.replace(
      /(id="priceNum"[^>]*value=")(\d+)(")/g,
      `$1${priceVal}$3`
    );
    // Update display text
    const formatted = '$' + priceVal.toLocaleString('en-US');
    html = html.replace(
      /(id="priceDisplay">)\$[\d,]+(<)/,
      `$1${formatted}$2`
    );
  }

  // Update default ADR slider value
  if (stats.median_adr) {
    const adr = stats.median_adr;
    html = html.replace(
      /(id="nightly"[^>]*value=")(\d+)(")/g,
      `$1${adr}$3`
    );
    html = html.replace(
      /(id="nightlyNum"[^>]*value=")(\d+)(")/g,
      `$1${adr}$3`
    );
    html = html.replace(
      /(id="nightlyDisplay">)\$[\d]+(<)/,
      `$1$${adr}$2`
    );
  }

  changed = html !== original;
  if (changed) {
    fs.writeFileSync(filePath, html, 'utf-8');
    console.log('roi-calculator.html updated.');
  } else {
    console.log('roi-calculator.html: no changes needed.');
  }
  return changed;
}

// Main
function main() {
  console.log('=== Weekly Data Refresh ===');
  console.log(`Data dir: ${DATA_DIR}`);

  const config = loadJSON(CONFIG_PATH);
  const marketPulse = loadJSON(path.join(DATA_DIR, 'market-pulse.json'));
  const airbnbRates = loadJSON(path.join(DATA_DIR, 'airbnb-rates.json'));

  let anyChanges = false;

  // Build zone updates from airbnb-rates.json
  if (airbnbRates && airbnbRates.zones) {
    anyChanges = updateMarketIntel(airbnbRates.zones) || anyChanges;
  } else if (config) {
    console.log('No airbnb-rates.json found. Using config.json as fallback.');
    const zones = config.neighborhoods.map(n => ({
      id: n.id,
      adr_low: n.adr_range[0],
      adr_high: n.adr_range[1],
      occ_low: n.occupancy_range[0],
      occ_high: n.occupancy_range[1]
    }));
    anyChanges = updateMarketIntel(zones) || anyChanges;
  }

  // Update ROI calculator with market stats
  const stats = (marketPulse && marketPulse.stats) || (config && config.market_stats);
  if (stats) {
    anyChanges = updateROICalculator(stats) || anyChanges;
  }

  if (anyChanges) {
    console.log('\nData refresh complete. Files were updated.');
  } else {
    console.log('\nNo data changes detected.');
  }

  process.exit(0);
}

main();
