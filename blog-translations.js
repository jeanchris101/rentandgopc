(function() {
const BLOG_ES = {
  // Nav (shared keys)
  nav_properties: "Propiedades",
  blog_nav: "Guia",
  nav_contact: "Contacto",

  // Hero
  blog_title: "Guia para Comprar Propiedad en Punta Cana",
  blog_subtitle: "Todo lo que necesitas saber: leyes, impuestos, proceso y respuestas a las preguntas mas frecuentes.",

  // Table of Contents
  blog_toc: "Tabla de Contenido",
  blog_toc_1: "Por que Punta Cana?",
  blog_toc_2: "Pueden los Extranjeros Comprar?",
  blog_toc_3: "Ley CONFOTUR Explicada",
  blog_toc_4: "El Proceso de Compra Paso a Paso",
  blog_toc_5: "Impuestos y Costos de Cierre",
  blog_toc_6: "Ingresos por Alquiler y Airbnb",
  blog_toc_7: "Residencia a traves de Propiedad",
  blog_toc_8: "Preguntas Frecuentes",

  // Section 1: Why Punta Cana
  blog_s1_title: "1. Por que Punta Cana?",
  blog_s1_p1: "Punta Cana es el destino mas visitado del Caribe, recibiendo mas de 7 millones de turistas al ano. Ubicada en el extremo este de la Republica Dominicana, ofrece mas de 100 kilometros de playas de arena blanca, campos de golf de clase mundial y un mercado inmobiliario en rapido crecimiento.",
  blog_s1_p2: "La region ha visto una inversion masiva en infraestructura en los ultimos anos: nuevas autopistas, hospitales internacionales (Hospiten, HOMS), internet de fibra optica y un aeropuerto en expansion (PUJ) con vuelos directos desde mas de 80 ciudades en todo el mundo, incluyendo Nueva York, Miami, Montreal, Madrid y Moscu.",
  blog_s1_box_title: "Cifras Clave",
  blog_s1_box_1: "7+ millones de turistas al ano",
  blog_s1_box_2: "Vuelos directos desde 80+ ciudades (EE.UU., Canada, Europa, LatAm)",
  blog_s1_box_3: "Temperatura promedio: 27°C / 80°F todo el ano",
  blog_s1_box_4: "Apreciacion inmobiliaria: 5-10% anual",
  blog_s1_box_5: "Tasa de ocupacion en Airbnb: 65-80% en zonas turisticas",
  blog_s1_box_6: "Costo de vida: 50-70% mas bajo que las principales ciudades de EE.UU.",
  blog_s1_p3: "Las zonas mas populares incluyen Bavaro (la franja turistica principal), Cap Cana (lujo), Cocotal (comunidad de golf con acceso al Hotel Melia) y Punta Cana Village (cerca del aeropuerto). Cada zona tiene su propio caracter y rango de precios, desde estudios de $100,000 hasta villas de varios millones de dolares.",

  // Section 2: Foreign Ownership
  blog_s2_title: "2. Pueden los Extranjeros Comprar Propiedad?",
  blog_s2_p1: "Si. La Republica Dominicana permite la propiedad 100% extranjera de bienes inmuebles sin restricciones. No necesitas ser residente, tener una pareja dominicana ni constituir una empresa local. Un extranjero tiene exactamente los mismos derechos de propiedad que un ciudadano dominicano.",
  blog_s2_p2: "Las propiedades se registran en el Registro de Titulos y recibes un Certificado de Titulo a tu nombre. Este es un documento respaldado por el gobierno que demuestra tu propiedad.",
  blog_s2_box_title: "Documentos que Necesitas",
  blog_s2_box_1: "Pasaporte vigente",
  blog_s2_box_2: "Prueba de fondos (estado de cuenta bancario)",
  blog_s2_box_3: "Eso es todo. No se necesita visa, residencia ni empresa local.",
  blog_s2_p3: "Recomendamos fuertemente contratar un abogado inmobiliario dominicano para realizar la debida diligencia antes de comprar. El abogado verificara el titulo, revisara si existen gravamenes o cargas, y se asegurara de que la propiedad este debidamente registrada. Los honorarios legales tipicamente oscilan entre 1-1.5% del precio de compra.",

  // Section 3: CONFOTUR
  blog_s3_title: "3. Ley CONFOTUR Explicada",
  blog_s3_p1: "CONFOTUR (Ley 158-01) es el incentivo mas poderoso de la Republica Dominicana para inversionistas inmobiliarios. Fue disenada para promover el desarrollo turistico otorgando generosas exenciones fiscales a proyectos que califiquen.",
  blog_s3_p2: "Si una propiedad tiene certificacion CONFOTUR, el comprador recibe las siguientes exenciones por 15 anos a partir de la fecha de compra:",
  blog_s3_th1: "Impuesto",
  blog_s3_th2: "Tasa Normal",
  blog_s3_th3: "Con CONFOTUR",
  blog_s3_r1c1: "Impuesto de Transferencia (unico al cierre)",
  blog_s3_r2c1: "Impuesto Anual a la Propiedad (IPI)",
  blog_s3_r2note: "(sobre el valor superior a ~$7.7M DOP)",
  blog_s3_r3c1: "Impuesto sobre Ganancias de Capital (al vender)",
  blog_s3_r4c1: "Impuesto sobre Ingresos por Alquiler",
  blog_s3_r5c1: "ITBIS sobre Materiales de Construccion",
  blog_s3_r6c1: "Aranceles de Importacion",
  blog_s3_r6c2: "Variable",
  blog_s3_example_title: "Ejemplo de Ahorro en una Propiedad de $315,000",
  blog_s3_ex1: "Impuesto de transferencia ahorrado: ~$9,450 (3% del precio)",
  blog_s3_ex2: "Impuesto anual a la propiedad ahorrado: ~$1,500-$3,000/ano",
  blog_s3_ex3: "Ganancia de capital ahorrada (con 30% de apreciacion): ~$25,000+",
  blog_s3_ex4: "Ahorro potencial total en 15 anos: $50,000-$80,000+",
  blog_s3_p3: "No todas las propiedades califican para CONFOTUR. El proyecto debe estar certificado por el Ministerio de Turismo (MITUR). Siempre verifica que una propiedad tenga certificacion CONFOTUR antes de comprar — solicita el numero de resolucion CONFOTUR.",
  blog_s3_warn_title: "Notas Importantes",
  blog_s3_warn1: "Las exenciones CONFOTUR aplican solo en la Republica Dominicana. Tu pais de origen puede aun gravar los ingresos por propiedad en el extranjero y las ganancias de capital (EE.UU., Canada, Francia, etc.).",
  blog_s3_warn2: "El reloj de 15 anos comienza en la fecha de tu compra, no en la fecha en que el proyecto fue certificado.",
  blog_s3_warn3: "Los beneficios de CONFOTUR se transfieren al nuevo comprador si vendes antes de que expiren los 15 anos.",

  // Section 4: Buying Process
  blog_s4_title: "4. El Proceso de Compra Paso a Paso",
  blog_s4_step1: "Paso 1: Encuentra tu Propiedad",
  blog_s4_step1_p: "Explora nuestros listados o dinos lo que estas buscando. Podemos organizar tours virtuales (recorrido por videollamada) o visitas presenciales.",
  blog_s4_step2: "Paso 2: Haz una Oferta y Firma la Promesa de Venta",
  blog_s4_step2_p: "Una vez que encuentres tu propiedad, firmas un \"Contrato de Promesa de Venta\" y pagas un deposito de reserva, tipicamente el 10% del precio. Esto retira la propiedad del mercado.",
  blog_s4_step3: "Paso 3: Debida Diligencia",
  blog_s4_step3_p: "Tu abogado verifica el titulo en el Registro de Titulos, revisa gravamenes, confirma el estatus CONFOTUR y revisa todos los documentos. Esto toma de 2 a 4 semanas.",
  blog_s4_step4: "Paso 4: Cierre ante el Notario",
  blog_s4_step4_p: "Ambas partes firman la escritura final (Acto de Venta) ante un notario dominicano. Pagas el saldo restante. Si tienes CONFOTUR, el 3% del impuesto de transferencia se exonera. El notario se encarga del registro.",
  blog_s4_step5: "Paso 5: Registro del Titulo",
  blog_s4_step5_p: "El nuevo titulo se registra en el Registro de Titulos a tu nombre. Este proceso toma de 30 a 90 dias. Una vez completado, recibes tu Certificado de Titulo — ahora eres el propietario legal.",
  blog_s4_timeline_title: "Tiempo Estimado",
  blog_s4_tl1: "De la reserva al cierre: 30-60 dias",
  blog_s4_tl2: "Registro del titulo: 30-90 dias despues del cierre",
  blog_s4_tl3: "Total desde la primera visita hasta las llaves: 2-4 meses",

  // Section 5: Costs
  blog_s5_title: "5. Impuestos y Costos de Cierre",
  blog_s5_th1: "Costo",
  blog_s5_th2: "Sin CONFOTUR",
  blog_s5_th3: "Con CONFOTUR",
  blog_s5_r1: "Impuesto de Transferencia",
  blog_s5_r2: "Honorarios Legales (abogado)",
  blog_s5_r3: "Honorarios Notariales",
  blog_s5_r4: "Registro del Titulo",
  blog_s5_r5: "TOTAL (en propiedad de $315,000)",
  blog_s5_ongoing: "Costos Recurrentes",
  blog_s5_og1: "Cuotas de HOA / Condominio: $150-$400/mes (varia segun el complejo)",
  blog_s5_og2: "Electricidad: $80-$200/mes (el aire acondicionado es el costo principal)",
  blog_s5_og3: "Agua: $15-$30/mes",
  blog_s5_og4: "Internet (fibra): $40-$60/mes",
  blog_s5_og5: "Seguro de propiedad: $500-$1,200/ano",
  blog_s5_og6: "Administracion de propiedad (si alquilas): 15-25% del ingreso por alquiler",

  // Section 6: Rental Income
  blog_s6_title: "6. Ingresos por Alquiler y Airbnb",
  blog_s6_p1: "Punta Cana es uno de los mercados de Airbnb mas fuertes del Caribe. Con mas de 7 millones de turistas al ano, hay una fuerte demanda de alquileres vacacionales a corto plazo durante todo el ano.",
  blog_s6_box_title: "Numeros Tipicos de Alquiler (2 habitaciones en Bavaro/Cocotal)",
  blog_s6_box1: "Tarifa por noche: $80-$180 dependiendo de la temporada y amenidades",
  blog_s6_box2: "Ocupacion: 65-80% anual",
  blog_s6_box3: "Ingreso bruto anual: $25,000-$45,000",
  blog_s6_box4: "Despues de comisiones de administracion (20%): $20,000-$36,000",
  blog_s6_box5: "ROI neto en una propiedad de $315,000: 6-11%",
  blog_s6_p2: "La temporada alta va de diciembre a abril (invierno norteamericano). Los meses de verano (junio-septiembre) tienen menor ocupacion, pero los turistas europeos ayudan a llenar el vacio. Las propiedades con acceso a piscina, vistas al golf o proximidad a la playa obtienen tarifas premium.",
  blog_s6_p3: "La mayoria de los propietarios contratan una empresa local de administracion de propiedades para manejar reservas, limpieza, mantenimiento y comunicacion con los huespedes. Las comisiones tipicas son 15-25% del ingreso por alquiler. Es completamente libre de preocupaciones — no necesitas estar en el pais.",

  // Section 7: Residency
  blog_s7_title: "7. Residencia a traves de Propiedad",
  blog_s7_p1: "Ser propietario de un inmueble en la Republica Dominicana no otorga residencia automaticamente, pero simplifica significativamente el proceso. Los propietarios pueden solicitar una \"Residencia por Inversion\".",
  blog_s7_h1: "Tipos de Residencia",
  blog_s7_r1: "<strong>Residencia Temporal</strong> — Valida por 1 ano, renovable. Disponible para propietarios. Requiere prueba de propiedad + ingresos ($1,500/mes minimo).",
  blog_s7_r2: "<strong>Residencia Permanente</strong> — Disponible despues de tener residencia temporal. Permite estadía indefinida.",
  blog_s7_r3: "<strong>Naturalizacion</strong> — La ciudadania dominicana es posible despues de 2+ anos de residencia permanente (requiere dominio del espanol).",
  blog_s7_box_title: "Por que Obtener Residencia?",
  blog_s7_box1: "Abrir cuentas bancarias dominicanas",
  blog_s7_box2: "Acceder a financiamiento local para futuras compras",
  blog_s7_box3: "Registro de vehiculos y servicios publicos mas facil",
  blog_s7_box4: "Camino al pasaporte dominicano (viaje sin visa a 60+ paises)",
  blog_s7_box5: "Sin requisito de estadia minima — conservas tu ciudadania original",

  // Section 8: FAQ
  blog_s8_title: "8. Preguntas Frecuentes",
  blog_faq1_q: "Es seguro comprar propiedad en la Republica Dominicana?",
  blog_faq1_a: "Si. La Republica Dominicana tiene un sistema de registro de propiedad bien establecido. Los titulos se registran ante el gobierno y brindan proteccion legal. La clave es trabajar con un abogado calificado que realice la debida diligencia (busqueda de titulo, verificacion de gravamenes, verificacion CONFOTUR). Punta Cana especificamente es una de las zonas mas seguras del pais, con comunidades cerradas, seguridad 24/7 y una fuerza policial turistica dedicada (CESTUR).",
  blog_faq2_q: "Puedo obtener financiamiento / hipoteca?",
  blog_faq2_a: "Algunos bancos dominicanos ofrecen hipotecas a extranjeros, pero los terminos suelen ser menos favorables que las hipotecas de EE.UU./Canada (tasas de interes mas altas, plazos mas cortos, 30-50% de enganche requerido). La mayoria de los compradores extranjeros compran en efectivo o usan financiamiento de su pais de origen (linea de credito hipotecaria, prestamo personal, etc.). Muchos desarrolladores tambien ofrecen planes de pago directos durante la construccion (ej. 30% de enganche, 70% en 12-24 meses).",
  blog_faq3_q: "Necesito visitar en persona para comprar?",
  blog_faq3_a: "No. Todo el proceso se puede hacer de forma remota usando un poder notarial (Poder Notarial). Tu abogado puede firmar en tu nombre en el cierre. Podemos organizar tours virtuales por videollamada. Dicho esto, siempre recomendamos visitar al menos una vez antes de comprar para ver la propiedad y la zona en persona.",
  blog_faq4_q: "En que moneda se cotizan las propiedades?",
  blog_faq4_a: "Los bienes inmuebles en la Republica Dominicana se cotizan y se negocian en dolares estadounidenses (USD). Esto es estandar en todo el mercado. No hay riesgo cambiario para los compradores estadounidenses. Los compradores canadienses, europeos y de otros paises deben considerar el tipo de cambio al presupuestar.",
  blog_faq5_q: "Que pasa si quiero vender despues?",
  blog_faq5_a: "Puedes vender libremente en cualquier momento. Si tu propiedad tiene CONFOTUR, las exenciones fiscales se transfieren al nuevo comprador por el resto del periodo de 15 anos — esto hace tu propiedad mas atractiva para los compradores. Con CONFOTUR, pagas 0% de impuesto sobre ganancias de capital en la venta. Sin CONFOTUR, las ganancias de capital tributan al 27%.",
  blog_faq6_q: "Hay servicios de salud en Punta Cana?",
  blog_faq6_a: "Si. Punta Cana tiene varios hospitales y clinicas modernas incluyendo Hospiten Bavaro (estandar internacional, personal bilingue espanol/ingles), HOMS y Centro Medico Punta Cana. El seguro medico privado es accesible ($80-$200/mes). Para visitantes y snowbirds, se recomienda un seguro medico de viaje de tu pais de origen.",
  blog_faq7_q: "Que tan lejos esta el aeropuerto?",
  blog_faq7_a: "El Aeropuerto Internacional de Punta Cana (PUJ) es el aeropuerto mas concurrido del Caribe. Desde Cocotal/Bavaro, el aeropuerto esta a aproximadamente 20-25 minutos en auto. Hay vuelos directos disponibles desde Nueva York (3.5h), Miami (3h), Montreal (4.5h), Toronto (4.5h), Madrid (8h) y muchas otras ciudades.",
  blog_faq8_q: "Necesito hablar espanol?",
  blog_faq8_a: "No necesariamente. Punta Cana es muy internacional — el ingles se habla ampliamente en zonas turisticas, hoteles, restaurantes y por la mayoria de los profesionales inmobiliarios. Sin embargo, un espanol basico es util para la vida diaria. Los documentos legales estan en espanol pero tu abogado te explicara todo.",

  // CTA
  blog_cta_title: "Listo para Explorar tus Opciones?",
  blog_cta_subtitle: "Estoy aqui para responder tus preguntas y ayudarte a encontrar la propiedad ideal en Punta Cana.",
  whatsapp_msg: "Escribe por WhatsApp",

  // Footer
  footer: "Punta Cana, Republica Dominicana"
};

const BLOG_FR = {
  // Nav (shared keys)
  nav_properties: "Proprietes",
  blog_nav: "Guide",
  nav_contact: "Contact",

  // Hero
  blog_title: "Guide pour acheter une propriete a Punta Cana",
  blog_subtitle: "Tout ce que tu dois savoir : lois, taxes, processus et reponses aux questions les plus frequentes.",

  // Table of Contents
  blog_toc: "Table des matieres",
  blog_toc_1: "Pourquoi Punta Cana?",
  blog_toc_2: "Les etrangers peuvent-ils acheter?",
  blog_toc_3: "La loi CONFOTUR expliquee",
  blog_toc_4: "Le processus d'achat etape par etape",
  blog_toc_5: "Taxes et frais de cloture",
  blog_toc_6: "Revenus locatifs et Airbnb",
  blog_toc_7: "Residence par investissement immobilier",
  blog_toc_8: "Questions frequentes",

  // Section 1: Why Punta Cana
  blog_s1_title: "1. Pourquoi Punta Cana?",
  blog_s1_p1: "Punta Cana est la destination la plus visitee des Caraibes, accueillant plus de 7 millions de touristes par annee. Situee a la pointe est de la Republique dominicaine, elle offre plus de 100 kilometres de plages de sable blanc, des terrains de golf de calibre mondial et un marche immobilier en pleine croissance.",
  blog_s1_p2: "La region a connu des investissements massifs en infrastructure ces dernieres annees : nouvelles autoroutes, hopitaux internationaux (Hospiten, HOMS), internet fibre optique et un aeroport en expansion (PUJ) avec des vols directs depuis plus de 80 villes dans le monde, incluant New York, Miami, Montreal, Madrid et Moscou.",
  blog_s1_box_title: "Chiffres cles",
  blog_s1_box_1: "7+ millions de touristes par annee",
  blog_s1_box_2: "Vols directs depuis 80+ villes (USA, Canada, Europe, Amerique latine)",
  blog_s1_box_3: "Temperature moyenne : 27°C / 80°F a l'annee",
  blog_s1_box_4: "Appreciation immobiliere : 5-10% par annee",
  blog_s1_box_5: "Taux d'occupation Airbnb : 65-80% dans les zones touristiques",
  blog_s1_box_6: "Cout de la vie : 50-70% moins cher que les grandes villes americaines",
  blog_s1_p3: "Les secteurs populaires incluent Bavaro (la zone touristique principale), Cap Cana (luxe), Cocotal (communaute de golf avec acces a l'Hotel Melia) et Punta Cana Village (pres de l'aeroport). Chaque secteur a son propre caractere et ses prix, allant de condos a $100,000 jusqu'a des villas de plusieurs millions.",

  // Section 2: Foreign Ownership
  blog_s2_title: "2. Les etrangers peuvent-ils acheter une propriete?",
  blog_s2_p1: "Oui. La Republique dominicaine permet la propriete etrangere a 100% sans aucune restriction. Tu n'as pas besoin d'etre resident, d'avoir un conjoint dominicain ou de creer une entreprise locale. Un etranger a exactement les memes droits de propriete qu'un citoyen dominicain.",
  blog_s2_p2: "Les proprietes sont enregistrees au Registro de Titulos (Registre des titres) et tu recois un Certificat de titre (Certificado de Titulo) a ton nom. C'est un document appuye par le gouvernement qui prouve ta propriete.",
  blog_s2_box_title: "Documents requis",
  blog_s2_box_1: "Passeport valide",
  blog_s2_box_2: "Preuve de fonds (releve bancaire)",
  blog_s2_box_3: "C'est tout. Pas de visa, pas de residence, pas d'entreprise locale requise.",
  blog_s2_p3: "On recommande fortement d'engager un avocat immobilier dominicain pour faire la verification diligente avant d'acheter. Il va verifier le titre, checker s'il y a des hypotheques ou charges, et s'assurer que la propriete est bien enregistree. Les frais juridiques sont typiquement de 1-1.5% du prix d'achat.",

  // Section 3: CONFOTUR
  blog_s3_title: "3. La loi CONFOTUR expliquee",
  blog_s3_p1: "CONFOTUR (Ley 158-01) est l'incitatif le plus puissant de la Republique dominicaine pour les investisseurs immobiliers. Elle a ete concue pour promouvoir le developpement touristique en accordant de genereuses exemptions fiscales aux projets admissibles.",
  blog_s3_p2: "Si une propriete a la certification CONFOTUR, l'acheteur recoit les exemptions suivantes pour 15 ans a partir de la date d'achat :",
  blog_s3_th1: "Taxe",
  blog_s3_th2: "Taux normal",
  blog_s3_th3: "Avec CONFOTUR",
  blog_s3_r1c1: "Taxe de transfert (unique a la cloture)",
  blog_s3_r2c1: "Taxe fonciere annuelle (IPI)",
  blog_s3_r2note: "(sur la valeur au-dessus de ~$7.7M DOP)",
  blog_s3_r3c1: "Impot sur le gain en capital (a la vente)",
  blog_s3_r4c1: "Impot sur les revenus locatifs",
  blog_s3_r5c1: "ITBIS sur les materiaux de construction",
  blog_s3_r6c1: "Droits d'importation",
  blog_s3_r6c2: "Variable",
  blog_s3_example_title: "Exemple d'economies sur une propriete de $315,000",
  blog_s3_ex1: "Taxe de transfert economisee : ~$9,450 (3% du prix)",
  blog_s3_ex2: "Taxe fonciere annuelle economisee : ~$1,500-$3,000/an",
  blog_s3_ex3: "Gain en capital economise (sur 30% d'appreciation) : ~$25,000+",
  blog_s3_ex4: "Economies potentielles totales sur 15 ans : $50,000-$80,000+",
  blog_s3_p3: "Toutes les proprietes ne sont pas admissibles a CONFOTUR. Le projet doit etre certifie par le ministere du tourisme (MITUR). Verifie toujours qu'une propriete a la certification CONFOTUR avant d'acheter — demande le numero de resolution CONFOTUR.",
  blog_s3_warn_title: "Notes importantes",
  blog_s3_warn1: "Les exemptions CONFOTUR s'appliquent en Republique dominicaine seulement. Ton pays d'origine peut quand meme imposer les revenus de propriete a l'etranger et les gains en capital (USA, Canada, France, etc.). Au Quebec, pense a consulter ton comptable pour les implications fiscales.",
  blog_s3_warn2: "Le compteur de 15 ans commence a la date de ton achat, pas a la date de certification du projet.",
  blog_s3_warn3: "Les avantages CONFOTUR se transferent au nouvel acheteur si tu vends avant la fin des 15 ans.",

  // Section 4: Buying Process
  blog_s4_title: "4. Le processus d'achat etape par etape",
  blog_s4_step1: "Etape 1 : Trouve ta propriete",
  blog_s4_step1_p: "Explore nos listings ou dis-nous ce que tu cherches. On peut organiser des visites virtuelles (tour par appel video) ou des visites en personne.",
  blog_s4_step2: "Etape 2 : Fais une offre et signe la promesse de vente",
  blog_s4_step2_p: "Une fois que tu as trouve ta propriete, tu signes un \"Contrato de Promesa de Venta\" (Promesse de vente) et tu verses un depot de reservation, typiquement 10% du prix. Ca retire la propriete du marche.",
  blog_s4_step3: "Etape 3 : Verification diligente",
  blog_s4_step3_p: "Ton avocat verifie le titre au Registro de Titulos, checke les hypotheques, confirme le statut CONFOTUR et revise tous les documents. Ca prend 2 a 4 semaines.",
  blog_s4_step4: "Etape 4 : Cloture chez le notaire",
  blog_s4_step4_p: "Les deux parties signent l'acte de vente final (Acto de Venta) chez un notaire dominicain. Tu paies le solde restant. Si tu as CONFOTUR, la taxe de transfert de 3% est exoneree. Le notaire s'occupe de l'enregistrement.",
  blog_s4_step5: "Etape 5 : Enregistrement du titre",
  blog_s4_step5_p: "Le nouveau titre est enregistre au Registro de Titulos a ton nom. Ce processus prend 30 a 90 jours. Une fois complete, tu recois ton Certificat de titre — tu es maintenant le proprietaire legal.",
  blog_s4_timeline_title: "Delais typiques",
  blog_s4_tl1: "De la reservation a la cloture : 30-60 jours",
  blog_s4_tl2: "Enregistrement du titre : 30-90 jours apres la cloture",
  blog_s4_tl3: "Total de la premiere visite aux cles : 2-4 mois",

  // Section 5: Costs
  blog_s5_title: "5. Taxes et frais de cloture",
  blog_s5_th1: "Cout",
  blog_s5_th2: "Sans CONFOTUR",
  blog_s5_th3: "Avec CONFOTUR",
  blog_s5_r1: "Taxe de transfert",
  blog_s5_r2: "Frais juridiques (avocat)",
  blog_s5_r3: "Frais de notaire",
  blog_s5_r4: "Enregistrement du titre",
  blog_s5_r5: "TOTAL (sur une propriete de $315,000)",
  blog_s5_ongoing: "Couts recurrents",
  blog_s5_og1: "Frais de condo / copropriete : $150-$400/mois (varie selon le complexe)",
  blog_s5_og2: "Electricite : $80-$200/mois (la climatisation est le cout principal)",
  blog_s5_og3: "Eau : $15-$30/mois",
  blog_s5_og4: "Internet (fibre) : $40-$60/mois",
  blog_s5_og5: "Assurance propriete : $500-$1,200/an",
  blog_s5_og6: "Gestion de propriete (si tu loues) : 15-25% des revenus locatifs",

  // Section 6: Rental Income
  blog_s6_title: "6. Revenus locatifs et Airbnb",
  blog_s6_p1: "Punta Cana est l'un des meilleurs marches Airbnb des Caraibes. Avec 7+ millions de touristes par annee, la demande pour les locations vacances a court terme est forte a l'annee longue.",
  blog_s6_box_title: "Chiffres typiques de location (2 chambres a Bavaro/Cocotal)",
  blog_s6_box1: "Tarif par nuit : $80-$180 selon la saison et les amenites",
  blog_s6_box2: "Taux d'occupation : 65-80% annuellement",
  blog_s6_box3: "Revenu brut annuel : $25,000-$45,000",
  blog_s6_box4: "Apres frais de gestion (20%) : $20,000-$36,000",
  blog_s6_box5: "ROI net sur une propriete de $315,000 : 6-11%",
  blog_s6_p2: "La haute saison va de decembre a avril (l'hiver nord-americain — parfait pour les snowbirds du Quebec!). Les mois d'ete (juin-septembre) ont un taux d'occupation plus bas, mais les touristes europeens aident a combler l'ecart. Les proprietes avec acces piscine, vue sur le golf ou proximite de la plage obtiennent des tarifs premium.",
  blog_s6_p3: "La plupart des proprietaires engagent une compagnie locale de gestion de proprietes pour s'occuper des reservations, du menage, de l'entretien et de la communication avec les invites. Les frais typiques sont de 15-25% des revenus locatifs. C'est completement clé en main — tu n'as pas besoin d'etre sur place.",

  // Section 7: Residency
  blog_s7_title: "7. Residence par investissement immobilier",
  blog_s7_p1: "Etre proprietaire en Republique dominicaine ne donne pas automatiquement la residence, mais ca simplifie beaucoup le processus. Les proprietaires peuvent faire une demande de \"Residencia por Inversion\" (Residence par investissement).",
  blog_s7_h1: "Types de residence",
  blog_s7_r1: "<strong>Residence temporaire</strong> — Valide 1 an, renouvelable. Disponible pour les proprietaires. Requiert une preuve de propriete + revenus ($1,500/mois minimum).",
  blog_s7_r2: "<strong>Residence permanente</strong> — Disponible apres avoir detenu la residence temporaire. Permet un sejour indefini.",
  blog_s7_r3: "<strong>Naturalisation</strong> — La citoyennete dominicaine est possible apres 2+ ans de residence permanente (la connaissance de l'espagnol est requise).",
  blog_s7_box_title: "Pourquoi obtenir la residence?",
  blog_s7_box1: "Ouvrir des comptes bancaires dominicains",
  blog_s7_box2: "Acceder au financement local pour de futurs achats",
  blog_s7_box3: "Immatriculation de vehicule et services publics plus faciles",
  blog_s7_box4: "Chemin vers le passeport dominicain (voyage sans visa dans 60+ pays)",
  blog_s7_box5: "Aucune exigence de sejour minimum — tu gardes ta citoyennete canadienne (ou autre)",

  // Section 8: FAQ
  blog_s8_title: "8. Questions frequentes",
  blog_faq1_q: "Est-ce securitaire d'acheter en Republique dominicaine?",
  blog_faq1_a: "Oui. La Republique dominicaine a un systeme d'enregistrement de propriete bien etabli. Les titres sont enregistres aupres du gouvernement et offrent une protection legale. La cle, c'est de travailler avec un avocat qualifie qui fait une verification diligente complete (recherche de titre, verification d'hypotheques, verification CONFOTUR). Punta Cana specifiquement est l'un des secteurs les plus securitaires du pays, avec des communautes fermees, de la securite 24/7 et une force policiere touristique dediee.",
  blog_faq2_q: "Est-ce que je peux obtenir du financement / une hypotheque?",
  blog_faq2_a: "Certaines banques dominicaines offrent des hypotheques aux etrangers, mais les conditions sont typiquement moins avantageuses que les hypotheques canadiennes ou americaines (taux d'interet plus eleves, termes plus courts, mise de fonds de 30-50% requise). La plupart des acheteurs etrangers achetent comptant ou utilisent du financement de leur pays d'origine (marge de credit hypothecaire, pret personnel, etc.). Plusieurs developpeurs offrent aussi des plans de paiement directs pendant la construction (ex. 30% de mise de fonds, 70% sur 12-24 mois).",
  blog_faq3_q: "Faut-il se deplacer en personne pour acheter?",
  blog_faq3_a: "Non. Tout le processus peut se faire a distance avec une procuration (Poder Notarial). Ton avocat peut signer a ta place a la cloture. On peut organiser des visites virtuelles par appel video. Cela dit, on recommande toujours de visiter au moins une fois avant d'acheter pour voir la propriete et le secteur en personne.",
  blog_faq4_q: "En quelle devise les proprietes sont-elles affichees?",
  blog_faq4_a: "L'immobilier en Republique dominicaine est affiche et transige en dollars americains (USD). C'est la norme dans tout le marche. Il n'y a pas de risque de change pour les acheteurs americains. Les acheteurs canadiens, europeens et internationaux devraient considerer le taux de change dans leur budget. Pour les Quebecois, c'est important de calculer en CAD.",
  blog_faq5_q: "Qu'est-ce qui arrive si je veux revendre plus tard?",
  blog_faq5_a: "Tu peux vendre librement a tout moment. Si ta propriete a CONFOTUR, les exemptions fiscales se transferent au nouvel acheteur pour le reste de la periode de 15 ans — ca rend ta propriete plus attrayante. Avec CONFOTUR, tu paies 0% d'impot sur le gain en capital a la vente. Sans CONFOTUR, le gain en capital est impose a 27%.",
  blog_faq6_q: "Y a-t-il des soins de sante a Punta Cana?",
  blog_faq6_a: "Oui. Punta Cana a plusieurs hopitaux et cliniques modernes incluant Hospiten Bavaro (standard international, personnel bilingue espagnol/anglais), HOMS et Centro Medico Punta Cana. L'assurance sante privee est abordable ($80-$200/mois). Pour les visiteurs et les snowbirds, une assurance voyage de ton pays est recommandee — la RAMQ ne couvre pas grand-chose a l'etranger.",
  blog_faq7_q: "C'est loin de l'aeroport?",
  blog_faq7_a: "L'Aeroport international de Punta Cana (PUJ) est le plus achalande des Caraibes. Depuis Cocotal/Bavaro, l'aeroport est a environ 20-25 minutes en char. Des vols directs sont disponibles depuis New York (3.5h), Miami (3h), Montreal (4.5h), Toronto (4.5h), Madrid (8h) et plusieurs autres villes.",
  blog_faq8_q: "Faut-il parler espagnol?",
  blog_faq8_a: "Pas necessairement. Punta Cana est tres internationale — l'anglais est largement parle dans les zones touristiques, les hotels, les restos et par la plupart des professionnels de l'immobilier. Par contre, un espagnol de base est utile pour la vie quotidienne. Les documents legaux sont en espagnol, mais ton avocat va tout t'expliquer.",

  // CTA
  blog_cta_title: "Pret a explorer tes options?",
  blog_cta_subtitle: "Je suis la pour repondre a tes questions et t'aider a trouver la bonne propriete a Punta Cana.",
  whatsapp_msg: "Ecris-nous sur WhatsApp",

  // Footer
  footer: "Punta Cana, Republique dominicaine"
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
