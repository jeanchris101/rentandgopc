// === Rent & Go Analytics Tracker ===
(function () {
  const TRACK_URL = '/api/track';
  const LEAD_URL = '/api/lead/capture';
  const page = location.pathname.replace(/\/$/, '') || '/';

  // Same shape api/_lib/classify.js parses: RG-<code>-<sourceLetter><suffix>.
  // Kept in sync by hand; if the ref format changes, change it in both places.
  const REF_RE = /RG-[A-Z0-9]{2,6}-[FGPWID][A-Z0-9]{1,5}/i;

  const VISITOR_KEY = 'rg_vid';
  const ATTR_KEY = 'rg_attr';
  const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];

  /* ---------------------------------------------------------------- transport */

  // sendBeacon is queued by the browser and survives the navigation that a click
  // is about to start, so it is the only safe way to report a click on an <a>.
  // Never replace it with an awaited fetch: the page is gone before it resolves.
  function beacon(url, payload) {
    try {
      const data = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        return navigator.sendBeacon(url, new Blob([data], { type: 'application/json' }));
      }
      // keepalive is the fetch equivalent for older browsers. Fire and forget.
      fetch(url, {
        method: 'POST',
        body: data,
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
      });
    } catch (e) { /* silent */ }
    return false;
  }

  // `page` rides along on every event, so the origin page is always recorded.
  function track(category, label) {
    beacon(TRACK_URL, { category, label, page });
  }

  /* ---------------------------------------------------------------- identity */

  function lsGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function lsSet(key, value) {
    // Private mode and blocked storage throw on write; losing the id is fine,
    // throwing inside a click handler is not.
    try { localStorage.setItem(key, value); } catch (e) { /* silent */ }
  }

  function uuid() {
    try {
      if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    } catch (e) { /* fall through */ }
    // randomUUID needs a secure context; this covers http and older browsers.
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  // Stable per-browser id. Without it two clicks from the same person look like
  // two different leads and there is no way to join a click to the WhatsApp
  // conversation it produced. Not a login, no PII in it.
  function visitorId() {
    let id = lsGet(VISITOR_KEY);
    if (!id) {
      id = uuid();
      lsSet(VISITOR_KEY, id);
    }
    return id;
  }

  /* ------------------------------------------------------------- attribution */

  // The utm_*/fbclid params land on the entry page, but the WhatsApp click
  // usually happens two pages later. Remember the first touch or the campaign
  // is lost exactly on the event that matters.
  function attribution() {
    let current = {};
    try {
      const params = new URLSearchParams(location.search);
      UTM_KEYS.concat('fbclid').forEach(function (k) {
        const v = params.get(k);
        if (v) current[k] = v.slice(0, 200);
      });
    } catch (e) { current = {}; }

    if (Object.keys(current).length) {
      lsSet(ATTR_KEY, JSON.stringify(current));
      return current;
    }

    try {
      const stored = JSON.parse(lsGet(ATTR_KEY) || '{}');
      return stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {};
    } catch (e) { return {}; }
  }

  // /cocotal-2bdr.html -> "cocotal-2bdr". The home page is not a property, so it
  // deliberately returns nothing and the caller falls through to "unknown".
  function pageSlug() {
    const last = (location.pathname.split('/').pop() || '').trim();
    const slug = last.replace(/\.html?$/i, '');
    return slug && slug !== 'index' ? slug : '';
  }

  // The ref lives inside the prefilled WhatsApp message (?text=...), URL-encoded.
  function refFromHref(href) {
    if (!href) return null;
    let text = href;
    const m = /[?&]text=([^&#]*)/i.exec(href);
    if (m) {
      try { text = decodeURIComponent(m[1].replace(/\+/g, ' ')); } catch (e) { text = m[1]; }
    }
    const found = REF_RE.exec(text);
    return found ? found[0].toUpperCase() : null;
  }

  // Public endpoint, same beacon: this must not delay the jump to WhatsApp.
  function captureLead(extra) {
    beacon(
      LEAD_URL,
      Object.assign(
        {
          source: 'wa-click',
          page: page,
          referrer: document.referrer || '',
          visitorId: visitorId(),
        },
        attribution(),
        extra || {}
      )
    );
  }

  /* ---------------------------------------------------------------- events */

  // Track page view on load
  track('pageview', page);

  // Delegate clicks from the whole document
  document.addEventListener('click', function (e) {
    const link = e.target.closest('a, button');
    if (!link) return;

    const href = link.getAttribute('href') || '';
    const text = link.textContent.trim().substring(0, 60);
    const classes = link.className || '';

    // WhatsApp buttons
    if (href.includes('wa.me') || classes.includes('btn-rental-wa') || classes.includes('whatsapp')) {
      // data-prop is what the link itself declares about the property; the page
      // slug covers links that were never tagged. Both beat textContent, which
      // collapsed the 7 buttons on the home page into a single bucket called
      // "WhatsApp" — you could see the clicks but not which listing sold them.
      const prop = (link.getAttribute('data-prop') || '').trim() || pageSlug() || 'unknown';
      track('whatsapp', prop);
      captureLead({ propertySlug: prop, ref: refFromHref(href) });
      return;
    }

    // Airbnb buttons
    if (href.includes('airbnb.com') || classes.includes('btn-rental-airbnb')) {
      track('airbnb', text || href);
      return;
    }

    // Property detail pages
    if (href.includes('cocotal') || href.includes('paseo') || href.includes('karen') || href.includes('arboleda') || href.includes('costa')) {
      track('property', text || href);
      return;
    }

    // Navigation links
    if (link.closest('.nav') || link.closest('nav')) {
      track('navigation', text || href);
      return;
    }

    // Tool links (ROI calculator, buying guide, etc.)
    if (href.includes('roi-calculator') || href.includes('buying-guide') || href.includes('cost-of-living') || href.includes('confotur') || href.includes('neighborhoods')) {
      track('tool', text || href);
      return;
    }

    // Footer links
    if (link.closest('.footer')) {
      track('footer', text || href);
      return;
    }

    // Language selector
    if (classes.includes('lang-btn')) {
      track('language', link.dataset.lang || text);
      return;
    }

    // CTA / hero buttons
    if (classes.includes('btn') && !classes.includes('btn-rental')) {
      track('cta', text || href);
      return;
    }
  });
})();
