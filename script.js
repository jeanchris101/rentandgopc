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

// === Photo Gallery ===
let currentIndex = 0;
let galleryImages = [];

function initGallery() {
    const thumbs = document.querySelectorAll('#gallery-thumbs .thumb');
    if (!thumbs.length) return;
    galleryImages = Array.from(thumbs).map(t => ({ src: t.src, alt: t.alt }));
}

function setMainImage(idx) {
    if (!galleryImages.length) return;
    currentIndex = idx;
    const mainImg = document.getElementById('gallery-main-img');
    const counter = document.getElementById('gallery-counter');
    if (mainImg) {
        mainImg.src = galleryImages[idx].src;
        mainImg.alt = galleryImages[idx].alt;
    }
    if (counter) counter.textContent = (idx + 1) + ' / ' + galleryImages.length;
    document.querySelectorAll('#gallery-thumbs .thumb').forEach((t, i) => {
        t.classList.toggle('active', i === idx);
    });
}

function openLightbox(idx) {
    if (!galleryImages.length) return;
    const lb = document.getElementById('lightbox');
    const img = document.getElementById('lightbox-img');
    const counter = document.getElementById('lightbox-counter');
    if (!lb || !img) return;
    currentIndex = idx;
    img.src = galleryImages[idx].src;
    img.alt = galleryImages[idx].alt;
    if (counter) counter.textContent = (idx + 1) + ' / ' + galleryImages.length;
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
    if (!galleryImages.length) return;
    currentIndex = (currentIndex + dir + galleryImages.length) % galleryImages.length;
    const img = document.getElementById('lightbox-img');
    const counter = document.getElementById('lightbox-counter');
    if (img) {
        img.src = galleryImages[currentIndex].src;
        img.alt = galleryImages[currentIndex].alt;
    }
    if (counter) counter.textContent = (currentIndex + 1) + ' / ' + galleryImages.length;
    setMainImage(currentIndex);
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
