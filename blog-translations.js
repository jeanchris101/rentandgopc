(function() {
const BLOG_ES = {
  // Nav (shared keys)
  nav_properties: "Propiedades",
  blog_nav: "Guía",
  nav_contact: "Contacto",

  // Hero
  blog_title: "Guía para Comprar Propiedad en Punta Cana",
  blog_subtitle: "Todo lo que necesitas saber: leyes, impuestos, proceso y respuestas a las preguntas más frecuentes.",

  // Table of Contents
  blog_toc: "Tabla de Contenido",
  blog_toc_1: "¿Por qué Punta Cana?",
  blog_toc_2: "¿Pueden los Extranjeros Comprar?",
  blog_toc_3: "Ley CONFOTUR Explicada",
  blog_toc_4: "El Proceso de Compra Paso a Paso",
  blog_toc_5: "Impuestos y Costos de Cierre",
  blog_toc_6: "Ingresos por Alquiler y Airbnb",
  blog_toc_7: "Residencia a través de Propiedad",
  blog_toc_8: "Preguntas Frecuentes",

  // Section 1: Why Punta Cana
  blog_s1_title: "1. ¿Por qué Punta Cana?",
  blog_s1_p1: "Punta Cana es el destino más visitado del Caribe, recibiendo más de 7 millones de turistas al año. Ubicada en el extremo este de la República Dominicana, ofrece más de 100 kilómetros de playas de arena blanca, campos de golf de clase mundial y un mercado inmobiliario en rápido crecimiento.",
  blog_s1_p2: "La región ha visto una inversión masiva en infraestructura en los últimos años: nuevas autopistas, hospitales internacionales (Hospiten, HOMS), internet de fibra óptica y un aeropuerto en expansión (PUJ) con vuelos directos desde más de 80 ciudades en todo el mundo, incluyendo Nueva York, Miami, Montreal, Madrid y Moscú.",
  blog_s1_box_title: "Cifras Clave",
  blog_s1_box_1: "7+ millones de turistas al año",
  blog_s1_box_2: "Vuelos directos desde 80+ ciudades (EE.UU., Canadá, Europa, LatAm)",
  blog_s1_box_3: "Temperatura promedio: 27°C / 80°F todo el año",
  blog_s1_box_4: "Apreciación inmobiliaria: 5-10% anual",
  blog_s1_box_5: "Tasa de ocupación en Airbnb: 65-80% en zonas turísticas",
  blog_s1_box_6: "Costo de vida: 50-70% más bajo que las principales ciudades de EE.UU.",
  blog_s1_p3: "Las zonas más populares incluyen Bávaro (la franja turística principal), Cap Cana (lujo), Cocotal (comunidad de golf con acceso al Hotel Meliá) y Punta Cana Village (cerca del aeropuerto). Cada zona tiene su propio carácter y rango de precios, desde estudios de $100,000 hasta villas de varios millones de dólares.",

  // Section 2: Foreign Ownership
  blog_s2_title: "2. ¿Pueden los Extranjeros Comprar Propiedad?",
  blog_s2_p1: "Sí. La República Dominicana permite la propiedad 100% extranjera de bienes inmuebles sin restricciones. No necesitas ser residente, tener una pareja dominicana ni constituir una empresa local. Un extranjero tiene exactamente los mismos derechos de propiedad que un ciudadano dominicano.",
  blog_s2_p2: "Las propiedades se registran en el Registro de Títulos y recibes un Certificado de Título a tu nombre. Este es un documento respaldado por el gobierno que demuestra tu propiedad.",
  blog_s2_box_title: "Documentos que Necesitas",
  blog_s2_box_1: "Pasaporte vigente",
  blog_s2_box_2: "Prueba de fondos (estado de cuenta bancario)",
  blog_s2_box_3: "Eso es todo. No se necesita visa, residencia ni empresa local.",
  blog_s2_p3: "Recomendamos fuertemente contratar un abogado inmobiliario dominicano para realizar la debida diligencia antes de comprar. El abogado verificará el título, revisará si existen gravámenes o cargas, y se asegurará de que la propiedad esté debidamente registrada. Los honorarios legales típicamente oscilan entre 1-1.5% del precio de compra.",

  // Section 3: CONFOTUR
  blog_s3_title: "3. Ley CONFOTUR Explicada",
  blog_s3_p1: "CONFOTUR (Ley 158-01) es el incentivo más poderoso de la República Dominicana para inversionistas inmobiliarios. Fue diseñada para promover el desarrollo turístico otorgando generosas exenciones fiscales a proyectos que califiquen.",
  blog_s3_p2: "Si una propiedad tiene certificación CONFOTUR, el comprador recibe las siguientes exenciones por 15 años a partir de la fecha de compra:",
  blog_s3_th1: "Impuesto",
  blog_s3_th2: "Tasa Normal",
  blog_s3_th3: "Con CONFOTUR",
  blog_s3_r1c1: "Impuesto de Transferencia (único al cierre)",
  blog_s3_r2c1: "Impuesto Anual a la Propiedad (IPI)",
  blog_s3_r2note: "(sobre el valor superior a ~$7.7M DOP)",
  blog_s3_r3c1: "Impuesto sobre Ganancias de Capital (al vender)",
  blog_s3_r4c1: "Impuesto sobre Ingresos por Alquiler",
  blog_s3_r5c1: "ITBIS sobre Materiales de Construcción",
  blog_s3_r6c1: "Aranceles de Importacion",
  blog_s3_r6c2: "Variable",
  blog_s3_example_title: "Ejemplo de Ahorro en una Propiedad de $315,000",
  blog_s3_ex1: "Impuesto de transferencia ahorrado: ~$9,450 (3% del precio)",
  blog_s3_ex2: "Impuesto anual a la propiedad ahorrado: ~$1,500-$3,000/año",
  blog_s3_ex3: "Ganancia de capital ahorrada (con 30% de apreciación): ~$25,000+",
  blog_s3_ex4: "Ahorro potencial total en 15 años: $50,000-$80,000+",
  blog_s3_p3: "No todas las propiedades califican para CONFOTUR. El proyecto debe estar certificado por el Ministerio de Turismo (MITUR). Siempre verifica que una propiedad tenga certificación CONFOTUR antes de comprar — solicita el número de resolución CONFOTUR.",
  blog_s3_warn_title: "Notas Importantes",
  blog_s3_warn1: "Las exenciones CONFOTUR aplican solo en la República Dominicana. Tu país de origen puede aún gravar los ingresos por propiedad en el extranjero y las ganancias de capital (EE.UU., Canadá, Francia, etc.).",
  blog_s3_warn2: "El reloj de 15 años comienza en la fecha de tu compra, no en la fecha en que el proyecto fue certificado.",
  blog_s3_warn3: "Los beneficios de CONFOTUR se transfieren al nuevo comprador si vendes antes de que expiren los 15 años.",

  // Section 4: Buying Process
  blog_s4_title: "4. El Proceso de Compra Paso a Paso",
  blog_s4_step1: "Paso 1: Encuentra tu Propiedad",
  blog_s4_step1_p: "Explora nuestros listados o dinos lo que estás buscando. Podemos organizar tours virtuales (recorrido por videollamada) o visitas presenciales.",
  blog_s4_step2: "Paso 2: Haz una Oferta y Firma la Promesa de Venta",
  blog_s4_step2_p: "Una vez que encuentres tu propiedad, firmas un \"Contrato de Promesa de Venta\" y pagas un depósito de reserva, típicamente el 10% del precio. Esto retira la propiedad del mercado.",
  blog_s4_step3: "Paso 3: Debida Diligencia",
  blog_s4_step3_p: "Tu abogado verifica el título en el Registro de Títulos, revisa gravámenes, confirma el estatus CONFOTUR y revisa todos los documentos. Esto toma de 2 a 4 semanas.",
  blog_s4_step4: "Paso 4: Cierre ante el Notario",
  blog_s4_step4_p: "Ambas partes firman la escritura final (Acto de Venta) ante un notario dominicano. Pagas el saldo restante. Si tienes CONFOTUR, el 3% del impuesto de transferencia se exonera. El notario se encarga del registro.",
  blog_s4_step5: "Paso 5: Registro del Título",
  blog_s4_step5_p: "El nuevo título se registra en el Registro de Títulos a tu nombre. Este proceso toma de 30 a 90 días. Una vez completado, recibes tu Certificado de Título — ahora eres el propietario legal.",
  blog_s4_timeline_title: "Tiempo Estimado",
  blog_s4_tl1: "De la reserva al cierre: 30-60 días",
  blog_s4_tl2: "Registro del título: 30-90 días después del cierre",
  blog_s4_tl3: "Total desde la primera visita hasta las llaves: 2-4 meses",

  // Section 5: Costs
  blog_s5_title: "5. Impuestos y Costos de Cierre",
  blog_s5_th1: "Costo",
  blog_s5_th2: "Sin CONFOTUR",
  blog_s5_th3: "Con CONFOTUR",
  blog_s5_r1: "Impuesto de Transferencia",
  blog_s5_r2: "Honorarios Legales (abogado)",
  blog_s5_r3: "Honorarios Notariales",
  blog_s5_r4: "Registro del Título",
  blog_s5_r5: "TOTAL (en propiedad de $315,000)",
  blog_s5_ongoing: "Costos Recurrentes",
  blog_s5_og1: "Cuotas de HOA / Condominio: $150-$400/mes (varía según el complejo)",
  blog_s5_og2: "Electricidad: $80-$200/mes (el aire acondicionado es el costo principal)",
  blog_s5_og3: "Agua: $15-$30/mes",
  blog_s5_og4: "Internet (fibra): $40-$60/mes",
  blog_s5_og5: "Seguro de propiedad: $500-$1,200/año",
  blog_s5_og6: "Administración de propiedad (si alquilas): 15-25% del ingreso por alquiler",

  // Section 6: Rental Income
  blog_s6_title: "6. Ingresos por Alquiler y Airbnb",
  blog_s6_p1: "Punta Cana es uno de los mercados de Airbnb más fuertes del Caribe. Con más de 7 millones de turistas al año, hay una fuerte demanda de alquileres vacacionales a corto plazo durante todo el año.",
  blog_s6_box_title: "Números Típicos de Alquiler (2 habitaciones en Bávaro/Cocotal)",
  blog_s6_box1: "Tarifa por noche: $80-$180 dependiendo de la temporada y amenidades",
  blog_s6_box2: "Ocupación: 65-80% anual",
  blog_s6_box3: "Ingreso bruto anual: $25,000-$45,000",
  blog_s6_box4: "Después de comisiones de administración (20%): $20,000-$36,000",
  blog_s6_box5: "ROI neto en una propiedad de $315,000: 6-11%",
  blog_s6_p2: "La temporada alta va de diciembre a abril (invierno norteamericano). Los meses de verano (junio-septiembre) tienen menor ocupación, pero los turistas europeos ayudan a llenar el vacío. Las propiedades con acceso a piscina, vistas al golf o proximidad a la playa obtienen tarifas premium.",
  blog_s6_p3: "La mayoría de los propietarios contratan una empresa local de administración de propiedades para manejar reservas, limpieza, mantenimiento y comunicación con los huéspedes. Las comisiones típicas son 15-25% del ingreso por alquiler. Es completamente libre de preocupaciones — no necesitas estar en el país.",

  // Section 7: Residency
  blog_s7_title: "7. Residencia a través de Propiedad",
  blog_s7_p1: "Ser propietario de un inmueble en la República Dominicana no otorga residencia automáticamente, pero simplifica significativamente el proceso. Los propietarios pueden solicitar una \"Residencia por Inversión\".",
  blog_s7_h1: "Tipos de Residencia",
  blog_s7_r1: "<strong>Residencia Temporal</strong> — Válida por 1 año, renovable. Disponible para propietarios. Requiere prueba de propiedad + ingresos ($1,500/mes mínimo).",
  blog_s7_r2: "<strong>Residencia Permanente</strong> — Disponible después de tener residencia temporal. Permite estadía indefinida.",
  blog_s7_r3: "<strong>Naturalización</strong> — La ciudadanía dominicana es posible después de 2+ años de residencia permanente (requiere dominio del español).",
  blog_s7_box_title: "¿Por qué Obtener Residencia?",
  blog_s7_box1: "Abrir cuentas bancarias dominicanas",
  blog_s7_box2: "Acceder a financiamiento local para futuras compras",
  blog_s7_box3: "Registro de vehículos y servicios públicos más fácil",
  blog_s7_box4: "Camino al pasaporte dominicano (viaje sin visa a 60+ países)",
  blog_s7_box5: "Sin requisito de estadía mínima — conservas tu ciudadanía original",

  // Section 8: FAQ
  blog_s8_title: "8. Preguntas Frecuentes",
  blog_faq1_q: "¿Es seguro comprar propiedad en la República Dominicana?",
  blog_faq1_a: "Sí. La República Dominicana tiene un sistema de registro de propiedad bien establecido. Los títulos se registran ante el gobierno y brindan protección legal. La clave es trabajar con un abogado calificado que realice la debida diligencia (búsqueda de título, verificación de gravámenes, verificación CONFOTUR). Punta Cana específicamente es una de las zonas más seguras del país, con comunidades cerradas, seguridad 24/7 y una fuerza policial turística dedicada (CESTUR).",
  blog_faq2_q: "¿Puedo obtener financiamiento / hipoteca?",
  blog_faq2_a: "Algunos bancos dominicanos ofrecen hipotecas a extranjeros, pero los términos suelen ser menos favorables que las hipotecas de EE.UU./Canadá (tasas de interés más altas, plazos más cortos, 30-50% de enganche requerido). La mayoría de los compradores extranjeros compran en efectivo o usan financiamiento de su país de origen (línea de crédito hipotecaria, préstamo personal, etc.). Muchos desarrolladores también ofrecen planes de pago directos durante la construcción (ej. 30% de enganche, 70% en 12-24 meses).",
  blog_faq3_q: "¿Necesito visitar en persona para comprar?",
  blog_faq3_a: "No. Todo el proceso se puede hacer de forma remota usando un poder notarial (Poder Notarial). Tu abogado puede firmar en tu nombre en el cierre. Podemos organizar tours virtuales por videollamada. Dicho esto, siempre recomendamos visitar al menos una vez antes de comprar para ver la propiedad y la zona en persona.",
  blog_faq4_q: "¿En qué moneda se cotizan las propiedades?",
  blog_faq4_a: "Los bienes inmuebles en la República Dominicana se cotizan y se negocian en dólares estadounidenses (USD). Esto es estándar en todo el mercado. No hay riesgo cambiario para los compradores estadounidenses. Los compradores canadienses, europeos y de otros países deben considerar el tipo de cambio al presupuestar.",
  blog_faq5_q: "¿Qué pasa si quiero vender después?",
  blog_faq5_a: "Puedes vender libremente en cualquier momento. Si tu propiedad tiene CONFOTUR, las exenciones fiscales se transfieren al nuevo comprador por el resto del período de 15 años — esto hace tu propiedad más atractiva para los compradores. Con CONFOTUR, pagas 0% de impuesto sobre ganancias de capital en la venta. Sin CONFOTUR, las ganancias de capital tributan al 27%.",
  blog_faq6_q: "¿Hay servicios de salud en Punta Cana?",
  blog_faq6_a: "Sí. Punta Cana tiene varios hospitales y clínicas modernas incluyendo Hospiten Bávaro (estándar internacional, personal bilingüe español/inglés), HOMS y Centro Médico Punta Cana. El seguro médico privado es accesible ($80-$200/mes). Para visitantes y snowbirds, se recomienda un seguro médico de viaje de tu país de origen.",
  blog_faq7_q: "¿Qué tan lejos está el aeropuerto?",
  blog_faq7_a: "El Aeropuerto Internacional de Punta Cana (PUJ) es el aeropuerto más concurrido del Caribe. Desde Cocotal/Bávaro, el aeropuerto está a aproximadamente 20-25 minutos en auto. Hay vuelos directos disponibles desde Nueva York (3.5h), Miami (3h), Montreal (4.5h), Toronto (4.5h), Madrid (8h) y muchas otras ciudades.",
  blog_faq8_q: "¿Necesito hablar español?",
  blog_faq8_a: "No necesariamente. Punta Cana es muy internacional — el inglés se habla ampliamente en zonas turísticas, hoteles, restaurantes y por la mayoría de los profesionales inmobiliarios. Sin embargo, un español básico es útil para la vida diaria. Los documentos legales están en español pero tu abogado te explicará todo.",

  // CTA
  blog_cta_title: "¿Listo para Explorar tus Opciones?",
  blog_cta_subtitle: "Estoy aquí para responder tus preguntas y ayudarte a encontrar la propiedad ideal en Punta Cana.",
  whatsapp_msg: "Escribe por WhatsApp",

  // Footer
  footer: "Punta Cana, República Dominicana"
};

const BLOG_FR = {
  // Nav (shared keys)
  nav_properties: "Propriétés",
  blog_nav: "Guide",
  nav_contact: "Nous joindre",

  // Hero
  blog_title: "Guide pour acheter une propriété à Punta Cana",
  blog_subtitle: "Tout ce que tu dois savoir : lois, taxes, processus et réponses aux questions les plus fréquentes.",

  // Table of Contents
  blog_toc: "Table des matières",
  blog_toc_1: "Pourquoi Punta Cana?",
  blog_toc_2: "Les étrangers peuvent-ils acheter?",
  blog_toc_3: "La loi CONFOTUR expliquée",
  blog_toc_4: "Le processus d'achat étape par étape",
  blog_toc_5: "Taxes et frais de clôture",
  blog_toc_6: "Revenus locatifs et Airbnb",
  blog_toc_7: "Résidence par investissement immobilier",
  blog_toc_8: "Questions fréquentes",

  // Section 1: Why Punta Cana
  blog_s1_title: "1. Pourquoi Punta Cana?",
  blog_s1_p1: "Punta Cana est la destination la plus visitée des Caraïbes, accueillant plus de 7 millions de touristes par année. Située à la pointe est de la République dominicaine, elle offre plus de 100 kilomètres de plages de sable blanc, des terrains de golf de calibre mondial et un marché immobilier en pleine croissance.",
  blog_s1_p2: "La région a connu des investissements massifs en infrastructure ces dernières années : nouvelles autoroutes, hôpitaux internationaux (Hospiten, HOMS), internet fibre optique et un aéroport en expansion (PUJ) avec des vols directs depuis plus de 80 villes dans le monde, incluant New York, Miami, Montréal, Madrid et Moscou.",
  blog_s1_box_title: "Chiffres clés",
  blog_s1_box_1: "7+ millions de touristes par année",
  blog_s1_box_2: "Vols directs depuis 80+ villes (USA, Canada, Europe, Amérique latine)",
  blog_s1_box_3: "Température moyenne : 27°C / 80°F à l'année",
  blog_s1_box_4: "Appréciation immobilière : 5-10% par année",
  blog_s1_box_5: "Taux d'occupation Airbnb : 65-80% dans les zones touristiques",
  blog_s1_box_6: "Coût de la vie : 50-70% moins cher que les grandes villes américaines",
  blog_s1_p3: "Les secteurs populaires incluent Bávaro (la zone touristique principale), Cap Cana (luxe), Cocotal (communauté de golf avec accès à l'Hôtel Meliá) et Punta Cana Village (près de l'aéroport). Chaque secteur a son propre caractère et ses prix, allant de condos à $100,000 jusqu'à des villas de plusieurs millions.",

  // Section 2: Foreign Ownership
  blog_s2_title: "2. Les étrangers peuvent-ils acheter une propriété?",
  blog_s2_p1: "Oui. La République dominicaine permet la propriété étrangère à 100% sans aucune restriction. Tu n'as pas besoin d'être résident, d'avoir un conjoint dominicain ou de créer une entreprise locale. Un étranger a exactement les mêmes droits de propriété qu'un citoyen dominicain.",
  blog_s2_p2: "Les propriétés sont enregistrées au Registro de Títulos (Registre des titres) et tu reçois un Certificat de titre (Certificado de Título) à ton nom. C'est un document appuyé par le gouvernement qui prouve ta propriété.",
  blog_s2_box_title: "Documents requis",
  blog_s2_box_1: "Passeport valide",
  blog_s2_box_2: "Preuve de fonds (relevé bancaire)",
  blog_s2_box_3: "C'est tout. Pas de visa, pas de résidence, pas d'entreprise locale requise.",
  blog_s2_p3: "On recommande fortement d'engager un avocat immobilier dominicain pour faire la vérification diligente avant d'acheter. Il va vérifier le titre, checker s'il y a des hypothèques ou charges, et s'assurer que la propriété est bien enregistrée. Les frais juridiques sont typiquement de 1-1.5% du prix d'achat.",

  // Section 3: CONFOTUR
  blog_s3_title: "3. La loi CONFOTUR expliquée",
  blog_s3_p1: "CONFOTUR (Ley 158-01) est l'incitatif le plus puissant de la République dominicaine pour les investisseurs immobiliers. Elle a été conçue pour promouvoir le développement touristique en accordant de généreuses exemptions fiscales aux projets admissibles.",
  blog_s3_p2: "Si une propriété a la certification CONFOTUR, l'acheteur reçoit les exemptions suivantes pour 15 ans à partir de la date d'achat :",
  blog_s3_th1: "Taxe",
  blog_s3_th2: "Taux normal",
  blog_s3_th3: "Avec CONFOTUR",
  blog_s3_r1c1: "Taxe de transfert (unique à la clôture)",
  blog_s3_r2c1: "Taxe foncière annuelle (IPI)",
  blog_s3_r2note: "(sur la valeur au-dessus de ~$7.7M DOP)",
  blog_s3_r3c1: "Impôt sur le gain en capital (à la vente)",
  blog_s3_r4c1: "Impôt sur les revenus locatifs",
  blog_s3_r5c1: "ITBIS sur les matériaux de construction",
  blog_s3_r6c1: "Droits d'importation",
  blog_s3_r6c2: "Variable",
  blog_s3_example_title: "Exemple d'économies sur une propriété de $315,000",
  blog_s3_ex1: "Taxe de transfert économisée : ~$9,450 (3% du prix)",
  blog_s3_ex2: "Taxe foncière annuelle économisée : ~$1,500-$3,000/an",
  blog_s3_ex3: "Gain en capital économisé (sur 30% d'appréciation) : ~$25,000+",
  blog_s3_ex4: "Économies potentielles totales sur 15 ans : $50,000-$80,000+",
  blog_s3_p3: "Toutes les propriétés ne sont pas admissibles à CONFOTUR. Le projet doit être certifié par le ministère du tourisme (MITUR). Vérifie toujours qu'une propriété a la certification CONFOTUR avant d'acheter — demande le numéro de résolution CONFOTUR.",
  blog_s3_warn_title: "Notes importantes",
  blog_s3_warn1: "Les exemptions CONFOTUR s'appliquent en République dominicaine seulement. Ton pays d'origine peut quand même imposer les revenus de propriété à l'étranger et les gains en capital (USA, Canada, France, etc.). Au Québec, pense à consulter ton comptable pour les implications fiscales.",
  blog_s3_warn2: "Le compteur de 15 ans commence à la date de ton achat, pas à la date de certification du projet.",
  blog_s3_warn3: "Les avantages CONFOTUR se transfèrent au nouvel acheteur si tu vends avant la fin des 15 ans.",

  // Section 4: Buying Process
  blog_s4_title: "4. Le processus d'achat étape par étape",
  blog_s4_step1: "Étape 1 : Trouve ta propriété",
  blog_s4_step1_p: "Explore nos listings ou dis-nous ce que tu cherches. On peut organiser des visites virtuelles (tour par appel vidéo) ou des visites en personne.",
  blog_s4_step2: "Étape 2 : Fais une offre et signe la promesse de vente",
  blog_s4_step2_p: "Une fois que tu as trouvé ta propriété, tu signes un \"Contrato de Promesa de Venta\" (Promesse de vente) et tu verses un dépôt de réservation, typiquement 10% du prix. Ça retire la propriété du marché.",
  blog_s4_step3: "Étape 3 : Vérification diligente",
  blog_s4_step3_p: "Ton avocat vérifie le titre au Registro de Títulos, checke les hypothèques, confirme le statut CONFOTUR et révise tous les documents. Ça prend 2 à 4 semaines.",
  blog_s4_step4: "Étape 4 : Clôture chez le notaire",
  blog_s4_step4_p: "Les deux parties signent l'acte de vente final (Acto de Venta) chez un notaire dominicain. Tu paies le solde restant. Si tu as CONFOTUR, la taxe de transfert de 3% est exonérée. Le notaire s'occupe de l'enregistrement.",
  blog_s4_step5: "Étape 5 : Enregistrement du titre",
  blog_s4_step5_p: "Le nouveau titre est enregistré au Registro de Títulos à ton nom. Ce processus prend 30 à 90 jours. Une fois complété, tu reçois ton Certificat de titre — tu es maintenant le propriétaire légal.",
  blog_s4_timeline_title: "Délais typiques",
  blog_s4_tl1: "De la réservation à la clôture : 30-60 jours",
  blog_s4_tl2: "Enregistrement du titre : 30-90 jours après la clôture",
  blog_s4_tl3: "Total de la première visite aux clés : 2-4 mois",

  // Section 5: Costs
  blog_s5_title: "5. Taxes et frais de clôture",
  blog_s5_th1: "Coût",
  blog_s5_th2: "Sans CONFOTUR",
  blog_s5_th3: "Avec CONFOTUR",
  blog_s5_r1: "Taxe de transfert",
  blog_s5_r2: "Frais juridiques (avocat)",
  blog_s5_r3: "Frais de notaire",
  blog_s5_r4: "Enregistrement du titre",
  blog_s5_r5: "TOTAL (sur une propriété de $315,000)",
  blog_s5_ongoing: "Coûts récurrents",
  blog_s5_og1: "Frais de condo / copropriété : $150-$400/mois (varie selon le complexe)",
  blog_s5_og2: "Électricité : $80-$200/mois (la climatisation est le coût principal)",
  blog_s5_og3: "Eau : $15-$30/mois",
  blog_s5_og4: "Internet (fibre) : $40-$60/mois",
  blog_s5_og5: "Assurance propriété : $500-$1,200/an",
  blog_s5_og6: "Gestion de propriété (si tu loues) : 15-25% des revenus locatifs",

  // Section 6: Rental Income
  blog_s6_title: "6. Revenus locatifs et Airbnb",
  blog_s6_p1: "Punta Cana est l'un des meilleurs marchés Airbnb des Caraïbes. Avec 7+ millions de touristes par année, la demande pour les locations vacances à court terme est forte à l'année longue.",
  blog_s6_box_title: "Chiffres typiques de location (2 chambres à Bávaro/Cocotal)",
  blog_s6_box1: "Tarif par nuit : $80-$180 selon la saison et les aménités",
  blog_s6_box2: "Taux d'occupation : 65-80% annuellement",
  blog_s6_box3: "Revenu brut annuel : $25,000-$45,000",
  blog_s6_box4: "Après frais de gestion (20%) : $20,000-$36,000",
  blog_s6_box5: "Rendement net sur une propriété de $315,000 : 6-11%",
  blog_s6_p2: "La haute saison va de décembre à avril (l'hiver nord-américain — parfait pour les snowbirds du Québec!). Les mois d'été (juin-septembre) ont un taux d'occupation plus bas, mais les touristes européens aident à combler l'écart. Les propriétés avec accès piscine, vue sur le golf ou proximité de la plage obtiennent des tarifs premium.",
  blog_s6_p3: "La plupart des propriétaires engagent une compagnie locale de gestion de propriétés pour s'occuper des réservations, du ménage, de l'entretien et de la communication avec les invités. Les frais typiques sont de 15-25% des revenus locatifs. C'est complètement clé en main — tu n'as pas besoin d'être sur place.",

  // Section 7: Residency
  blog_s7_title: "7. Résidence par investissement immobilier",
  blog_s7_p1: "Être propriétaire en République dominicaine ne donne pas automatiquement la résidence, mais ça simplifie beaucoup le processus. Les propriétaires peuvent faire une demande de \"Residencia por Inversión\" (Résidence par investissement).",
  blog_s7_h1: "Types de résidence",
  blog_s7_r1: "<strong>Résidence temporaire</strong> — Valide 1 an, renouvelable. Disponible pour les propriétaires. Requiert une preuve de propriété + revenus ($1,500/mois minimum).",
  blog_s7_r2: "<strong>Résidence permanente</strong> — Disponible après avoir détenu la résidence temporaire. Permet un séjour indéfini.",
  blog_s7_r3: "<strong>Naturalisation</strong> — La citoyenneté dominicaine est possible après 2+ ans de résidence permanente (la connaissance de l'espagnol est requise).",
  blog_s7_box_title: "Pourquoi obtenir la résidence?",
  blog_s7_box1: "Ouvrir des comptes bancaires dominicains",
  blog_s7_box2: "Accéder au financement local pour de futurs achats",
  blog_s7_box3: "Immatriculation de véhicule et services publics plus faciles",
  blog_s7_box4: "Chemin vers le passeport dominicain (voyage sans visa dans 60+ pays)",
  blog_s7_box5: "Aucune exigence de séjour minimum — tu gardes ta citoyenneté canadienne (ou autre)",

  // Section 8: FAQ
  blog_s8_title: "8. Questions fréquentes",
  blog_faq1_q: "Est-ce sécuritaire d'acheter en République dominicaine?",
  blog_faq1_a: "Oui. La République dominicaine a un système d'enregistrement de propriété bien établi. Les titres sont enregistrés auprès du gouvernement et offrent une protection légale. La clé, c'est de travailler avec un avocat qualifié qui fait une vérification diligente complète (recherche de titre, vérification d'hypothèques, vérification CONFOTUR). Punta Cana spécifiquement est l'un des secteurs les plus sécuritaires du pays, avec des communautés fermées, de la sécurité 24/7 et une force policière touristique dédiée.",
  blog_faq2_q: "Est-ce que je peux obtenir du financement / une hypothèque?",
  blog_faq2_a: "Certaines banques dominicaines offrent des hypothèques aux étrangers, mais les conditions sont typiquement moins avantageuses que les hypothèques canadiennes ou américaines (taux d'intérêt plus élevés, termes plus courts, mise de fonds de 30-50% requise). La plupart des acheteurs étrangers achètent comptant ou utilisent du financement de leur pays d'origine (marge de crédit hypothécaire, prêt personnel, etc.). Plusieurs développeurs offrent aussi des plans de paiement directs pendant la construction (ex. 30% de mise de fonds, 70% sur 12-24 mois).",
  blog_faq3_q: "Faut-il se déplacer en personne pour acheter?",
  blog_faq3_a: "Non. Tout le processus peut se faire à distance avec une procuration (Poder Notarial). Ton avocat peut signer à ta place à la clôture. On peut organiser des visites virtuelles par appel vidéo. Cela dit, on recommande toujours de visiter au moins une fois avant d'acheter pour voir la propriété et le secteur en personne.",
  blog_faq4_q: "En quelle devise les propriétés sont-elles affichées?",
  blog_faq4_a: "L'immobilier en République dominicaine est affiché et transigé en dollars américains (USD). C'est la norme dans tout le marché. Il n'y a pas de risque de change pour les acheteurs américains. Les acheteurs canadiens, européens et internationaux devraient considérer le taux de change dans leur budget. Pour les Québécois, c'est important de calculer en CAD.",
  blog_faq5_q: "Qu'est-ce qui arrive si je veux revendre plus tard?",
  blog_faq5_a: "Tu peux vendre librement à tout moment. Si ta propriété a CONFOTUR, les exemptions fiscales se transfèrent au nouvel acheteur pour le reste de la période de 15 ans — ça rend ta propriété plus attrayante. Avec CONFOTUR, tu paies 0% d'impôt sur le gain en capital à la vente. Sans CONFOTUR, le gain en capital est imposé à 27%.",
  blog_faq6_q: "Y a-t-il des soins de sante a Punta Cana?",
  blog_faq6_a: "Oui. Punta Cana a plusieurs hôpitaux et cliniques modernes incluant Hospiten Bávaro (standard international, personnel bilingue espagnol/anglais), HOMS et Centro Médico Punta Cana. L'assurance santé privée est abordable ($80-$200/mois). Pour les visiteurs et les snowbirds, une assurance voyage de ton pays est recommandée — la RAMQ ne couvre pas grand-chose à l'étranger.",
  blog_faq7_q: "C'est loin de l'aéroport?",
  blog_faq7_a: "L'Aéroport international de Punta Cana (PUJ) est le plus achalandé des Caraïbes. Depuis Cocotal/Bávaro, l'aéroport est à environ 20-25 minutes en char. Des vols directs sont disponibles depuis New York (3.5h), Miami (3h), Montréal (4.5h), Toronto (4.5h), Madrid (8h) et plusieurs autres villes.",
  blog_faq8_q: "Faut-il parler espagnol?",
  blog_faq8_a: "Pas nécessairement. Punta Cana est très internationale — l'anglais est largement parlé dans les zones touristiques, les hôtels, les restos et par la plupart des professionnels de l'immobilier. Par contre, un espagnol de base est utile pour la vie quotidienne. Les documents légaux sont en espagnol, mais ton avocat va tout t'expliquer.",

  // CTA
  blog_cta_title: "Prêt à explorer tes options?",
  blog_cta_subtitle: "Je suis là pour répondre à tes questions et t'aider à trouver la bonne propriété à Punta Cana.",
  whatsapp_msg: "Écris-nous sur WhatsApp",

  // Footer
  footer: "Punta Cana, République dominicaine"
};
const BLOG_RU = {
  // Navigation
  nav_properties: "Недвижимость",
  blog_nav: "Гид",
  nav_contact: "Контакты",

  // Hero
  blog_title: "Руководство по покупке недвижимости в Пунта-Кане",
  blog_subtitle: "Все, что нужно знать: законы, налоги, процесс покупки и ответы на самые частые вопросы.",

  // Table of Contents
  blog_toc: "Содержание",
  blog_toc_1: "Почему Пунта-Кана?",
  blog_toc_2: "Могут ли иностранцы покупать недвижимость?",
  blog_toc_3: "Закон CONFOTUR: подробный разбор",
  blog_toc_4: "Процесс покупки: пошаговая инструкция",
  blog_toc_5: "Налоги и расходы при закрытии сделки",
  blog_toc_6: "Доход от аренды и Airbnb",
  blog_toc_7: "Вид на жительство через покупку недвижимости",
  blog_toc_8: "Часто задаваемые вопросы",

  // Section 1: Why Punta Cana
  blog_s1_title: "1. Почему Пунта-Кана?",
  blog_s1_p1: "Пунта-Кана — самое посещаемое направление на Карибах, принимающее более 7 миллионов туристов ежегодно. Расположенная на восточной оконечности Доминиканской Республики, она предлагает более 100 километров белоснежных пляжей, гольф-поля мирового уровня и быстрорастущий рынок недвижимости.",
  blog_s1_p2: "В последние годы в регионе проведены масштабные инфраструктурные инвестиции: новые автомагистрали, международные больницы (Hospiten, HOMS), оптоволоконный интернет и расширяющийся аэропорт (PUJ) с прямыми рейсами из более чем 80 городов мира, включая Нью-Йорк, Майами, Монреаль, Мадрид и Москву.",

  blog_s1_box_title: "Ключевые цифры",
  blog_s1_box_1: "7+ миллионов туристов в год",
  blog_s1_box_2: "Прямые рейсы из 80+ городов (США, Канада, Европа, Латинская Америка)",
  blog_s1_box_3: "Средняя температура: 27°C / 80°F круглый год",
  blog_s1_box_4: "Рост стоимости недвижимости: 5-10% ежегодно",
  blog_s1_box_5: "Загрузка на Airbnb: 65-80% в туристических зонах",
  blog_s1_box_6: "Стоимость жизни: на 50-70% ниже, чем в крупных городах США",

  blog_s1_p3: "Популярные районы: Баваро (основная туристическая зона), Кап-Кана (премиум-класс), Кокоталь (гольф-комьюнити с доступом к отелю Melia) и Пунта-Кана Виллидж (рядом с аэропортом). Каждый район имеет свой характер и ценовой диапазон — от студий за $100 000 до вилл стоимостью в несколько миллионов долларов.",

  // Section 2: Foreign Ownership
  blog_s2_title: "2. Могут ли иностранцы покупать недвижимость?",
  blog_s2_p1: "Да. Доминиканская Республика разрешает иностранцам 100% владение недвижимостью без каких-либо ограничений. Вам не нужно быть резидентом, иметь доминиканского партнера или создавать местную компанию. Иностранец обладает точно такими же правами на собственность, как и гражданин Доминиканской Республики.",
  blog_s2_p2: "Объекты недвижимости регистрируются в Registro de Títulos (Реестре титулов), и вы получаете Certificado de Título (Свидетельство о праве собственности) на ваше имя. Это государственный документ, подтверждающий ваше право владения.",

  blog_s2_box_title: "Необходимые документы",
  blog_s2_box_1: "Действующий загранпаспорт",
  blog_s2_box_2: "Подтверждение наличия средств (выписка из банка)",
  blog_s2_box_3: "Это все. Виза, вид на жительство и местная компания не требуются.",

  blog_s2_p3: "Мы настоятельно рекомендуем нанять доминиканского адвоката по недвижимости для проведения юридической проверки перед покупкой. Он проверит титул, наличие обременений и залогов, а также убедится в правильной регистрации объекта. Стоимость юридических услуг обычно составляет 1-1,5% от цены покупки.",

  // Section 3: CONFOTUR
  blog_s3_title: "3. Закон CONFOTUR: подробный разбор",
  blog_s3_p1: "CONFOTUR (Закон 158-01) — наиболее мощный инструмент стимулирования инвесторов в недвижимость Доминиканской Республики. Он был разработан для развития туризма и предоставляет значительные налоговые льготы квалифицированным проектам.",
  blog_s3_p2: "Если объект недвижимости имеет сертификацию CONFOTUR, покупатель получает следующие освобождения от налогов сроком на 15 лет с даты покупки:",

  blog_s3_th1: "Налог",
  blog_s3_th2: "Обычная ставка",
  blog_s3_th3: "С CONFOTUR",

  blog_s3_r1c1: "Налог на передачу права собственности (единовременно при закрытии сделки)",
  blog_s3_r2c1: "Ежегодный налог на недвижимость (IPI)",
  blog_s3_r2note: "(на стоимость свыше ~7,7 млн DOP)",
  blog_s3_r3c1: "Налог на прирост капитала (при продаже)",
  blog_s3_r4c1: "Налог на доход от аренды",
  blog_s3_r5c1: "ITBIS на строительные материалы",
  blog_s3_r6c1: "Импортные пошлины",
  blog_s3_r6c2: "Различается",

  blog_s3_example_title: "Пример экономии на объекте стоимостью $315 000",
  blog_s3_ex1: "Экономия на налоге на передачу: ~$9 450 (3% от стоимости)",
  blog_s3_ex2: "Экономия на ежегодном налоге на недвижимость: ~$1 500-$3 000/год",
  blog_s3_ex3: "Экономия на налоге на прирост капитала (при росте 30%): ~$25 000+",
  blog_s3_ex4: "Общая потенциальная экономия за 15 лет: $50 000-$80 000+",

  blog_s3_p3: "Не все объекты подпадают под действие CONFOTUR. Проект должен быть сертифицирован Министерством туризма (MITUR). Всегда уточняйте наличие сертификации CONFOTUR перед покупкой — запросите номер резолюции CONFOTUR.",

  blog_s3_warn_title: "Важные замечания",
  blog_s3_warn1: "Льготы CONFOTUR действуют только в Доминиканской Республике. Ваша страна проживания может по-прежнему облагать налогом доход от зарубежной собственности и прирост капитала (США, Канада, Франция и т.д.).",
  blog_s3_warn2: "15-летний срок начинается с даты вашей покупки, а не с даты сертификации проекта.",
  blog_s3_warn3: "Льготы CONFOTUR переходят к новому покупателю, если вы продаете объект до истечения 15-летнего срока.",

  // Section 4: Buying Process
  blog_s4_title: "4. Процесс покупки: пошаговая инструкция",

  blog_s4_step1: "Шаг 1: Найдите объект недвижимости",
  blog_s4_step1_p: "Просмотрите наши предложения или сообщите нам, что вы ищете. Мы можем организовать виртуальный просмотр (по видеосвязи) или личный визит.",

  blog_s4_step2: "Шаг 2: Сделайте предложение и подпишите предварительный договор",
  blog_s4_step2_p: "Когда вы нашли подходящий объект, подписывается «Contrato de Promesa de Venta» (Предварительный договор купли-продажи), и вносится резервационный залог, обычно 10% от стоимости. Это снимает объект с продажи.",

  blog_s4_step3: "Шаг 3: Юридическая проверка (Due Diligence)",
  blog_s4_step3_p: "Ваш адвокат проверяет титул в Registro de Títulos, наличие обременений, подтверждает статус CONFOTUR и проверяет все документы. Это занимает 2-4 недели.",

  blog_s4_step4: "Шаг 4: Закрытие сделки у нотариуса",
  blog_s4_step4_p: "Обе стороны подписывают окончательный акт купли-продажи (Acto de Venta) у доминиканского нотариуса. Вы оплачиваете остаток суммы. При наличии CONFOTUR 3% налог на передачу права не взимается. Нотариус оформляет регистрацию.",

  blog_s4_step5: "Шаг 5: Регистрация права собственности",
  blog_s4_step5_p: "Новый титул регистрируется в Registro de Títulos на ваше имя. Процесс занимает 30-90 дней. По завершении вы получаете Свидетельство о праве собственности — вы становитесь законным владельцем.",

  blog_s4_timeline_title: "Типичные сроки",
  blog_s4_tl1: "От бронирования до закрытия сделки: 30-60 дней",
  blog_s4_tl2: "Регистрация права собственности: 30-90 дней после закрытия",
  blog_s4_tl3: "Общий срок от первого просмотра до получения ключей: 2-4 месяца",

  // Section 5: Costs
  blog_s5_title: "5. Налоги и расходы при закрытии сделки",

  blog_s5_th1: "Расходы",
  blog_s5_th2: "Без CONFOTUR",
  blog_s5_th3: "С CONFOTUR",

  blog_s5_r1: "Налог на передачу права собственности",
  blog_s5_r2: "Юридические услуги (адвокат)",
  blog_s5_r3: "Нотариальные услуги",
  blog_s5_r4: "Регистрация права собственности",
  blog_s5_r5: "ИТОГО (для объекта стоимостью $315 000)",

  blog_s5_ongoing: "Текущие расходы",
  blog_s5_og1: "Обслуживание / взносы в кондоминиум: $150-$400/мес. (зависит от комплекса)",
  blog_s5_og2: "Электричество: $80-$200/мес. (основной расход — кондиционер)",
  blog_s5_og3: "Вода: $15-$30/мес.",
  blog_s5_og4: "Интернет (оптоволокно): $40-$60/мес.",
  blog_s5_og5: "Страхование недвижимости: $500-$1 200/год",
  blog_s5_og6: "Управление недвижимостью (при сдаче в аренду): 15-25% от дохода",

  // Section 6: Rental Income
  blog_s6_title: "6. Доход от аренды и Airbnb",
  blog_s6_p1: "Пунта-Кана — один из ведущих рынков Airbnb на Карибах. С более чем 7 миллионами туристов ежегодно здесь существует стабильный спрос на краткосрочную аренду круглый год.",

  blog_s6_box_title: "Типичные показатели аренды (2-комнатная квартира в Баваро/Кокоталь)",
  blog_s6_box1: "Стоимость за ночь: $80-$180 в зависимости от сезона и удобств",
  blog_s6_box2: "Загрузка: 65-80% в годовом исчислении",
  blog_s6_box3: "Валовой годовой доход: $25 000-$45 000",
  blog_s6_box4: "После вычета комиссии за управление (20%): $20 000-$36 000",
  blog_s6_box5: "Чистая доходность для объекта стоимостью $315 000: 6-11%",

  blog_s6_p2: "Высокий сезон длится с декабря по апрель (зима в Северной Америке). Летние месяцы (июнь-сентябрь) отличаются более низкой загрузкой, но европейские туристы помогают компенсировать разницу. Объекты с бассейном, видом на гольф-поле или близостью к пляжу приносят повышенный доход.",
  blog_s6_p3: "Большинство собственников нанимают местную управляющую компанию для работы с бронированиями, уборкой, обслуживанием и коммуникацией с гостями. Типичная комиссия составляет 15-25% от дохода от аренды. Это полностью пассивный доход — вам не нужно находиться в стране.",

  // Section 7: Residency
  blog_s7_title: "7. Вид на жительство через покупку недвижимости",
  blog_s7_p1: "Владение недвижимостью в Доминиканской Республике не дает автоматического права на проживание, но значительно упрощает процесс. Владельцы недвижимости могут подать заявку на «Residencia por Inversión» (Вид на жительство на основании инвестиций).",

  blog_s7_h1: "Типы вида на жительство",
  blog_s7_r1: "<strong>Временный вид на жительство</strong> — Действует 1 год, с возможностью продления. Доступен владельцам недвижимости. Требуется подтверждение собственности + доход (минимум $1 500/мес.).",
  blog_s7_r2: "<strong>Постоянный вид на жительство</strong> — Доступен после временного вида на жительство. Позволяет проживать без ограничения срока.",
  blog_s7_r3: "<strong>Натурализация</strong> — Получение гражданства Доминиканской Республики возможно через 2+ года постоянного проживания (требуется знание испанского языка).",

  blog_s7_box_title: "Преимущества вида на жительство",
  blog_s7_box1: "Открытие банковских счетов в Доминиканской Республике",
  blog_s7_box2: "Доступ к местному финансированию для будущих покупок",
  blog_s7_box3: "Упрощенная регистрация автомобиля и подключение коммунальных услуг",
  blog_s7_box4: "Путь к доминиканскому паспорту (безвизовый въезд в 60+ стран)",
  blog_s7_box5: "Нет требований по минимальному сроку проживания — вы сохраняете свое исходное гражданство",

  // Section 8: FAQ
  blog_s8_title: "8. Часто задаваемые вопросы",

  blog_faq1_q: "Безопасно ли покупать недвижимость в Доминиканской Республике?",
  blog_faq1_a: "Да. В Доминиканской Республике действует надежная система регистрации собственности. Титулы регистрируются государством и обеспечивают правовую защиту. Главное — работать с квалифицированным адвокатом, который проведет надлежащую юридическую проверку (поиск по титулу, проверка обременений, верификация CONFOTUR). Пунта-Кана — один из самых безопасных районов страны с закрытыми жилыми комплексами, круглосуточной охраной и специальной туристической полицией.",

  blog_faq2_q: "Можно ли получить ипотеку?",
  blog_faq2_a: "Некоторые доминиканские банки предоставляют ипотеку иностранцам, но условия, как правило, менее выгодны, чем в США или Канаде (более высокие процентные ставки, более короткие сроки, первоначальный взнос 30-50%). Большинство иностранных покупателей приобретают за наличные или используют финансирование из своей страны (кредитная линия под залог жилья, потребительский кредит и т.д.). Многие застройщики также предлагают прямые рассрочки на этапе строительства (например, 30% первоначальный взнос, 70% в течение 12-24 месяцев).",

  blog_faq3_q: "Нужно ли приезжать лично для покупки?",
  blog_faq3_a: "Нет. Весь процесс можно провести дистанционно по доверенности (Poder Notarial). Ваш адвокат может подписать документы от вашего имени при закрытии сделки. Мы можем организовать виртуальные просмотры по видеосвязи. Тем не менее, мы всегда рекомендуем хотя бы один раз посетить объект и район лично перед покупкой.",

  blog_faq4_q: "В какой валюте указаны цены на недвижимость?",
  blog_faq4_a: "Недвижимость в Доминиканской Республике оценивается и продается в долларах США (USD). Это стандарт для всего рынка. Для американских покупателей валютный риск отсутствует. Покупателям из Канады, Европы и других стран следует учитывать обменный курс при планировании бюджета.",

  blog_faq5_q: "Что будет, если я захочу продать объект позднее?",
  blog_faq5_a: "Вы можете свободно продать объект в любое время. Если ваша недвижимость имеет CONFOTUR, налоговые льготы переходят новому покупателю на оставшийся срок из 15 лет — это делает ваш объект более привлекательным для покупателей. С CONFOTUR вы платите 0% налога на прирост капитала при продаже. Без CONFOTUR налог на прирост капитала составляет 27%.",

  blog_faq6_q: "Есть ли медицина в Пунта-Кане?",
  blog_faq6_a: "Да. В Пунта-Кане есть несколько современных больниц и клиник, включая Hospiten Bavaro (международный стандарт, англо- и испаноговорящий персонал), HOMS и Centro Médico Punta Cana. Частная медицинская страховка доступна по цене ($80-$200/мес.). Для гостей и «зимовщиков» рекомендуется туристическая медицинская страховка из вашей страны.",

  blog_faq7_q: "Как далеко находится аэропорт?",
  blog_faq7_a: "Международный аэропорт Пунта-Каны (PUJ) — самый загруженный аэропорт на Карибах. От Кокоталь/Баваро до аэропорта примерно 20-25 минут на автомобиле. Прямые рейсы доступны из Нью-Йорка (3,5 ч.), Майами (3 ч.), Монреаля (4,5 ч.), Торонто (4,5 ч.), Мадрида (8 ч.) и многих других городов.",

  blog_faq8_q: "Нужно ли знать испанский язык?",
  blog_faq8_a: "Не обязательно. Пунта-Кана — очень международный регион: в туристических зонах, отелях, ресторанах и среди большинства специалистов по недвижимости широко распространен английский язык. Тем не менее, базовые знания испанского полезны в повседневной жизни. Юридические документы составляются на испанском, но ваш адвокат все объяснит.",

  // CTA
  blog_cta_title: "Готовы рассмотреть варианты?",
  blog_cta_subtitle: "Я готов ответить на ваши вопросы и помочь найти подходящую недвижимость в Пунта-Кане.",
  whatsapp_msg: "Написать в WhatsApp",

  // Footer
  footer: "Пунта-Кана, Доминиканская Республика"
};

    // Merge into global TRANSLATIONS
    if (typeof TRANSLATIONS !== 'undefined') {
        if (TRANSLATIONS.es) Object.assign(TRANSLATIONS.es, BLOG_ES);
        if (TRANSLATIONS.fr) Object.assign(TRANSLATIONS.fr, BLOG_FR);
        if (TRANSLATIONS.ru) Object.assign(TRANSLATIONS.ru, BLOG_RU);
    }
})();
