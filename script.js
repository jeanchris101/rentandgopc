// Language system
const LANGS = ['en', 'es', 'fr', 'ru'];
const LANG_LABELS = { en: 'EN', es: 'ES', fr: 'FR', ru: 'RU' };

let currentLang = localStorage.getItem('lang') || 'en';

function setLang(lang) {
    currentLang = lang;
    localStorage.setItem('lang', lang);
    applyTranslations();
    updateLangSelector();
}

function cycleLang() {
    const idx = LANGS.indexOf(currentLang);
    const next = LANGS[(idx + 1) % LANGS.length];
    setLang(next);
}

function applyTranslations() {
    const t = TRANSLATIONS[currentLang] || TRANSLATIONS.en;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (t[key]) {
            el.textContent = t[key];
        }
    });
    // Update html lang attribute
    document.documentElement.lang = currentLang === 'es' ? 'es' : currentLang === 'fr' ? 'fr' : currentLang === 'ru' ? 'ru' : 'en';
}

function updateLangSelector() {
    // Update all lang buttons
    document.querySelectorAll('.lang-selector').forEach(selector => {
        selector.querySelectorAll('.lang-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.lang === currentLang);
        });
    });
    // Update mobile toggle text
    document.querySelectorAll('.lang-toggle-mobile').forEach(el => {
        const idx = LANGS.indexOf(currentLang);
        const next = LANGS[(idx + 1) % LANGS.length];
        el.textContent = LANG_LABELS[next];
    });
}

// Mobile menu
function toggleMenu() {
    document.querySelector('.nav').classList.toggle('active');
}

// === Slideshow ===
let currentIndex = 0;
let slideCount = 0;
let slideImages = [];
let touchStartX = 0;

function initGallery() {
    const slides = document.querySelectorAll('.slide');
    if (!slides.length) return;
    slideCount = slides.length;
    slideImages = Array.from(slides).map(s => {
        const img = s.querySelector('img');
        return { src: img.src, alt: img.alt };
    });

    // Add lazy loading to off-screen slide images
    slides.forEach((s, i) => {
        const img = s.querySelector('img');
        if (i > 0) img.loading = 'lazy';
        img.decoding = 'async';
    });

    // Build dots
    const dotsEl = document.getElementById('slide-dots');
    if (dotsEl) {
        for (let i = 0; i < slideCount; i++) {
            const dot = document.createElement('button');
            dot.className = 'slide-dot' + (i === 0 ? ' active' : '');
            dot.onclick = () => goToSlide(i);
            dotsEl.appendChild(dot);
        }
    }

    // Click slide to open lightbox
    slides.forEach((s, i) => {
        s.addEventListener('click', () => openLightbox(i));
    });

    // Touch/swipe support with visual drag feedback
    const track = document.getElementById('slideshow-track');
    if (track) {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchDeltaX = 0;
        let isSwiping = false;

        track.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchDeltaX = 0;
            isSwiping = false;
            track.style.transition = 'none';
        }, { passive: true });

        track.addEventListener('touchmove', (e) => {
            const dx = e.touches[0].clientX - touchStartX;
            const dy = e.touches[0].clientY - touchStartY;
            // Lock to horizontal swipe after 10px movement
            if (!isSwiping && Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
                isSwiping = true;
            }
            if (isSwiping) {
                touchDeltaX = dx;
                const base = -(currentIndex * 100);
                const pct = (dx / track.offsetWidth) * 100;
                track.style.transform = 'translateX(' + (base + pct) + '%)';
            }
        }, { passive: true });

        track.addEventListener('touchend', () => {
            track.style.transition = 'transform 0.3s ease';
            if (isSwiping && Math.abs(touchDeltaX) > 40) {
                slideNav(touchDeltaX < 0 ? 1 : -1);
            } else {
                goToSlide(currentIndex);
            }
            isSwiping = false;
        }, { passive: true });
    }

    // Lightbox swipe support
    const lb = document.getElementById('lightbox');
    if (lb) {
        let lbStartX = 0;
        lb.addEventListener('touchstart', (e) => { lbStartX = e.touches[0].clientX; }, { passive: true });
        lb.addEventListener('touchend', (e) => {
            const diff = lbStartX - e.changedTouches[0].clientX;
            if (Math.abs(diff) > 50) lightboxNav(diff > 0 ? 1 : -1);
        }, { passive: true });
    }
}

function goToSlide(idx) {
    currentIndex = idx;
    const track = document.getElementById('slideshow-track');
    if (track) track.style.transform = 'translateX(-' + (idx * 100) + '%)';
    const counter = document.getElementById('slide-counter');
    if (counter) counter.textContent = (idx + 1) + ' / ' + slideCount;
    document.querySelectorAll('.slide-dot').forEach((d, i) => d.classList.toggle('active', i === idx));
}

function slideNav(dir) {
    let next = currentIndex + dir;
    if (next < 0) next = slideCount - 1;
    if (next >= slideCount) next = 0;
    goToSlide(next);
}

// === Lightbox ===
function openLightbox(idx) {
    if (!slideImages.length) return;
    const lb = document.getElementById('lightbox');
    const img = document.getElementById('lightbox-img');
    const counter = document.getElementById('lightbox-counter');
    if (!lb || !img) return;
    currentIndex = idx;
    img.src = slideImages[idx].src;
    img.alt = slideImages[idx].alt;
    if (counter) counter.textContent = (idx + 1) + ' / ' + slideCount;
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeLightbox(e) {
    if (e && e.target !== e.currentTarget && !e.target.classList.contains('lightbox-close')) return;
    const lb = document.getElementById('lightbox');
    if (lb) lb.classList.remove('open');
    document.body.style.overflow = '';
}

function lightboxNav(dir) {
    if (!slideImages.length) return;
    currentIndex = (currentIndex + dir + slideCount) % slideCount;
    const img = document.getElementById('lightbox-img');
    const counter = document.getElementById('lightbox-counter');
    if (img) {
        img.src = slideImages[currentIndex].src;
        img.alt = slideImages[currentIndex].alt;
    }
    if (counter) counter.textContent = (currentIndex + 1) + ' / ' + slideCount;
    goToSlide(currentIndex);
}

// Init on page load
document.addEventListener('DOMContentLoaded', () => {
    applyTranslations();
    updateLangSelector();
    initGallery();

    // Close mobile menu on link click
    document.querySelectorAll('.nav a').forEach(link => {
        link.addEventListener('click', () => {
            document.querySelector('.nav').classList.remove('active');
        });
    });

    // Header shadow on scroll
    window.addEventListener('scroll', () => {
        const header = document.querySelector('.header');
        if (header) {
            header.style.boxShadow = window.scrollY > 10
                ? '0 2px 20px rgba(0,0,0,0.1)'
                : 'none';
        }
    });

    // Keyboard nav for lightbox
    document.addEventListener('keydown', (e) => {
        const lb = document.getElementById('lightbox');
        if (!lb || !lb.classList.contains('open')) return;
        if (e.key === 'Escape') closeLightbox();
        if (e.key === 'ArrowLeft') lightboxNav(-1);
        if (e.key === 'ArrowRight') lightboxNav(1);
    });

    // === Auto-apply .animate-on-scroll to key elements ===
    const animateSelectors = [
        '.section-title',
        '.property-card',
        '.benefit-card',
        '.stat-item',
        '.rental-card',
        '.tool-card'
    ];
    animateSelectors.forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            el.classList.add('animate-on-scroll');
        });
    });

    // === Initialize scroll animations ===
    initScrollAnimations();
});

// === Scroll Animations ===

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Initialize all scroll-based animations
 */
function initScrollAnimations() {
    initScrollReveal();
    initNumberCounters();
    initHeroParallax();
    initHeaderTransition();
}

// --- 1. Scroll-reveal animations ---
function initScrollReveal() {
    const elements = document.querySelectorAll('.animate-on-scroll');
    if (!elements.length) return;

    // If user prefers reduced motion, show everything immediately
    if (prefersReducedMotion) {
        elements.forEach(el => el.classList.add('visible'));
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });

    elements.forEach(el => observer.observe(el));
}

// --- 2. Animated number counters ---
function initNumberCounters() {
    const counters = document.querySelectorAll('[data-count-to]');
    if (!counters.length) return;

    // If reduced motion, show final values immediately
    if (prefersReducedMotion) {
        counters.forEach(el => {
            const target = parseFloat(el.getAttribute('data-count-to'));
            const suffix = el.getAttribute('data-count-suffix') || '';
            el.textContent = formatCounterValue(target) + suffix;
        });
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });

    counters.forEach(el => observer.observe(el));
}

function formatCounterValue(value) {
    // If it's a whole number, show without decimals; otherwise keep one decimal
    return Number.isInteger(value) ? value.toString() : value.toFixed(1);
}

function animateCounter(el) {
    const target = parseFloat(el.getAttribute('data-count-to'));
    const suffix = el.getAttribute('data-count-suffix') || '';
    const duration = 2000; // ~2 seconds
    let start = null;

    function easeOutQuart(t) {
        return 1 - Math.pow(1 - t, 4);
    }

    function step(timestamp) {
        if (!start) start = timestamp;
        const elapsed = timestamp - start;
        const progress = Math.min(elapsed / duration, 1);
        const easedProgress = easeOutQuart(progress);
        const current = easedProgress * target;

        el.textContent = formatCounterValue(Math.round(current * 10) / 10) + suffix;

        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            el.textContent = formatCounterValue(target) + suffix;
        }
    }

    requestAnimationFrame(step);
}

// --- 3. Parallax on hero background ---
function initHeroParallax() {
    if (prefersReducedMotion) return;

    const hero = document.querySelector('.hero');
    if (!hero) return;

    let ticking = false;

    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(() => {
                const scrollY = window.scrollY;
                // Only apply when hero is in view range
                if (scrollY < window.innerHeight * 1.5) {
                    hero.style.backgroundPositionY = (scrollY * 0.3) + 'px';
                }
                ticking = false;
            });
            ticking = true;
        }
    }, { passive: true });
}

// --- 4. Smooth header transition on scroll ---
function initHeaderTransition() {
    const header = document.querySelector('.header');
    if (!header) return;

    // Remove the basic scroll handler — we replace it with an enhanced one
    // (The old one in DOMContentLoaded only set box-shadow)
    let ticking = false;

    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(() => {
                const scrollY = window.scrollY;
                const scrolled = scrollY > 10;

                header.style.boxShadow = scrolled
                    ? '0 2px 20px rgba(0,0,0,0.15)'
                    : 'none';
                header.style.backdropFilter = scrolled
                    ? 'blur(12px)'
                    : 'blur(8px)';
                header.style.height = scrolled ? '60px' : '70px';
                header.style.transition = 'box-shadow 0.3s, backdrop-filter 0.3s, height 0.3s';

                ticking = false;
            });
            ticking = true;
        }
    }, { passive: true });
}
