# Airbnb Dashboard Backend Integration Report

## 1. Current Dashboard Analysis

The existing `airbnb-dashboard.html` is a fully functional single-page app with 6 sections:

- **Properties**: Card grid showing 7 sample properties (Villa Bavaro Sunrise, Condo Cap Cana Marina, etc.) with status, nightly rate, occupancy bar
- **Calendar**: Gantt-style monthly view with booking blocks per property
- **Revenue**: YTD stats (revenue, expenses, net profit, ADR, occupancy), bar chart by property, expense tracker, P&L summary
- **Guest Pipeline**: Buyer scoring system (Hot/Warm/Cold) based on stays, country, notes keywords (buy/invest/property)
- **Cleaning**: Auto-generated tasks from checkout dates, cleaner assignment, WhatsApp notify
- **Templates**: 7 multilingual (EN/ES/FR) message templates with placeholder substitution

**Current data layer**: `localStorage` with JSON import/export. No backend API.

### Data Schema (Current)

```json
{
  "properties": [{ "id", "name", "status", "nightlyRate" }],
  "bookings": [{ "id", "propertyId", "guest", "checkIn", "checkOut", "nightlyRate", "platform", "country", "notes" }],
  "expenses": [{ "id", "propertyId", "date", "category", "amount", "note" }],
  "cleaners": [{ "id", "name", "phone" }],
  "cleaningTasks": [{ "id", "bookingId", "propertyId", "checkOut", "guest", "cleanerId", "status" }],
  "guestNotes": { "guest_name_lowercase": "note text" },
  "nextId": 100
}
```

---

## 2. Airbnb Data Access Options

### Option A: Official Airbnb API (NOT Recommended)

- **Status**: Closed to individual hosts. Only approved partners (PMS/channel managers) get access.
- **What it does**: Real-time sync of rates, availability, booking details, guest info
- **Barrier**: Must be an established software company with significant user base. Airbnb reaches out to prospective partners — you cannot apply.
- **Verdict**: Not viable for a 1-3 property operation.

### Option B: AirDNA ($100/mo)

- **What it does**: Market analytics — occupancy rates, ADR, revenue estimates, comp set analysis for 10M+ listings
- **Useful for**: Competitive pricing analysis, market benchmarking
- **API access**: Available on Enterprise plan (custom pricing)
- **Verdict**: Good for market research but overkill for operational tracking of your own properties. More useful for the investment/sales pitch side.

### Option C: Mashvisor ($25/mo)

- **What it does**: Investment analytics, ROI calculations, neighborhood comparisons, rental data
- **API**: Available, covers Airbnb data + long-term rental rates + property data
- **Verdict**: Better value than AirDNA for investment analysis. Still doesn't solve operational tracking.

### Option D: PricelLabs / Wheelhouse / Beyond ($20-30/mo)

- **What it does**: Dynamic pricing — automatically adjusts your Airbnb nightly rates based on demand, seasonality, events, comp set
- **Integration**: Connects directly to Airbnb via channel manager permissions
- **Verdict**: HIGHLY recommended for pricing optimization. Can increase revenue 15-36% according to industry data.

### Option E: Google Sheets Backend (RECOMMENDED for operations)

- **What it does**: Centralized data store accessible from any device, collaborative, free
- **Integration**: Google Sheets API for read/write, or simple fetch of published CSV/JSON
- **Verdict**: Best fit for 1-3 properties. Zero cost, easy to maintain, collaborative.

### Option F: Simple JSON File on Server

- **What it does**: Static JSON file served from the same hosting, manually edited or updated via simple admin
- **Integration**: Dashboard fetches JSON on load instead of localStorage
- **Verdict**: Simplest possible backend. Good if only one person updates data.

---

## 3. Recommended Architecture

### Tier 1: Immediate (Free, No Dependencies)

**Google Sheets as Backend**

```
[Google Sheet] --> [Published as JSON] --> [Dashboard fetches on load]
                                      --> [localStorage as offline cache]
```

**Implementation:**
1. Create a Google Sheet with tabs: Properties, Bookings, Expenses, Cleaners, CleaningTasks, GuestNotes
2. Publish each sheet as CSV/JSON via `https://docs.google.com/spreadsheets/d/{ID}/gviz/tq?tqx=out:json&sheet={TAB}`
3. Dashboard loads from Google Sheets on startup, falls back to localStorage if offline
4. Data entry can happen in either the dashboard UI OR directly in Google Sheets
5. Dashboard writes back to localStorage + optionally to Google Sheets via Apps Script web app

**Pros:**
- Free, no server needed
- Multiple people can edit data
- Built-in version history
- Works with existing dashboard code (minimal changes)
- Mobile-friendly via Google Sheets app

**Cons:**
- ~1-2s load delay for initial fetch
- Google Sheets API has rate limits (but fine for 1-3 properties)
- Two-way sync requires Google Apps Script (medium complexity)

### Tier 2: Growth Phase (When you hit 3+ properties)

**Lightweight API + Database**

Add a small FastAPI or Express backend (could share Railway with QChulo backend) with:
- PostgreSQL for persistent storage
- REST API matching current data schema
- iCal import from Airbnb/VRBO/Booking.com calendars (free, no API approval needed)
- Webhook receiver for PriceLabs/dynamic pricing tool

### Tier 3: Scale Phase (5+ properties)

- Full PMS integration (Guesty, Hospitable, or OwnerRez)
- These connect to Airbnb API as approved partners
- Cost: $10-25/property/month
- Handles multi-channel sync, automated messaging, cleaning coordination

---

## 4. Data Schema for Backend

### Google Sheets Tab: Properties

| Column | Type | Example |
|--------|------|---------|
| id | string | p1 |
| name | string | Villa Bavaro Sunrise |
| status | enum | occupied/vacant/cleaning/maintenance |
| nightlyRate | number | 185 |
| address | string | Bavaro, Los Corales |
| bedrooms | number | 2 |
| bathrooms | number | 2 |
| maxGuests | number | 6 |
| airbnbUrl | string | https://airbnb.com/rooms/123 |
| icalUrl | string | (Airbnb iCal export URL) |
| cleaningFee | number | 45 |
| monthlyHOA | number | 250 |

### Google Sheets Tab: Bookings

| Column | Type | Example |
|--------|------|---------|
| id | string | b1 |
| propertyId | string | p1 |
| guest | string | Sarah Thompson |
| checkIn | date | 2026-03-04 |
| checkOut | date | 2026-03-11 |
| nightlyRate | number | 185 |
| platform | enum | Airbnb/VRBO/Booking.com/Direct |
| country | string | USA |
| notes | string | Asked about buying |
| totalPayout | number | 1200 |
| status | enum | confirmed/completed/cancelled |
| guestEmail | string | (optional) |
| guestPhone | string | (optional) |

### Google Sheets Tab: Expenses

| Column | Type | Example |
|--------|------|---------|
| id | string | e1 |
| propertyId | string | p1 |
| date | date | 2026-03-01 |
| category | enum | Cleaning/Maintenance/Supplies/HOA/Utilities/Insurance/Taxes/Management |
| amount | number | 45 |
| note | string | Turnover clean |
| recurring | boolean | false |

### Google Sheets Tab: GuestNotes

| Column | Type | Example |
|--------|------|---------|
| guestKey | string | sarah thompson |
| notes | string | Interested in investment |
| buyerScore | enum | Hot/Warm/Cold |
| followUpDate | date | 2026-03-20 |

---

## 5. iCal Sync (Free Airbnb Calendar Import)

Every Airbnb listing has an iCal export URL. This is the simplest way to get real booking data without any API approval:

1. In Airbnb host dashboard: Listing > Availability > Connect Calendar > Export Calendar
2. Get the `.ics` URL (e.g., `https://www.airbnb.com/calendar/ical/12345.ics?s=abc123`)
3. Dashboard or backend fetches this URL periodically
4. Parse iCal events to extract: guest name (from SUMMARY), check-in/check-out (DTSTART/DTEND), blocked dates

**Limitation**: iCal only gives dates and guest first name. No pricing, no contact info, no platform details. Manual entry still needed for financials.

---

## 6. Punta Cana Market Intelligence

### Occupancy Benchmarks (2025-2026)

| Metric | Average Host | Top 25% | Top 10% |
|--------|-------------|---------|---------|
| Occupancy | 49% | 52% | 62%+ |
| Nights/month | ~15 | ~16 | 18-21 |
| Monthly Revenue (low season) | ~$1,250 | -- | -- |
| Monthly Revenue (high season) | ~$2,550 | -- | -- |

### Seasonal Calendar

| Season | Months | Strategy |
|--------|--------|----------|
| **Peak** | Dec 15 - Apr 15 | Premium pricing (+30-50%), 3-night minimum, strict cancellation |
| **Shoulder** | Apr 15 - Jun, Nov - Dec 15 | Standard pricing, 2-night minimum |
| **Low** | Jul - Oct | Discount 15-25%, weekly/monthly discounts, flexible cancellation, target remote workers |

### Key Events to Price For

- **Christmas/New Year** (Dec 20 - Jan 5): Maximum rates, book 2-3 months ahead
- **Semana Santa** (Easter week): Dominican domestic tourism surge
- **US Presidents' Day weekend** (Feb): US travelers
- **Spring Break** (Mar-Apr): College-age + families
- **Dominican Independence Day** (Feb 27): Local tourism
- **PGA/Golf tournaments at Corales**: Cap Cana premium
- **Summer (Jul-Aug)**: European travelers + Dominican diaspora returning

### Top-Performing Neighborhoods

1. **Los Corales / El Cortecito**: Walk to Bavaro Beach, restaurants, nightlife. Best for studios/1BR.
2. **Cap Cana (Juanillo)**: Luxury segment. Villas with private pools. $300+ nightly.
3. **Cana Bay / Arena Gorda**: Resort-area feel, good for families.
4. **Cocotal Golf**: Mid-range, golf access, quiet. Good for couples.

---

## 7. Listing Optimization Checklist

### Photography (Most Important Factor)
- Professional photos (not phone) — budget $200-400 for a shoot
- Hero image: Pool/terrace with ocean or palm trees visible
- Show every room, bathroom, kitchen fully staged
- Golden hour exterior shots
- Drone shot if property has views
- Lifestyle shots: breakfast on terrace, cocktails by pool

### Title Formula
`[Property Type] [Key Feature] [Location] | [Amenity]`
- "Luxury 2BR Condo Steps from Bavaro Beach | Pool & Rooftop"
- "Cap Cana Villa with Private Pool | Golf & Beach Club Access"

### Must-Have Amenities (Punta Cana specific)
- AC in every room (non-negotiable)
- High-speed WiFi (50+ Mbps)
- Backup power / inverter (power outages are common in DR)
- Pool access (shared or private)
- Hot water
- Smart lock (keyless entry)
- Washer/dryer
- Workspace (for remote workers — growing segment)
- Quality linens & towels
- Beach chairs/cooler available
- Netflix/streaming on smart TV

### Review Strategy
- Respond to every review within 24 hours
- Send checkout reminder requesting review (template already in dashboard)
- Target 4.8+ overall rating
- Address any negative feedback publicly and constructively

---

## 8. Pricing Strategy

### Base Rate Guidelines (Punta Cana 2026)

| Property Type | Low Season | Shoulder | Peak | Holiday Peak |
|--------------|-----------|----------|------|-------------|
| Studio/1BR | $65-95 | $85-120 | $120-160 | $160-220 |
| 2BR Condo | $95-150 | $140-200 | $200-280 | $280-380 |
| 3BR Villa | $150-250 | $220-320 | $320-450 | $450-600 |
| Luxury Villa (pool) | $280-425 | $380-550 | $550-750 | $750-1000+ |

### Dynamic Pricing Tool Recommendation

**PriceLabs** ($20/mo per listing)
- Connects directly to Airbnb
- Auto-adjusts based on: local demand, day of week, seasonality, events, lead time, orphan days
- Customizable min/max prices, last-minute discounts
- Has Punta Cana market data built in
- ROI: Hosts report 15-36% revenue increase

### Discount Strategy
- **Weekly discount**: 10-15% (encourages longer stays, fewer turnovers)
- **Monthly discount**: 25-40% (target remote workers, snowbirds)
- **Last-minute (within 3 days)**: 15-20% off (better than empty night)
- **Early bird (60+ days out)**: 5% off (lock in bookings early)

---

## 9. Competitor Analysis — What Top PC Listings Do Well

### Common Patterns in Top-Rated Listings (4.8+ stars)

1. **Instant Book enabled** — Airbnb algorithm favors this heavily
2. **Response time < 1 hour** — Superhost requirement
3. **Professional photos** — Consistent style, bright, well-composed
4. **Detailed house manual** — Digital guidebook with local tips
5. **Concierge touches** — Airport transfer arrangement, excursion booking
6. **Welcome basket** — Local fruits, rum, coffee, water bottles
7. **Bilingual** — EN + ES descriptions (FR is a bonus for Quebec market)
8. **Smart pricing** — Not static; adjusts with market
9. **5-star cleaning** — Most common complaint in Punta Cana reviews is cleanliness
10. **Fast WiFi** — Advertise actual speed test results

### Differentiators for Standing Out
- Offer a "Punta Cana Experience Guide" (printed or digital) — local restaurants, beaches, activities
- Partner with local tour operators for guest discounts
- Provide a WhatsApp number for real-time support (already built into dashboard!)
- "Try Before You Buy" program for investor-guests (already on the website!)

---

## 10. Implementation Roadmap

### Phase 1: Quick Win (This Week)
1. Create Google Sheet with the schema from Section 4
2. Populate with real property data
3. Add a `fetchFromSheet()` function to dashboard that loads on startup
4. Keep localStorage as write target + offline fallback

### Phase 2: Sync (Week 2)
1. Deploy Google Apps Script web app as write endpoint
2. Dashboard saves to both localStorage AND Google Sheets
3. Add iCal import for each property's Airbnb calendar
4. Auto-populate bookings from iCal data

### Phase 3: Pricing (Week 3-4)
1. Sign up for PriceLabs ($20/listing/mo)
2. Connect Airbnb listings
3. Set min/max prices per season using the rates table above
4. Monitor for 1 month, adjust

### Phase 4: Scale (Month 2+)
1. If managing 3+ properties, evaluate Hospitable or Guesty Lite
2. Migrate Google Sheets data to PostgreSQL if needed
3. Add automated messaging via Airbnb's approved PMS integration

---

## Summary of Recommendations

| Need | Solution | Cost | Priority |
|------|----------|------|----------|
| Data persistence | Google Sheets backend | Free | HIGH |
| Calendar sync | Airbnb iCal export | Free | HIGH |
| Dynamic pricing | PriceLabs | $20/listing/mo | HIGH |
| Market research | AirDNA (or free Airbtics) | $0-100/mo | MEDIUM |
| Full PMS | Hospitable/Guesty Lite | $10-25/listing/mo | LOW (wait for 3+ properties) |
| Automated messaging | Dashboard templates + WhatsApp | Free (built) | ALREADY DONE |

The Google Sheets approach is the right balance of simplicity, cost, and functionality for a 1-3 property operation. It integrates cleanly with the existing dashboard (just swap the data source from localStorage to a sheet fetch), requires no server infrastructure, and can be upgraded to a proper backend later without changing the UI.
