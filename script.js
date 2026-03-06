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

// Init on page load
document.addEventListener('DOMContentLoaded', () => {
    applyTranslations();
    updateLangSelector();

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
});
