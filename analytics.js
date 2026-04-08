// === Rent & Go Analytics Tracker ===
(function () {
  const TRACK_URL = '/api/track';
  const page = location.pathname.replace(/\/$/, '') || '/';

  function track(category, label) {
    try {
      const data = JSON.stringify({ category, label, page });
      if (navigator.sendBeacon) {
        navigator.sendBeacon(TRACK_URL, new Blob([data], { type: 'application/json' }));
      } else {
        fetch(TRACK_URL, { method: 'POST', body: data, headers: { 'Content-Type': 'application/json' }, keepalive: true });
      }
    } catch (e) { /* silent */ }
  }

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
      track('whatsapp', text || href);
      return;
    }

    // Airbnb buttons
    if (href.includes('airbnb.com') || classes.includes('btn-rental-airbnb')) {
      track('airbnb', text || href);
      return;
    }

    // Property detail pages
    if (href.includes('cocotal') || href.includes('paseo') || href.includes('karen') || href.includes('arboleda') || href.includes('costa-garden')) {
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
