/**
 * pixel.js — Meta (Facebook) Pixel loader for Rent & Go PC
 *
 * Replaces the inline pixel snippet that used to be duplicated in the <head>
 * of 12 pages. Include it once per page, in <head>:
 *
 *     <script src="pixel.js"></script>
 *
 * Pages keep firing their own events the same way they always did:
 *
 *     if (typeof fbq === 'function') { fbq('track', 'Lead', {...}); }
 *
 * While the ID below is still the placeholder, `fbq` is never defined, so
 * those guards are false and nothing fires. Nothing is requested from
 * Facebook either.
 */
(function () {
    'use strict';

    /* =====================================================================
     * >>> EDIT THIS ONE LINE <<<
     * Paste the real Meta Pixel ID (digits only, e.g. '1234567890123456').
     * Until then leave it exactly as-is and the pixel stays fully off.
     * ===================================================================== */
    var META_PIXEL_ID = 'YOUR_PIXEL_ID_HERE';
    /* ===================================================================== */

    var PLACEHOLDER = 'YOUR_PIXEL_ID_HERE';

    // Not configured yet: load nothing, define nothing, fire nothing.
    // (Before this file existed, all 12 pages downloaded fbevents.js and
    // called fbq('init', 'YOUR_PIXEL_ID_HERE') on every single page load.)
    if (!META_PIXEL_ID || META_PIXEL_ID === PLACEHOLDER) {
        return;
    }

    // Standard Meta Pixel base code.
    !function (f, b, e, v, n, t, s) {
        if (f.fbq) return;
        n = f.fbq = function () {
            n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
        };
        if (!f._fbq) f._fbq = n;
        n.push = n; n.loaded = !0; n.version = '2.0'; n.queue = [];
        t = b.createElement(e); t.async = !0; t.src = v;
        s = b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t, s);
    }(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');

    fbq('init', META_PIXEL_ID);
    fbq('track', 'PageView');

    // Note: the old inline blocks also carried a <noscript><img ...></noscript>
    // fallback. That fallback is intentionally not reproduced here — this file
    // is JavaScript, so with JavaScript disabled it never runs and could never
    // emit the tag anyway. If the no-JS fallback is ever needed, it has to go
    // back into the HTML of each page as static markup.
})();
