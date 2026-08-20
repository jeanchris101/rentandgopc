/**
 * popup.js — FB Cookie Export
 * Grabs facebook.com cookies via chrome.cookies API and exports as JSON
 */

const $ = (sel) => document.querySelector(sel);

let lastCookieData = null;

// Load last export time on open
async function init() {
  const data = await chrome.storage.local.get(['lastExportTime', 'lastCookieCount']);
  if (data.lastExportTime) {
    showLastExport(data.lastExportTime, data.lastCookieCount || 0);
  }
}

function showLastExport(isoTime, count) {
  const d = new Date(isoTime);
  const timeStr = d.toLocaleString();
  $('#lastExport').textContent = `Last export: ${timeStr} (${count} cookies)`;
}

function setStatus(text, type) {
  const el = $('#status');
  el.textContent = text;
  el.className = 'status ' + type;
}

async function getCookies() {
  return new Promise((resolve, reject) => {
    chrome.cookies.getAll({ domain: '.facebook.com' }, (cookies) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(cookies);
    });
  });
}

function formatCookies(rawCookies) {
  const now = new Date().toISOString();

  const cookies = rawCookies.map(c => {
    const entry = {
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      httpOnly: c.httpOnly,
      secure: c.secure,
    };

    // Map Chrome sameSite to Playwright format
    // Note: "None" requires secure=true per spec; default unspecified to "Lax"
    if (c.sameSite === 'no_restriction') {
      entry.sameSite = 'None';
    } else if (c.sameSite === 'lax') {
      entry.sameSite = 'Lax';
    } else if (c.sameSite === 'strict') {
      entry.sameSite = 'Strict';
    } else {
      // Chrome returns "unspecified" for cookies with no sameSite attribute.
      // Using "Lax" (browser default) instead of "None" because
      // sameSite=None requires secure=true, which not all cookies have.
      entry.sameSite = 'Lax';
    }

    // Include expiry if present
    if (c.expirationDate) {
      entry.expires = c.expirationDate;
    }

    return entry;
  });

  return {
    exported_at: now,
    cookies: cookies,
  };
}

// --- Export button ---
$('#exportBtn').addEventListener('click', async () => {
  try {
    setStatus('Fetching cookies...', 'ready');

    const rawCookies = await getCookies();

    if (rawCookies.length === 0) {
      setStatus('Error: open facebook.com first', 'error');
      return;
    }

    lastCookieData = formatCookies(rawCookies);
    const jsonStr = JSON.stringify(lastCookieData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    // Download as fb-cookies.json
    chrome.downloads.download({
      url: url,
      filename: 'fb-cookies.json',
      conflictAction: 'overwrite',
      saveAs: false,
    }, (downloadId) => {
      URL.revokeObjectURL(url);
      if (chrome.runtime.lastError) {
        // If auto-download fails, fall back to saveAs
        const url2 = URL.createObjectURL(blob);
        chrome.downloads.download({
          url: url2,
          filename: 'fb-cookies.json',
          conflictAction: 'overwrite',
          saveAs: true,
        }, () => URL.revokeObjectURL(url2));
      }
    });

    // Save to storage
    const exportTime = lastCookieData.exported_at;
    await chrome.storage.local.set({
      lastExportTime: exportTime,
      lastCookieCount: rawCookies.length,
      lastCookieData: lastCookieData,
    });

    setStatus(`Exported! (${rawCookies.length} cookies)`, 'success');
    showLastExport(exportTime, rawCookies.length);

  } catch (err) {
    setStatus('Error: ' + err.message, 'error');
  }
});

// --- Copy button ---
$('#copyBtn').addEventListener('click', async () => {
  try {
    // Use cached data or fetch fresh
    let data = lastCookieData;
    if (!data) {
      const stored = await chrome.storage.local.get(['lastCookieData']);
      data = stored.lastCookieData;
    }
    if (!data) {
      // Fetch fresh if nothing cached
      const rawCookies = await getCookies();
      if (rawCookies.length === 0) {
        setStatus('Error: open facebook.com first', 'error');
        return;
      }
      data = formatCookies(rawCookies);
    }

    const jsonStr = JSON.stringify(data, null, 2);
    await navigator.clipboard.writeText(jsonStr);
    setStatus('Copied to clipboard!', 'success');

  } catch (err) {
    setStatus('Error: ' + err.message, 'error');
  }
});

// --- Init ---
init();
