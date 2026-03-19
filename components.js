/**
 * components.js — Centralized header, footer, and Meta Pixel for Rent & Go PC
 *
 * USAGE: In each page, replace the full <header> and <footer> blocks with placeholder divs,
 * then include this script BEFORE translations.js and script.js:
 *
 *   <body>
 *       <div id="site-header"></div>
 *
 *       <!-- ... page content ... -->
 *
 *       <div id="site-footer"></div>
 *
 *       <script src="components.js"></script>
 *       <script src="translations.js"></script>
 *       <script src="script.js"></script>
 *   </body>
 *
 * The script auto-runs on load: injects header, footer, Meta Pixel, and marks
 * the active nav link based on the current page URL.
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Configuration
    // -------------------------------------------------------------------------

    var META_PIXEL_ID = 'YOUR_PIXEL_ID_HERE';

    var NAV_LINKS = [
        { href: 'index.html',            anchor: '#properties', i18nKey: 'nav_properties', label: 'Properties' },
        { href: 'index.html',            anchor: '#rentals',    i18nKey: null,              label: 'Rentals' },
        { href: 'neighborhoods.html',    anchor: null,          i18nKey: null,              label: 'Neighborhoods' },
        { href: 'blog.html',             anchor: null,          i18nKey: 'blog_nav',        label: 'Guide' },
        { href: 'try-before-you-buy.html', anchor: null,        i18nKey: null,              label: 'Try Before You Buy' },
        { href: 'index.html',            anchor: '#contact',    i18nKey: 'nav_contact',     label: 'Contact' }
    ];

    var LANGUAGES = ['en', 'es', 'fr', 'ru'];

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /**
     * Determine the current page filename from the URL (e.g. "blog.html").
     * Falls back to "index.html" for root paths or trailing slashes.
     */
    function getCurrentPage() {
        var path = window.location.pathname;
        var filename = path.substring(path.lastIndexOf('/') + 1);
        if (!filename || filename === '') {
            filename = 'index.html';
        }
        return filename.toLowerCase();
    }

    /**
     * Check whether a nav link should be marked active.
     * For links that point to an anchor on a specific page (e.g. index.html#contact),
     * the link is only active if both the page AND hash match.
     * The "Properties" link (index.html#properties) is the default active on index.html
     * when no hash is present.
     */
    function isActiveLink(link) {
        var currentPage = getCurrentPage();
        var currentHash = window.location.hash;
        var linkPage = link.href.toLowerCase();

        // If the link targets a specific anchor on a page
        if (link.anchor) {
            if (linkPage === currentPage) {
                // On index.html with no hash, treat #properties as active (first/default)
                if (linkPage === 'index.html' && link.anchor === '#properties' && (!currentHash || currentHash === '')) {
                    return true;
                }
                return currentHash === link.anchor;
            }
            return false;
        }

        // Standard page match (no anchor)
        return linkPage === currentPage;
    }

    // -------------------------------------------------------------------------
    // Header Builder
    // -------------------------------------------------------------------------

    function buildHeader() {
        var currentPage = getCurrentPage();

        // Build nav links
        var navLinksHtml = NAV_LINKS.map(function (link) {
            var href;
            if (link.anchor) {
                // If we're already on the target page, use just the anchor
                if (link.href.toLowerCase() === currentPage) {
                    href = link.anchor;
                } else {
                    href = link.href + link.anchor;
                }
            } else {
                href = link.href;
            }

            var activeClass = isActiveLink(link) ? ' class="active"' : '';
            var i18nAttr = link.i18nKey ? ' data-i18n="' + link.i18nKey + '"' : '';

            return '<a href="' + href + '"' + activeClass + i18nAttr + '>' + link.label + '</a>';
        }).join('\n                    ');

        // Build language selector
        var savedLang = localStorage.getItem('lang') || 'en';
        var langButtonsHtml = LANGUAGES.map(function (lang) {
            var activeClass = lang === savedLang ? ' active' : '';
            return '<button class="lang-btn' + activeClass + '" data-lang="' + lang + '" onclick="setLang(\'' + lang + '\')">' + lang.toUpperCase() + '</button>';
        }).join('\n                        ');

        return '<header class="header">' +
            '\n        <div class="container">' +
            '\n            <div class="header-content">' +
            '\n                <a href="index.html" class="logo">Rent & Go PC</a>' +
            '\n                <nav class="nav">' +
            '\n                    ' + navLinksHtml +
            '\n                    <div class="lang-selector">' +
            '\n                        ' + langButtonsHtml +
            '\n                    </div>' +
            '\n                </nav>' +
            '\n                <button class="mobile-menu-btn" onclick="toggleMenu()">' +
            '\n                    <span></span><span></span><span></span>' +
            '\n                </button>' +
            '\n            </div>' +
            '\n        </div>' +
            '\n    </header>';
    }

    // -------------------------------------------------------------------------
    // Footer Builder
    // -------------------------------------------------------------------------

    function buildFooter() {
        return '<footer class="footer">' +
            '\n        <div class="container">' +
            '\n            <div class="footer-grid">' +
            '\n                <div class="footer-col">' +
            '\n                    <a href="index.html" class="footer-logo">Rent &amp; Go PC</a>' +
            '\n                    <p class="footer-tagline">Your trusted real estate partner in Punta Cana, Dominican Republic.</p>' +
            '\n                </div>' +
            '\n                <div class="footer-col">' +
            '\n                    <h4>Explore</h4>' +
            '\n                    <ul>' +
            '\n                        <li><a href="index.html#properties">Properties</a></li>' +
            '\n                        <li><a href="index.html#rentals">Rentals</a></li>' +
            '\n                        <li><a href="neighborhoods.html">Neighborhoods</a></li>' +
            '\n                        <li><a href="blog.html">Guide</a></li>' +
            '\n                    </ul>' +
            '\n                </div>' +
            '\n                <div class="footer-col">' +
            '\n                    <h4>Tools</h4>' +
            '\n                    <ul>' +
            '\n                        <li><a href="roi-calculator.html">ROI Calculator</a></li>' +
            '\n                        <li><a href="buying-guide-2026.html">Buying Guide</a></li>' +
            '\n                        <li><a href="cost-of-living.html">Cost of Living</a></li>' +
            '\n                    </ul>' +
            '\n                </div>' +
            '\n                <div class="footer-col">' +
            '\n                    <h4>Contact</h4>' +
            '\n                    <ul>' +
            '\n                        <li><a href="https://wa.me/18094865386" target="_blank">WhatsApp: +1 (809) 486-5386</a></li>' +
            '\n                        <li><span data-i18n="footer">Punta Cana, Dominican Republic</span></li>' +
            '\n                    </ul>' +
            '\n                </div>' +
            '\n            </div>' +
            '\n            <div class="footer-bottom">' +
            '\n                <p>&copy; 2026 Rent &amp; Go PC. All rights reserved.</p>' +
            '\n            </div>' +
            '\n        </div>' +
            '\n    </footer>';
    }

    // -------------------------------------------------------------------------
    // Meta Pixel Injection
    // -------------------------------------------------------------------------

    function injectMetaPixel() {
        // Skip if pixel already loaded (e.g. page has its own pixel code)
        if (window.fbq) return;

        // Inline pixel script
        !function (f, b, e, v, n, t, s) {
            if (f.fbq) return; n = f.fbq = function () {
                n.callMethod ?
                    n.callMethod.apply(n, arguments) : n.queue.push(arguments);
            };
            if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = '2.0';
            n.queue = []; t = b.createElement(e); t.async = !0;
            t.src = v; s = b.getElementsByTagName(e)[0];
            s.parentNode.insertBefore(t, s);
        }(window, document, 'script',
            'https://connect.facebook.net/en_US/fbevents.js');

        fbq('init', META_PIXEL_ID);
        fbq('track', 'PageView');

        // Add noscript fallback
        var noscript = document.createElement('noscript');
        var img = document.createElement('img');
        img.height = 1;
        img.width = 1;
        img.style.display = 'none';
        img.src = 'https://www.facebook.com/tr?id=' + META_PIXEL_ID + '&ev=PageView&noscript=1';
        noscript.appendChild(img);
        document.body.appendChild(noscript);
    }

    // -------------------------------------------------------------------------
    // Public API (exposed on window.SiteComponents)
    // -------------------------------------------------------------------------

    window.SiteComponents = {
        /** Inject header into the element with id="site-header" */
        renderHeader: function () {
            var el = document.getElementById('site-header');
            if (el) {
                el.outerHTML = buildHeader();
            }
        },

        /** Inject footer into the element with id="site-footer" */
        renderFooter: function () {
            var el = document.getElementById('site-footer');
            if (el) {
                el.outerHTML = buildFooter();
            }
        },

        /** Inject Meta Pixel if not already present */
        renderPixel: function () {
            injectMetaPixel();
        },

        /** Convenience: render everything */
        init: function () {
            this.renderHeader();
            this.renderFooter();
            this.renderPixel();
        },

        /** Expose nav links data for external use */
        navLinks: NAV_LINKS,

        /** Expose pixel ID for external use */
        pixelId: META_PIXEL_ID
    };

    // -------------------------------------------------------------------------
    // Auto-initialize: inject header, footer, and pixel on script load
    // -------------------------------------------------------------------------

    // Run immediately (script is expected to be in <body>, after placeholder divs)
    // If placeholders exist, inject. If not, do nothing (allows manual init).
    if (document.getElementById('site-header') || document.getElementById('site-footer')) {
        window.SiteComponents.init();
    }

})();
