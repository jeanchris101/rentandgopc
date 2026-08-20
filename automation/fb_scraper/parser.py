"""
parser.py — Regex-based extraction of structured fields from raw FB post text.
Bilingual EN/ES/FR patterns for the Punta Cana real estate market.
130+ zones/communities, deep contact extraction, confidence scoring, spam filtering.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# Data classes
# ============================================================

@dataclass
class PriceResult:
    amount: float
    currency: str       # USD, DOP, EUR, CAD
    raw: str
    is_monthly: bool = False
    is_nightly: bool = False
    is_negotiable: bool = False
    is_minimum: bool = False   # "desde"


@dataclass
class AreaResult:
    value: float
    unit: str  # sqft, sqm


@dataclass
class ContactResult:
    phones: list[str] = field(default_factory=list)
    whatsapp: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    instagram: Optional[str] = None
    company: Optional[str] = None
    website: Optional[str] = None


@dataclass
class ParseResult:
    price: Optional[PriceResult] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    area: Optional[AreaResult] = None
    zone: Optional[str] = None           # parent zone (e.g., "Bavaro")
    community: Optional[str] = None      # specific match (e.g., "Cortecito")
    property_type: Optional[str] = None
    listing_type: Optional[str] = None
    contact: Optional[ContactResult] = None
    furnishing: Optional[str] = None
    amenities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = False
    review_reason: Optional[str] = None
    is_spam: bool = False
    # Kept for backward compat in database.py
    @property
    def neighborhood(self) -> Optional[str]:
        return self.zone


# ============================================================
# Spam filtering
# ============================================================

SPAM_PATTERNS = [
    re.compile(r'\b(buscando|busco|looking\s*for|searching\s*for|necesito|i\s*need)\b', re.I),
    re.compile(r'\b(does\s*anyone\s*know|alguien\s*sabe|recomiend[ae]n?|recommend)\b', re.I),
    re.compile(r'\b(happy\s*birthday|feliz\s*cumplea)', re.I),
    re.compile(r'\b(giveaway|sorteo|rifa|concurso)\b', re.I),
    re.compile(r'\b(RIP|condolencias|in\s*memoriam|QEPD)\b', re.I),
    re.compile(r'\b(lost\s*(?:dog|cat|pet)|mascota\s*perdida)\b', re.I),
    re.compile(r'\b(se\s*busca|wanted|missing\s*person)\b', re.I),
    re.compile(r'\b(uber|taxi|ride|colmado|delivery|comida|food|restaurant)\b', re.I),
    # Vehicles
    re.compile(r'\b(carro|vehiculo|camioneta|motocicleta|jeepeta|pickup|camion)\b', re.I),
    re.compile(r'\b(toyota|honda|hyundai|kia|nissan|mitsubishi)\b', re.I),
    # Electronics
    re.compile(r'\b(samsung|iphone|telefono|celular|laptop|computadora|televisor)\b', re.I),
    # Services
    re.compile(r'\b(peluqueria|barberia|excursion|submarine|scuba)\b', re.I),
    re.compile(r'\b(salon\s+de\s+(?:belleza|u[ñn]as))\b', re.I),
    # Jobs
    re.compile(r'\b(empleo|vacante|hiring)\b', re.I),
    re.compile(r'\b(se\s+necesita\s+personal|se\s+busca\s+personal|oferta\s+de\s+trabajo)\b', re.I),
    # Other non-RE
    re.compile(r'\b(playstation|xbox|nintendo|game\s*console)\b', re.I),
    # Garbage page text
    re.compile(r'there are currently no products', re.I),
    re.compile(r'no hay productos', re.I),
]

# Real estate keywords — posts containing these are protected from spam flagging
# even if they also match a spam pattern (e.g., street named "Toyota")
RE_SAFELIST_RE = re.compile(
    r'\b(casa|apartamento|apto|villa|terreno|solar|habitacion|habitaciones|'
    r'penthouse|condo|inmueble|propiedad|m2|metros|sqm|'
    r'rent|sale|bedroom|bath|piso|'
    r'condominio|residencial|lote|parcela|finca|'
    r'duplex|townhouse|studio|estudio|amueblado|furnished|piscina|pool|'
    r'dormitorio|recamara|alcoba|edificio|bienes\s*raices|real\s*estate|inmobiliaria)\b',
    re.I,
)


def is_spam(text: str) -> bool:
    """Check if post is clearly NOT a listing.

    Matches against spam patterns, but protects posts that contain
    real-estate keywords (safelist) to avoid false positives.
    """
    for pat in SPAM_PATTERNS:
        if pat.search(text):
            # If the post also contains RE keywords, it's probably legit
            if RE_SAFELIST_RE.search(text):
                return False
            return True
    return False


# ============================================================
# Price extraction — enhanced
# ============================================================

# Check for monthly/nightly/negotiable context
MONTHLY_RE = re.compile(r'\b(per\s*month|monthly|/\s*m(?:es|onth)|mensual|al\s*mes)\b', re.I)
NIGHTLY_RE = re.compile(r'\b(per\s*night|nightly|/\s*noche|por\s*noche)\b', re.I)
NEGOTIABLE_RE = re.compile(r'\b(negociable|negotiable|OBO|o\.b\.o|mejor\s*oferta|best\s*offer)\b', re.I)
DESDE_RE = re.compile(r'\b(desde|starting\s*(?:at|from)|from)\b', re.I)

# Number fragment that handles BOTH comma-thousands AND dot-thousands separators:
#   Comma-style: 1,234,567 or 1,234,567.50
#   Dot-style (DR): 1.234.567 or 170.000 (dot + 3 digits = thousands)
#   Plain: 170000
#   Decimal cents: 170.50 (dot + 1-2 digits at end)
# IMPORTANT: dot-thousands branch MUST come first in alternation, otherwise
# the regex engine greedily matches "170" from "170.000" via the comma branch.
_NUM = r'[\d]{1,3}(?:(?:\.\d{3})+(?:,\d{1,2})?|(?:,\d{3})*(?:\.\d{1,2})?)'

# K/M suffix number (simpler, no thousands separators expected)
_NUM_KM = r'[\d]+(?:\.\d{1,2})?'

PRICE_PATTERNS = [
    # RD$ / DOP — must come BEFORE generic $ to avoid false USD match
    (re.compile(r'RD\$\s*(' + _NUM + r')', re.I), 'DOP'),
    (re.compile(r'DOP\s*\$?\s*(' + _NUM + r')', re.I), 'DOP'),
    # CAD: C$450,000 or CAD 450,000 or CAD$450,000
    (re.compile(r'(?:CAD\s*\$?|C\$)\s*(' + _NUM + r')', re.I), 'CAD'),
    # USD: US$1,234 (explicit prefix)
    (re.compile(r'US\$\s*(' + _NUM + r')', re.I), 'USD'),
    # K suffix: $150K, 150K USD — BEFORE generic $ to avoid partial match
    (re.compile(r'(?<!RD)(?:USD?\s*\$?|\$)\s*(' + _NUM_KM + r')\s*K\b', re.I), 'USD'),
    (re.compile(r'(' + _NUM_KM + r')\s*K\s*(?:USD|dollars?|d[oó]lares?)', re.I), 'USD'),
    (re.compile(r'(?<!RD)(?:USD?\s*\$?|\$)\s*(' + _NUM_KM + r')\s*M\b', re.I), 'USD'),
    # "mil" suffix: "150 mil", "150mil dolares"
    (re.compile(r'(' + _NUM_KM + r')\s*mil\s*(?:d[oó]lares?|USD|pesos)?', re.I), 'USD'),
    # USD: $1,234,567 — negative lookbehind to skip RD$ and C$
    (re.compile(r'(?<!RD)(?<!CA)(?<!C)(?:USD?\s*\$?|\$)\s*(' + _NUM + r')\s*(?:USD|usd|dollars?|d[oó]lares?)?', re.I), 'USD'),
    # EUR
    (re.compile(r'\u20ac\s*(' + _NUM + r')', re.I), 'EUR'),
    (re.compile(r'(' + _NUM + r')\s*(?:EUR|euros?)', re.I), 'EUR'),
    # Plain number with context
    (re.compile(r'(?:precio|price|costo|cost|valor)\s*:?\s*\$?\s*(' + _NUM + r')', re.I), 'USD'),
]

# Patterns that use K/M multiplier (new indices after reorder)
_K_PATTERN_INDICES = {4, 5}   # K-suffix patterns
_M_PATTERN_INDICES = {6}      # M-suffix pattern
_MIL_PATTERN_INDICES = {7}    # "mil" pattern


def _normalize_price_number(raw: str) -> float:
    """
    Normalize a price number string handling both comma and dot thousands separators.
    Rules:
      - Dot followed by exactly 3 digits (possibly repeated): thousands separator (DR style)
        e.g., 170.000 → 170000, 1.200.000 → 1200000, 12.800.000 → 12800000
      - Dot followed by 1-2 digits at end: decimal (cents)
        e.g., 170.50 → 170.50
      - Commas are always thousands separators (already handled)
    """
    # Check if this is dot-thousands format: pattern like \d+\.\d{3}(\.\d{3})*
    # Must NOT end with dot + 1-2 digits (that would be decimal)
    if re.match(r'^\d{1,3}(\.\d{3})+$', raw):
        # Pure dot-thousands: 170.000 or 1.200.000
        return float(raw.replace('.', ''))
    if re.match(r'^\d{1,3}(\.\d{3})+,\d{1,2}$', raw):
        # Dot-thousands with comma-decimal: 170.000,50 (European style)
        return float(raw.replace('.', '').replace(',', '.'))
    # Standard: remove commas (thousands), keep dots (decimal)
    return float(raw.replace(',', ''))


def extract_price(text: str) -> Optional[PriceResult]:
    for idx, (pat, default_currency) in enumerate(PRICE_PATTERNS):
        m = pat.search(text)
        if m:
            raw_num = m.group(1)
            amount = _normalize_price_number(raw_num)

            # Apply multipliers
            if idx in _K_PATTERN_INDICES:
                amount *= 1000
            elif idx in _M_PATTERN_INDICES:
                amount *= 1_000_000
            elif idx in _MIL_PATTERN_INDICES:
                amount *= 1000
                # "mil pesos" → DOP
                if re.search(r'pesos', m.group(0), re.I):
                    default_currency = 'DOP'

            if amount < 50:
                continue

            currency = default_currency
            matched = m.group(0)
            if re.search(r'RD\$', matched, re.I):
                currency = 'DOP'
            elif re.search(r'DOP|pesos', matched, re.I):
                currency = 'DOP'
            elif re.search(r'\u20ac|EUR', matched, re.I):
                currency = 'EUR'
            elif re.search(r'CAD|C\$', matched, re.I):
                currency = 'CAD'

            # Override: If detected as DOP but text explicitly mentions "USD" or "US$"
            # with a similar amount, the listing is really in USD.
            # Common on Marketplace: header shows DOP but description says "USD 90,000"
            if currency == 'DOP':
                usd_override = re.search(
                    r'(?:USD|US\$|dolares?|d[oó]lares?)\s*\$?\s*(' + _NUM + r')',
                    text, re.I
                )
                if usd_override:
                    try:
                        usd_amount = _normalize_price_number(usd_override.group(1))
                        # If the USD amount is in a reasonable range and close to DOP amount,
                        # the listing was priced in USD (FB just auto-converted to DOP display)
                        if usd_amount >= 1000 and abs(usd_amount - amount) / max(amount, 1) < 0.15:
                            currency = 'USD'
                        elif usd_amount >= 1000:
                            # Different amounts — USD price in text is the real one
                            amount = usd_amount
                            currency = 'USD'
                    except (ValueError, ZeroDivisionError):
                        pass

            is_monthly = bool(MONTHLY_RE.search(text))
            is_nightly = bool(NIGHTLY_RE.search(text))
            is_negotiable = bool(NEGOTIABLE_RE.search(text))
            is_minimum = bool(DESDE_RE.search(text))

            return PriceResult(
                amount=amount,
                currency=currency,
                raw=matched.strip(),
                is_monthly=is_monthly,
                is_nightly=is_nightly,
                is_negotiable=is_negotiable,
                is_minimum=is_minimum,
            )
    return None


# ============================================================
# Bedrooms
# ============================================================

BED_PATTERNS = [
    re.compile(r'(\d+)\s*(?:bed(?:room)?s?|br|bdr|bdrm)', re.I),
    re.compile(r'(\d+)\s*(?:hab(?:itaci[oó]n(?:es)?)?|dormitorio?s?|rec[aá]mara?s?|cuarto?s?|alcoba?s?)', re.I),
    re.compile(r'(?:bed(?:room)?s?|hab(?:itaci[oó]n(?:es)?)?|dormitorio?s?)\s*:?\s*(\d+)', re.I),
    # French
    re.compile(r'(\d+)\s*(?:chambre?s?|ch\b)', re.I),
]


def extract_bedrooms(text: str) -> Optional[int]:
    for pat in BED_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
            n = int(val)
            if 0 < n <= 20:
                return n
    return None


# ============================================================
# Bathrooms
# ============================================================

BATH_PATTERNS = [
    re.compile(r'(\d+(?:\.\d)?)\s*(?:bath(?:room)?s?|ba\b)', re.I),
    re.compile(r'(\d+(?:\.\d)?)\s*(?:ba[ñn]o?s?)', re.I),
    re.compile(r'(?:bath(?:room)?s?|ba[ñn]o?s?)\s*:?\s*(\d+(?:\.\d)?)', re.I),
    # French
    re.compile(r'(\d+(?:\.\d)?)\s*(?:salle?s?\s*de?\s*bain)', re.I),
]


def extract_bathrooms(text: str) -> Optional[float]:
    for pat in BATH_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
            n = float(val)
            if 0 < n <= 20:
                return n
    return None


# ============================================================
# Area
# ============================================================

AREA_PATTERNS = [
    (re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square\s*feet|ft[^a-z]|ft2)', re.I), 'sqft'),
    (re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(?:m[^a-z]|m2|sqm|sq\.?\s*m|metros?\s*(?:cuadrados?)?)', re.I), 'sqm'),
]


def extract_area(text: str) -> Optional[AreaResult]:
    for pat, unit in AREA_PATTERNS:
        m = pat.search(text)
        if m:
            cleaned = m.group(1).replace(',', '')
            if not cleaned:
                continue
            val = float(cleaned)
            if val < 5:
                continue
            return AreaResult(value=val, unit=unit)
    return None


# ============================================================
# Zone + Community mapping (130+ locations)
# ============================================================

# ZONE_MAP: community/sub-area name → parent zone
# If a name IS a parent zone, it maps to itself.
ZONE_MAP = {
    # --- Cap Cana zone ---
    'Cap Cana': 'Cap Cana',
    'Juanillo': 'Cap Cana',
    'Punta Espada': 'Cap Cana',
    'Las Iguanas': 'Cap Cana',
    'Fundadores': 'Cap Cana',
    'Marina Cap Cana': 'Cap Cana',
    '7 Mares': 'Cap Cana',
    'Siete Mares': 'Cap Cana',
    'Danzza': 'Cap Cana',
    'Galia': 'Cap Cana',
    'Sanctuary': 'Cap Cana',
    'Sanctuary Cap Cana': 'Cap Cana',
    'Fishing Lodge': 'Cap Cana',
    'Caleton': 'Cap Cana',
    'Secrets Cap Cana': 'Cap Cana',
    'Aquamarina Cap Cana': 'Cap Cana',
    'Las Canas': 'Cap Cana',
    'Arrecife': 'Cap Cana',
    'Eden Roc': 'Cap Cana',
    'Al Sol Cap Cana': 'Cap Cana',

    # --- Bavaro zone ---
    'Bavaro': 'Bavaro',
    'Bávaro': 'Bavaro',
    'El Cortecito': 'Bavaro',
    'Cortecito': 'Bavaro',
    'Los Corales': 'Bavaro',
    'Arena Gorda': 'Bavaro',
    'Torres del Lago': 'Bavaro',
    'Turquesa': 'Bavaro',
    'Playa Turquesa': 'Bavaro',
    'Arboleda': 'Bavaro',
    'Ocean Bay': 'Bavaro',
    'Costa Bavaro': 'Bavaro',
    'Coral Village': 'Bavaro',
    'Taina': 'Bavaro',
    'Velero': 'Bavaro',
    'The Beach': 'Bavaro',
    'Palma Real': 'Bavaro',
    'Blue Beach': 'Bavaro',
    'Paseo del Mar': 'Bavaro',
    'Punta Palmera': 'Bavaro',
    'Aquamarina': 'Bavaro',
    'Coralina': 'Bavaro',
    'San Juan': 'Bavaro',
    'Cabeza de Toro': 'Bavaro',
    'Bavaro Green': 'Bavaro',
    'Iberostar': 'Bavaro',
    'Bahia Principe': 'Bavaro',
    'Hard Rock': 'Bavaro',
    'Hyatt Zilara': 'Bavaro',
    'Royalton': 'Bavaro',
    'Dreams': 'Bavaro',
    'Barcelo': 'Bavaro',
    'Melia': 'Bavaro',
    'Cocobay': 'Bavaro',
    'Ocean Village': 'Bavaro',
    'Las Atalayas': 'Bavaro',
    'Crisfer': 'Bavaro',

    # --- Cana Rock / Cana Bay zone ---
    'Cana Rock': 'Cana Rock',
    'Cana Rock Star': 'Cana Rock',
    'Cana Rock Universe': 'Cana Rock',
    'Cana Rock Galaxy': 'Cana Rock',
    'Cana Rock Next': 'Cana Rock',
    'Cana Rock Soul': 'Cana Rock',
    'Cana Bay': 'Cana Rock',
    'Cana Baya': 'Cana Rock',
    'Riviera Bay': 'Cana Rock',
    'Poseidonia': 'Cana Rock',
    'River Island': 'Cana Rock',

    # --- Vista Cana zone ---
    'Vista Cana': 'Vista Cana',
    'Vista Cana Boulevard': 'Vista Cana',
    'Vista Cana Golf': 'Vista Cana',
    'Smart Villas': 'Vista Cana',
    'Lake Condos': 'Vista Cana',
    'Colinas': 'Vista Cana',

    # --- Cocotal zone ---
    'Cocotal': 'Cocotal',
    'Cocotal Golf': 'Cocotal',
    'Cocotal Inn': 'Cocotal',
    'Cocotal Palms': 'Cocotal',

    # --- Punta Cana (generic / standalone) ---
    'Punta Cana': 'Punta Cana',
    'Puntacana': 'Punta Cana',

    # --- Punta Cana Village zone ---
    'Punta Cana Village': 'Punta Cana Village',
    'Tortuga Bay': 'Punta Cana Village',
    'Corales': 'Punta Cana Village',
    'Hacienda': 'Punta Cana Village',
    'Hacienda del Mar': 'Punta Cana Village',
    'Playa Serena': 'Punta Cana Village',
    'Lagos': 'Punta Cana Village',
    'Marina PC': 'Punta Cana Village',
    'Puntacana Resort': 'Punta Cana Village',

    # --- Uvero Alto zone ---
    'Uvero Alto': 'Uvero Alto',
    'Uvero': 'Uvero Alto',
    'Miches': 'Uvero Alto',
    'Excellence': 'Uvero Alto',
    'Breathless': 'Uvero Alto',
    'Sivory': 'Uvero Alto',
    'Zoetry': 'Uvero Alto',

    # --- Macao zone ---
    'Macao': 'Macao',
    'Macao Beach': 'Macao',

    # --- Veron / Friusa / Pueblo Bavaro zone ---
    'Veron': 'Veron',
    'Verón': 'Veron',
    'Friusa': 'Veron',
    'Pueblo Bavaro': 'Veron',
    'Los Platanitos': 'Veron',
    'Serena Village': 'Veron',

    # --- Downtown PC zone ---
    'Downtown Punta Cana': 'Downtown PC',
    'Downtown PC': 'Downtown PC',

    # --- White Sands zone ---
    'White Sands': 'White Sands',
    'White Sands Apartments': 'White Sands',

    # --- Higuey zone ---
    'Higuey': 'Higuey',
    'Higüey': 'Higuey',
    'Salvaleón de Higuey': 'Higuey',
    'Salvaleón de Higüey': 'Higuey',
    'La Altagracia': 'Higuey',

    # --- Scape Park (attraction area, sometimes used as location) ---
    'Scape Park': 'Cap Cana',
}

# Build regex — sort by length descending so longer names match first
_all_locations = sorted(ZONE_MAP.keys(), key=len, reverse=True)
_loc_escaped = [re.escape(n) for n in _all_locations]
LOCATION_RE = re.compile(r'\b(' + '|'.join(_loc_escaped) + r')\b', re.I)

# Canonical name lookup (lowercase → proper case)
_LOC_CANONICAL = {n.lower(): n for n in ZONE_MAP.keys()}


def extract_location(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract zone (parent) and community (specific match).
    Returns (zone, community). Community may equal zone for top-level matches.
    """
    m = LOCATION_RE.search(text)
    if not m:
        return (None, None)
    found = m.group(1)
    canonical = _LOC_CANONICAL.get(found.lower(), found)
    parent_zone = ZONE_MAP.get(canonical)
    # If the match IS the parent zone, community = None (it's the zone itself)
    if canonical == parent_zone:
        return (parent_zone, None)
    return (parent_zone, canonical)


# Backward compat aliases
def extract_neighborhood(text: str) -> Optional[str]:
    zone, _ = extract_location(text)
    return zone


def extract_community(text: str) -> Optional[str]:
    _, community = extract_location(text)
    return community


# ============================================================
# Property Type
# ============================================================

PROPERTY_TYPE_PATTERNS = [
    # --- Highest priority: unambiguous types ---
    (re.compile(r'\b(penthouse|ph|[aá]tico)\b', re.I), 'penthouse'),
    (re.compile(r'\b(hotel\s*unit|unidad\s*hotelera|condo[\s-]?hotel)\b', re.I), 'hotel_unit'),
    # --- Land BEFORE condo/villa: "solar en Residencial X" is land, not condo ---
    (re.compile(r'\b(lot|lote|solar(?:es)?|terreno|land|parcela|finca)\b', re.I), 'land'),
    # --- Commercial BEFORE condo: "oficina en condominio" is commercial ---
    (re.compile(r'\b(comercial|commercial|local\s*comercial|oficina|office|nave\s*industrial|negocio|plaza\s*comercial)\b', re.I), 'commercial'),
    # --- Specific dwelling types ---
    (re.compile(r'\b(villa|chalet|mansi[oó]n|mansion)\b', re.I), 'villa'),
    (re.compile(r'\b(studio|estudio|monoambiente|efficiency)\b', re.I), 'studio'),
    (re.compile(r'\b(townhouse|town\s*house|town\s*home|casa\s*adosada|duplex|d[uú]plex)\b', re.I), 'townhouse'),
    # --- casa/house BEFORE condo: "casa en residencial" is villa, not condo ---
    (re.compile(r'\b(house|casa|home|hogar|vivienda)\b', re.I), 'villa'),
    # --- Condo: removed "residencial" (too ambiguous, matches location names) ---
    (re.compile(r'\b(condo(?:minium)?|condominio)\b', re.I), 'condo'),
    (re.compile(r'\b(apart(?:a)?ment(?:o)?|apto\.?|apt\.?|depto|departamento|flat|edificio)\b', re.I), 'apartment'),
    # --- Generic property words as last resort (removed from villa pattern above) ---
    (re.compile(r'\b(propiedad|inmueble)\b', re.I), 'villa'),
]

# Patterns that indicate solar panels / solar energy (NOT land)
_SOLAR_ENERGY_RE = re.compile(
    r'\b(panel\s*solar|solar\s*panel|energ[ií]a\s*solar|solar\s*energy|'
    r'panel(?:es)?\s*fotovoltaico|calentador\s*solar)\b', re.I
)


def extract_property_type(text: str, bedrooms: Optional[int] = None) -> Optional[str]:
    for pat, ptype in PROPERTY_TYPE_PATTERNS:
        m = pat.search(text)
        if m:
            # Guard: if matched "solar" for land, check it's not "panel solar" etc.
            if ptype == 'land' and m.group(1).lower().startswith('solar'):
                if _SOLAR_ENERGY_RE.search(text):
                    continue  # skip — this is about solar energy, not land
            return ptype
    # Fallback: infer from context if we have bedroom data
    if bedrooms is not None:
        if bedrooms == 0:
            return 'land'
        elif bedrooms >= 4:
            return 'villa'
        elif bedrooms <= 2:
            return 'apartment'
    return None


# ============================================================
# Amenities — expanded
# ============================================================

AMENITY_PATTERNS = [
    (re.compile(r'\b(pool|piscina)\b', re.I), 'pool'),
    (re.compile(r'\b(gym|gimnasio|fitness)\b', re.I), 'gym'),
    (re.compile(r'\b(security|seguridad|vigilancia|24[\s/]?h(?:rs?|oras?)?|guardias?)\b', re.I), 'security'),
    (re.compile(r'\b(parking|estacionamiento|garaje|garage|parqueo)\b', re.I), 'parking'),
    (re.compile(r'\b(balc[oó]n|balcony|terraza|terrace)\b', re.I), 'balcony'),
    (re.compile(r'\b(rooftop|azotea|roof\s*deck)\b', re.I), 'rooftop'),
    (re.compile(r'\b(ocean\s*view|vista\s*(?:al\s*)?mar|sea\s*view|beachfront|frente\s*(?:al\s*)?mar)\b', re.I), 'ocean_view'),
    (re.compile(r'\b(beach\s*access|acceso\s*(?:a\s*(?:la\s*)?)?playa|beach\s*club)\b', re.I), 'beach_access'),
    (re.compile(r'\b(golf)\b', re.I), 'golf'),
    (re.compile(r'\b(elevator|ascensor)\b', re.I), 'elevator'),
    (re.compile(r'\b(generator|planta\s*(?:el[eé]ctrica)?|generador)\b', re.I), 'generator'),
    (re.compile(r'\b(a/?c|air\s*condition|aire\s*acondicionado|climatizado)\b', re.I), 'ac'),
    (re.compile(r'\b(laundry|lavander[ií]a|washer|lavadora)\b', re.I), 'laundry'),
    (re.compile(r'\b(jacuzzi|hot\s*tub|hidromasaje)\b', re.I), 'jacuzzi'),
    (re.compile(r'\b(bbq|grill|parrilla|asador)\b', re.I), 'bbq'),
    (re.compile(r'\b(kids|children|infantil|playground|juegos?\s*(?:infantiles?)?|[aá]rea\s*de\s*ni[ñn]os)\b', re.I), 'kids_area'),
    (re.compile(r'\b(pet|mascota|dog\s*friendly)\b', re.I), 'pet_friendly'),
    (re.compile(r'\b(spa)\b', re.I), 'spa'),
    (re.compile(r'\b(cowork(?:ing)?|[aá]rea\s*de\s*trabajo)\b', re.I), 'coworking'),
    (re.compile(r'\b(furnished|amueblado|amoblado|equipado)\b', re.I), 'furnished'),
    (re.compile(r'\b(smart\s*(?:home|lock)|dom[oó]tica)\b', re.I), 'smart_home'),
    (re.compile(r'\b(storage|almac[eé]n|bodega)\b', re.I), 'storage'),
    (re.compile(r'\b(solar\s*panel|panel\s*solar|energ[ií]a\s*solar)\b', re.I), 'solar'),
]


def extract_amenities(text: str) -> list[str]:
    found = []
    for pat, amenity in AMENITY_PATTERNS:
        if pat.search(text):
            found.append(amenity)
    return found


# ============================================================
# Listing Type — expanded EN/ES/FR
# ============================================================

SALE_RE = re.compile(
    r'\b(for\s*sale|en\s*venta|venta|se\s*vende|se\s*venden|selling|vendo|'
    r'venta\s*directa|venta\s*r[aá]pida|'
    r'[aà]\s*vendre|investment|inversi[oó]n|oportunidad|opportunity|ROI|'
    r'precio\s*de\s*venta|disponible\s*(?:para\s*)?venta|listado)\b', re.I)
RENT_LONG_RE = re.compile(
    r'\b(for\s*rent|en\s*alquiler|alquiler|se\s*alquila|se\s*alquilan|renta(?:l)?|arriendo|'
    r'alquiler\s*mensual|alquiler\s*anual|alquiler\s*largo\s*plazo|'
    r'alquiler\s*disponible|alquiler\s*inmediato|mensual(?:idad)?|por\s*mes|monthly|'
    r'long[\s-]?term|largo\s*plazo|[aà]\s*louer|unfurnished\s*rent)\b', re.I)
RENT_SHORT_RE = re.compile(
    r'\b(airbnb|short[\s-]?term|corto\s*plazo|nightly|por\s*noche|'
    r'alquiler\s*(?:corto\s*plazo|temporal|vacacional|por\s*noche|por\s*d[ií]a)|'
    r'vacation\s*rental|alquiler\s*vacacional|temporal|'
    r'noches?|/noche|per\s*night)\b', re.I)


def extract_listing_type(text: str) -> Optional[str]:
    has_short = bool(RENT_SHORT_RE.search(text))
    has_long = bool(RENT_LONG_RE.search(text))
    has_sale = bool(SALE_RE.search(text))

    if has_short:
        return 'short_term_rent'
    if has_sale and has_long:
        return 'sale_or_rent'
    if has_sale:
        return 'sale'
    if has_long:
        return 'rent'
    return None


# ============================================================
# Deep Contact Extraction
# ============================================================

# Phone patterns (find ALL matches)
PHONE_RES = [
    re.compile(r'\+?(?:1[\s\-.]?)?(?:809|829|849)[\s\-.]?\d{3}[\s\-.]?\d{4}'),  # DR
    re.compile(r'\+1[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}'),  # US
    re.compile(r'\+?\d{1,3}[\s\-.]?\(?\d{2,4}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4}'),  # international
    re.compile(r'(?:tel|phone|cel|contacto|llamar|contact)\s*:?\s*\+?([\d\s\-().]{7,20})', re.I),
]

# WhatsApp-specific
WHATSAPP_RES = [
    re.compile(r'wa\.me/(\+?\d{7,15})'),
    re.compile(r'whatsapp\s*:?\s*\+?([\d\s\-().]{7,20})', re.I),
    re.compile(r'[\U0001F4F1\U0001F4DE\u260E]\s*\+?([\d\s\-().]{7,20})'),
]

# Email
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Instagram
INSTAGRAM_RES = [
    re.compile(r'instagram\.com/([a-zA-Z0-9_.]+)', re.I),
    re.compile(r'(?:ig|insta(?:gram)?)\s*:?\s*@?([a-zA-Z0-9_.]{2,30})', re.I),
    re.compile(r'@([a-zA-Z0-9_.]{2,30})'),
]

# Real estate agencies — expanded from researcher data
COMPANY_NAMES = [
    # International franchises
    'RE/MAX', 'REMAX', 'Century 21', 'Coldwell Banker', 'Keller Williams',
    "Sotheby's", 'Sotheby', 'Engel & Volkers',
    'Rent-A-House', 'Rent A House',
    # DR-specific agencies
    'ASTRA Realty', 'Go Punta Cana', 'Blue Caribbean', 'Canablue',
    'Reliable Realty', 'Dominican Home', 'Inversiones AIDES',
    'Lunovi', 'Fritz Cana', 'Noval Properties', 'Tropical Realty',
    'DR Listings', 'Caribbean Realty', 'Punta Cana Realty',
    'Island Living', 'Paradise Realty', 'DR Realty',
    'Bavaro Realty', 'Cap Cana Realty', 'Caribe Realty',
    'Banyan Tree Realty', 'Exotic Realty', 'One Caribbean',
    'Real Vision', 'Dominican Quest', 'Caribbean Island',
    # Generic patterns (match as company indicator)
    'Inmobiliaria', 'Bienes Raices', 'Grupo Inmobiliario',
    'Real Estate Group', 'Realty Group', 'Properties LLC',
]

_company_escaped = [re.escape(c) for c in COMPANY_NAMES]
COMPANY_RE = re.compile(r'\b(' + '|'.join(_company_escaped) + r')\b', re.I)

# Agent heuristics — phrases that suggest professional agent
AGENT_INDICATOR_RE = re.compile(
    r'\b(DM\s*(?:for|me|para)\s*(?:info|details|m[aá]s)|'
    r'cont[aá]ct(?:a|e)?me|contact\s*me|escribeme|'
    r'link\s*(?:in|en)\s*bio|m[aá]s\s*info|more\s*info|'
    r'exclusive\s*listing|listado\s*exclusivo|'
    r'#realestate|#bienesraices|#puntacanarealestate|#investinDR|'
    r'I\s*have\s*(?:more|several)|tengo\s*(?:m[aá]s|varios))\b', re.I)

# Website URLs (not facebook.com or instagram.com)
URL_RE = re.compile(
    r'https?://(?!(?:www\.)?(?:facebook|instagram|fb)\.com)[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}[^\s<>"\']*', re.I)


def _normalize_phone(raw: str) -> str:
    cleaned = re.sub(r'[^\d+]', '', raw)
    if cleaned.startswith('++'):
        cleaned = '+' + cleaned.lstrip('+')
    return cleaned


def extract_contact(text: str) -> Optional[ContactResult]:
    phones = []
    whatsapp = []
    emails = []
    instagram = None
    company = None
    website = None

    for pat in PHONE_RES:
        for m in pat.finditer(text):
            raw = m.group(1) if m.lastindex else m.group(0)
            phone = _normalize_phone(raw)
            if len(phone) >= 7 and phone not in phones:
                phones.append(phone)

    has_wa_mention = bool(re.search(r'whatsapp|wa\.me|wa\s*:', text, re.I))
    for pat in WHATSAPP_RES:
        for m in pat.finditer(text):
            raw = m.group(1) if m.lastindex else m.group(0)
            num = _normalize_phone(raw)
            if len(num) >= 7 and num not in whatsapp:
                whatsapp.append(num)

    if has_wa_mention and not whatsapp and phones:
        whatsapp.append(phones[0])

    for m in EMAIL_RE.finditer(text):
        email = m.group(0).lower()
        if email not in emails:
            emails.append(email)

    for pat in INSTAGRAM_RES:
        m = pat.search(text)
        if m:
            handle = m.group(1).strip().rstrip('.')
            if handle and len(handle) >= 2 and '@' not in handle:
                instagram = handle
                break

    m = COMPANY_RE.search(text)
    if m:
        company = m.group(1)

    m = URL_RE.search(text)
    if m:
        website = m.group(0).rstrip('.,;:!?)')

    has_any = phones or whatsapp or emails or instagram or company or website
    if has_any:
        return ContactResult(
            phones=phones, whatsapp=whatsapp, emails=emails,
            instagram=instagram, company=company, website=website,
        )
    return None


# ============================================================
# Furnishing
# ============================================================

def extract_furnishing(text: str) -> Optional[str]:
    if re.search(r'\b(unfurnished|sin\s*(?:muebles|amueblar)|desamueblado|vac[ií]o)\b', text, re.I):
        return 'unfurnished'
    if re.search(r'\b(semi[\s-]?furnished|semi[\s-]?amueblado|parcialmente)\b', text, re.I):
        return 'semi-furnished'
    if re.search(r'\b(fully\s*furnished|furnished|amueblado|amoblado|equipado|totalmente\s*equipado)\b', text, re.I):
        return 'furnished'
    return None


# ============================================================
# Confidence scoring
# ============================================================

def calculate_confidence(result: 'ParseResult', has_images: bool = False) -> float:
    """
    Score 0.0-1.0 based on how much structured data was extracted.
    Posts below 0.4 → needs_review.
    """
    score = 0.0
    if result.price:
        score += 0.25
    if result.zone:
        score += 0.25
    if result.bedrooms is not None:
        score += 0.15
    if result.contact:
        score += 0.15
    if result.property_type:
        score += 0.10
    if has_images:
        score += 0.10
    return min(score, 1.0)


# ============================================================
# Main parse function
# ============================================================

def parse(raw_text: str, has_images: bool = False) -> ParseResult:
    if not raw_text or len(raw_text.strip()) < 20:
        return ParseResult(needs_review=True, review_reason='text_too_short', is_spam=False)

    # Spam check first
    if is_spam(raw_text):
        return ParseResult(is_spam=True, needs_review=False, review_reason='spam')

    price = extract_price(raw_text)
    zone, community = extract_location(raw_text)
    bedrooms = extract_bedrooms(raw_text)
    property_type = extract_property_type(raw_text, bedrooms=bedrooms)
    bathrooms = extract_bathrooms(raw_text)
    area = extract_area(raw_text)
    listing_type = extract_listing_type(raw_text)
    contact = extract_contact(raw_text)
    furnishing = extract_furnishing(raw_text)
    amenities = extract_amenities(raw_text)

    result = ParseResult(
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        area=area,
        zone=zone,
        community=community,
        property_type=property_type,
        listing_type=listing_type,
        contact=contact,
        furnishing=furnishing,
        amenities=amenities,
    )

    # Confidence scoring
    result.confidence = calculate_confidence(result, has_images)
    result.needs_review = result.confidence < 0.4

    if result.needs_review:
        missing = []
        if not price:
            missing.append('price')
        if not zone:
            missing.append('zone')
        if not bedrooms:
            missing.append('bedrooms')
        if not contact:
            missing.append('contact')
        result.review_reason = 'low_confidence:missing_' + '+'.join(missing)

    return result
