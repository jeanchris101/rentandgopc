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

    // Touch/swipe support
    const track = document.getElementById('slideshow-track');
    if (track) {
        track.addEventListener('touchstart', (e) => { touchStartX = e.touches[0].clientX; }, { passive: true });
        track.addEventListener('touchend', (e) => {
            const diff = touchStartX - e.changedTouches[0].clientX;
            if (Math.abs(diff) > 50) slideNav(diff > 0 ? 1 : -1);
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
});
