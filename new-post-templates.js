// =============================================================================
// NEW POST TEMPLATES FOR post-generator.html
// =============================================================================
// INSTRUCTIONS:
// 1. Add these category keys to the CATEGORIES object
// 2. Add these template blocks to the POSTS object
// 3. Add Russian to the language dropdown and LANG_LABELS/LANG_COLORS
// =============================================================================

// ---- STEP 1: Add to CATEGORIES object (after "social" entry) ----
//
//     trybeforebuy: { label: "Try Before You Buy", icon: "🏠" },
//     rental:     { label: "Rental Income", icon: "🔑" },
//     resort:     { label: "Resort Living", icon: "🏖️" },
//     roi:        { label: "ROI Deep Dive", icon: "📊" },
//     lifestyle2: { label: "Lifestyle II", icon: "🌅" }
//

// ---- STEP 2: Add Russian to language dropdown HTML ----
//
//     <option value="ru">Europe/Russia (Russian)</option>
//

// ---- STEP 3: Update LANG_LABELS and LANG_COLORS ----
//
// const LANG_LABELS = { en: 'USA', es: 'Dominican/LatAm', fr: 'Quebec', ru: 'Russian' };
// const LANG_COLORS = { en: 'en', es: 'es', fr: 'fr', ru: 'ru' };
//

// ---- STEP 4: Update langs array in generateAll() ----
//
//     const langs = langFilter === 'all' ? ['en', 'es', 'fr', 'ru'] : [langFilter];
//

// ---- STEP 5: Add these template blocks inside POSTS object ----

const NEW_TEMPLATES = {

    // ==========================================================
    // CATEGORY: Try Before You Buy (4 languages)
    // ==========================================================
    trybeforebuy: {
        en: (p) => `Not sure about buying in Punta Cana? Come stay first.

Our "Try Before You Buy" program lets you:
- Stay in the actual unit (or one just like it)
- Experience the Melia Hotel beach, pool, and restaurants firsthand
- Tour Cocotal Golf and the surrounding area
- Meet the attorney who handles closings
- See completed projects and talk to real owners

No pressure, no gimmicks. Just come see if this lifestyle fits you.

2BR at Cocotal Golf - ${p.price}. ${p.specs_en}.

We'll even credit your trip toward the purchase.

DM me to plan your visit.
${p.site_link}`,
        es: (p) => `No estas seguro de comprar en Punta Cana? Ven a probar primero.

Nuestro programa "Prueba Antes de Comprar" te permite:
- Quedarte en el apartamento real (o uno similar)
- Disfrutar la playa, piscina y restaurantes del Hotel Melia
- Recorrer Cocotal Golf y los alrededores
- Conocer al abogado que maneja los cierres
- Ver proyectos terminados y hablar con duenos reales

Sin presion. Ven, vive la experiencia, y decide despues.

2 habitaciones en Cocotal Golf - US${p.price}. ${p.specs_es}.

Te acreditamos el costo del viaje si decides comprar.

Escribeme para planificar tu visita.
${p.site_link}`,
        fr: (p) => `Pas certain d'acheter a Punta Cana? Viens essayer avant.

Notre programme "Essaie avant d'acheter" te permet de:
- Sejourner dans le condo reel (ou un similaire)
- Profiter de la plage, la piscine et les restos du Melia
- Visiter Cocotal Golf et les environs
- Rencontrer l'avocat qui gere les transactions
- Voir des projets completes et parler a de vrais proprietaires

Zero pression. Viens vivre l'experience et decide apres.

Condo 2 chambres a Cocotal Golf - US${p.price}. ${p.specs_fr}.

On credite le cout de ton voyage si tu achetes.

Ecris-moi pour organiser ta visite.
${p.site_link}`,
        ru: (p) => `Ne uvereny, chto hotite pokupat v Punta Cana? Priezzhajte snachala poprobovat.

Nasha programma "Poprobuj do pokupki":
- Prozhivanie v realnyh apartamentah (ili analogichnyh)
- Plyazh, bassejn i restorany otelya Melia — lichnyj opyt
- Ekskursiya po Cocotal Golf i okrestnostyam
- Vstrecha s advokatom, vedushchim sdelki
- Osmotr zavershyonnyh proektov i obshchenie s realnymi vladeltsami

Bez davleniya. Priezzhajte, otsените zhizn zdes, i reshajte potom.

2 spalni v Cocotal Golf - US${p.price}. 144 kv.m.

Stoimost poezdki zachityvaetsya pri pokupke.

Napishite, chtoby zaplanirovat vizit.
${p.site_link}`
    },

    // ==========================================================
    // CATEGORY: Rental Income (4 languages)
    // ==========================================================
    rental: {
        en: (p) => `Your tenants pay your mortgage while you sleep.

Here's what a 2BR in Cocotal Golf actually earns on Airbnb:

Peak season (Dec-Apr): $180-250/night, 85%+ occupancy
Shoulder (May-Jun, Nov): $140-180/night, 70% occupancy
Low season (Jul-Oct): $120-150/night, 60% occupancy

Annual gross: $28,000-$42,000
Management fees (25%): -$7,000-$10,500
Net to you: $21,000-$31,500

That's a 6.7-10% NET yield on a ${p.price} property.

And you still get to use it whenever you want. Just block your dates.

${p.specs_en}. Golf views. Melia Hotel beach access.

Want the full rental projection? DM me.
${p.site_link}`,
        es: (p) => `Tus huespedes pagan tu hipoteca mientras duermes.

Esto es lo que gana un apartamento 2 hab en Cocotal Golf en Airbnb:

Temporada alta (Dic-Abr): $180-250/noche, 85%+ ocupacion
Media (May-Jun, Nov): $140-180/noche, 70% ocupacion
Baja (Jul-Oct): $120-150/noche, 60% ocupacion

Ingreso bruto anual: $28,000-$42,000
Administracion (25%): -$7,000-$10,500
Neto para ti: $21,000-$31,500

Eso es 6.7-10% de retorno NETO sobre US${p.price}.

Y lo puedes usar cuando quieras. Solo bloqueas tus fechas.

${p.specs_es}. Vista al golf. Playa del Hotel Melia.

Quieres la proyeccion completa? Escribeme.
${p.site_link}`,
        fr: (p) => `Tes locataires payent ton hypotheque pendant que tu dors.

Voici ce qu'un condo 2 chambres a Cocotal Golf genere sur Airbnb:

Haute saison (dec-avr): $180-250/nuit, 85%+ d'occupation
Moyenne (mai-jun, nov): $140-180/nuit, 70% d'occupation
Basse (jul-oct): $120-150/nuit, 60% d'occupation

Revenu brut annuel: $28,000-$42,000
Frais de gestion (25%): -$7,000-$10,500
Net pour toi: $21,000-$31,500

Ca fait 6.7-10% de rendement NET sur un condo a US${p.price}.

Et tu peux l'utiliser quand tu veux. Bloque tes dates, c'est tout.

${p.specs_fr}. Vue sur le golf. Plage du Melia.

Tu veux la projection complete? Ecris-moi.
${p.site_link}`,
        ru: (p) => `Vashi arendatory platyat vashu ipoteku, poka vy spite.

Vot chto zarbatyvaet 2-komnatnaya kvartira v Cocotal Golf na Airbnb:

Vysokij sezon (dek-apr): $180-250/noch, 85%+ zagruzka
Srednij (maj-iun, noy): $140-180/noch, 70% zagruzka
Nizkij (iul-okt): $120-150/noch, 60% zagruzka

Valovoj godovoj dohod: $28,000-$42,000
Komissiya upravleniya (25%): -$7,000-$10,500
Chisto vam: $21,000-$31,500

Eto 6.7-10% CHISTOJ dohodnosti pri stoimosti US${p.price}.

I vy mozhete polzovatsya kogda ugodno. Prosto blokirujte svoi daty.

144 kv.m. Vid na golf. Plyazh otelya Melia.

Hotite polnuyu proektsiyu dohodov? Napishite.
${p.site_link}`
    },

    // ==========================================================
    // CATEGORY: Resort Living (4 languages)
    // ==========================================================
    resort: {
        en: (p) => `This is what your morning looks like at Cocotal Golf:

7:00 AM - Coffee on your terrace, golf course stretching out below
8:30 AM - Walk to Melia Hotel for a swim in the pool
10:00 AM - Beach day at the Melia's private beach
12:30 PM - Lunch at one of the resort's restaurants
2:00 PM - Back home for remote work with ocean breeze through the windows
5:00 PM - Sunset round of golf or spa session
7:30 PM - Dinner at the Beach Club

This isn't a vacation. This is your daily life.

2BR, ${p.specs_en}. ${p.price}.

DM me to see the property.
${p.site_link}`,
        es: (p) => `Asi se ve tu manana en Cocotal Golf:

7:00 AM - Cafe en tu terraza con vista al campo de golf
8:30 AM - Caminas al Hotel Melia para un chapuzon en la piscina
10:00 AM - Dia de playa en la playa privada del Melia
12:30 PM - Almuerzo en uno de los restaurantes del resort
2:00 PM - De vuelta a casa para trabajar remoto con brisa del mar
5:00 PM - Atardecer jugando golf o sesion de spa
7:30 PM - Cena en el Beach Club

Esto no es una vacacion. Es tu vida diaria.

2 hab, ${p.specs_es}. US${p.price}.

Escribeme para ver la propiedad.
${p.site_link}`,
        fr: (p) => `Voici a quoi ressemble ton matin a Cocotal Golf:

7h00 - Cafe sur ta terrasse, le parcours de golf devant toi
8h30 - Marche jusqu'au Melia pour un plongeon dans la piscine
10h00 - Journee plage sur la plage privee du Melia
12h30 - Diner dans un des restos du resort
14h00 - Retour chez toi pour travailler a distance avec la brise de mer
17h00 - Golf au coucher du soleil ou session spa
19h30 - Souper au Beach Club

C'est pas des vacances. C'est ta vie de tous les jours.

2 chambres, ${p.specs_fr}. US${p.price}.

Ecris-moi pour voir le condo.
${p.site_link}`,
        ru: (p) => `Vot kak vyglyadit vashe utro v Cocotal Golf:

7:00 - Kofe na terrasse, pole dlya golfa raskinulos vnizu
8:30 - Progulka do otelya Melia, kupanie v bassejne
10:00 - Den na chastnom plyazhe Melia
12:30 - Obed v odnom iz restoranov kurorta
14:00 - Domoj na udalyonnuyu rabotu s morskim vetrom v oknah
17:00 - Golf na zakate ili spa-sessiya
19:30 - Uzhin v Beach Club

Eto ne otpusk. Eto vasha povsednevnaya zhizn.

2 spalni, 144 kv.m. US${p.price}.

Napishite, chtoby uvidet nedvizhimost.
${p.site_link}`
    },

    // ==========================================================
    // CATEGORY: ROI Deep Dive (4 languages)
    // ==========================================================
    roi: {
        en: (p) => `Let's talk real numbers. No hype, just math.

PURCHASE: ${p.price}
Closing costs: ~$8,000 (attorney, notary, registration)
Furnishing: ~$12,000 (turnkey rental-ready)
TOTAL IN: ~$335,000

ANNUAL INCOME (Airbnb, managed):
Gross rental: $35,000 (conservative, 72% occupancy avg)
Management fee (-25%): -$8,750
HOA/utilities: -$4,800
Maintenance reserve: -$1,200
NET ANNUAL INCOME: ~$20,250

NET YIELD: 6.0%
Plus appreciation: 5-8% per year historically
TOTAL RETURN: 11-14% annually

Compare that to a savings account, a REIT, or a rental in the US.

${p.specs_en}. Golf views. Melia Hotel access.

Want me to run the numbers for YOUR scenario? DM me.
${p.site_link}`,
        es: (p) => `Hablemos de numeros reales. Sin hype, solo matematica.

COMPRA: US${p.price}
Costos de cierre: ~$8,000 (abogado, notario, registro)
Amueblado: ~$12,000 (listo para rentar)
TOTAL INVERTIDO: ~$335,000

INGRESO ANUAL (Airbnb, administrado):
Renta bruta: $35,000 (conservador, 72% ocupacion promedio)
Administracion (-25%): -$8,750
HOA/servicios: -$4,800
Reserva mantenimiento: -$1,200
INGRESO NETO ANUAL: ~$20,250

RENDIMIENTO NETO: 6.0%
Mas plusvalia: 5-8% anual historicamente
RETORNO TOTAL: 11-14% anual

Compara eso con una cuenta de ahorro, un REIT, o un alquiler en USA.

${p.specs_es}. Vista al golf. Acceso Hotel Melia.

Quieres que haga los numeros para TU caso? Escribeme.
${p.site_link}`,
        fr: (p) => `Parlons de vrais chiffres. Pas de hype, juste du math.

ACHAT: US${p.price}
Frais de cloture: ~$8,000 (avocat, notaire, enregistrement)
Ameublement: ~$12,000 (cle en main, pret a louer)
TOTAL INVESTI: ~$335,000

REVENU ANNUEL (Airbnb, gere):
Location brute: $35,000 (conservateur, 72% d'occupation moy.)
Gestion (-25%): -$8,750
Charges/services: -$4,800
Reserve entretien: -$1,200
REVENU NET ANNUEL: ~$20,250

RENDEMENT NET: 6.0%
Plus appreciation: 5-8% par an historiquement
RENDEMENT TOTAL: 11-14% par annee

Compare ca a un compte epargne, un FPI, ou un loyer au Quebec.

${p.specs_fr}. Vue sur le golf. Acces Hotel Melia.

Tu veux que je fasse les chiffres pour TON scenario? Ecris-moi.
${p.site_link}`,
        ru: (p) => `Pogovorim o realnyh cifrah. Bez hajpa, tolko matematika.

POKUPKA: US${p.price}
Zatraty na zakrytie: ~$8,000 (advokat, notarius, registratsiya)
Meblirovka: ~$12,000 (gotovo k sdache)
VSEGO VLOZHENO: ~$335,000

GODOVOJ DOHOD (Airbnb, s upravleniem):
Valovaya arenda: $35,000 (konservativno, 72% zagruzki)
Upravlenie (-25%): -$8,750
Kommunalnye/obsluzhivanie: -$4,800
Rezerv na remont: -$1,200
CHISTYJ GODOVOJ DOHOD: ~$20,250

CHISTAYA DOHODNOST: 6.0%
Plyus rost stoimosti: 5-8% v god istoricheski
OBSHCHIJ DOKHOD: 11-14% v god

Sravnite s bankovskim vkladom, fondom nedvizhimosti ili arendoj v SSHA.

144 kv.m. Vid na golf. Dostup k otelyu Melia.

Hotite raschet dlya VASHEGO scenariya? Napishite.
${p.site_link}`
    },

    // ==========================================================
    // CATEGORY: Lifestyle II (4 languages)
    // ==========================================================
    lifestyle2: {
        en: (p) => `People ask me: "What's it actually like living in Punta Cana?"

Here's the honest answer:

- Groceries cost 40-50% less than US cities
- A great dinner out: $15-25 per person
- Full-time housekeeper: $300-400/month
- High-speed internet: $40/month (yes, it works for Zoom calls)
- Private health insurance: $80-150/month
- Golf membership at Cocotal: included with your HOA
- Beach access via Melia: included with your unit

It's not "roughing it" in the Caribbean. It's living BETTER for less.

2BR at Cocotal Golf. ${p.specs_en}. ${p.price}.

Ready to upgrade your life? DM me.
${p.site_link}`,
        es: (p) => `La gente me pregunta: "Como es realmente vivir en Punta Cana?"

La respuesta honesta:

- El supermercado cuesta 40-50% menos que en USA
- Una buena cena: $15-25 por persona
- Empleada domestica full-time: $300-400/mes
- Internet de alta velocidad: $40/mes (si, funciona para Zoom)
- Seguro medico privado: $80-150/mes
- Golf en Cocotal: incluido en tu mantenimiento
- Acceso a playa del Melia: incluido con tu unidad

No es "sacrificarse" en el Caribe. Es vivir MEJOR por menos.

2 hab en Cocotal Golf. ${p.specs_es}. US${p.price}.

Listo para mejorar tu vida? Escribeme.
${p.site_link}`,
        fr: (p) => `Le monde me demande: "C'est comment vivre a Punta Cana pour vrai?"

La reponse honnete:

- L'epicerie coute 40-50% moins cher qu'a Montreal
- Un bon souper au resto: $15-25 par personne
- Femme de menage a temps plein: $300-400/mois
- Internet haute vitesse: $40/mois (oui, ca marche pour Zoom)
- Assurance sante privee: $80-150/mois
- Golf a Cocotal: inclus dans tes charges de condo
- Acces plage du Melia: inclus avec ton unite

C'est pas "endurer" dans les Caraibes. C'est vivre MIEUX pour moins cher.

Condo 2 chambres a Cocotal Golf. ${p.specs_fr}. US${p.price}.

Pret a ameliorer ta vie? Ecris-moi.
${p.site_link}`,
        ru: (p) => `Menya chasto sprashivayut: "Kak na samom dele zhit v Punta Cana?"

Chestnyj otvet:

- Produkty na 40-50% deshevle, chem v krupnyh gorodah SSHA
- Horoshij uzhin v restorane: $15-25 na cheloveka
- Domrabotnitsa na polnyj den: $300-400/mesyats
- Skorostnoj internet: $40/mesyats (da, Zoom rabotaet)
- Chastnaya medstrahovka: $80-150/mesyats
- Golf v Cocotal: vklyuchyon v obsluzhivanie
- Dostup k plyazhu Melia: vklyuchyon v vashu edinitsu

Eto ne "vyzhivanie" v Karibah. Eto zhizn LUCHSHE za menshe deneg.

2 spalni v Cocotal Golf. 144 kv.m. US${p.price}.

Gotovy uluchshit svoyu zhizn? Napishite.
${p.site_link}`
    }
};

// =============================================================================
// SUMMARY: 5 new categories x 4 languages = 20 new post templates
//
// Categories added:
// 1. trybeforebuy - "Try Before You Buy" program (stay in the unit, tour area, no pressure)
// 2. rental       - Detailed rental income breakdown by season
// 3. resort       - "Day in the life" at Cocotal Golf / Melia resort
// 4. roi          - Full ROI calculation with real numbers
// 5. lifestyle2   - Cost of living reality (groceries, healthcare, internet, staff)
//
// All templates follow these guidelines:
// - CONFOTUR is NOT mentioned as a main selling point
// - Focus: lifestyle, ROI, rental income, location, Try Before You Buy
// - EN: professional American English
// - ES: Dominican-flavored Spanish (tu, direct, warm)
// - FR: Quebec French (tu, condo, restos, jaser, souper)
// - RU: Transliterated Russian (matching existing template style)
// =============================================================================
