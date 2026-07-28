# Panel de WhatsApp de Rent & Go Punta Cana — Guía de instalación

Esta guía es para ti, el dueño. No hace falta saber programar. Sigue los pasos
en orden y no te saltes ninguno. Cuando algo sea delicado, te lo aviso con
**ATENCIÓN**.

Antes de empezar, lee la **sección 6 (Riesgo)**. Es la más importante de todo
este documento. Si después de leerla no te sientes cómodo, no montes esto:
tienes una alternativa oficial que también te explico ahí.

---

## Índice

1. [Qué es esto](#1-qué-es-esto)
2. [Desplegar en Railway](#2-desplegar-en-railway)
3. [Vincular el teléfono](#3-vincular-el-teléfono)
4. [Variables que van en Vercel](#4-variables-que-van-en-vercel)
5. [Configurar el webhook](#5-configurar-el-webhook)
6. [Riesgo — léelo completo](#6-riesgo--léelo-completo)
7. [Qué hacer si algo falla](#7-qué-hacer-si-algo-falla)
8. [Cómo apagar todo rápido](#8-cómo-apagar-todo-rápido)

---

## 1. Qué es esto

**WAHA** es un programita que se queda prendido en un servidor y hace de
traductor entre WhatsApp y tu sitio web. Tu página le dice "manda este
mensaje" y WAHA lo manda; cuando alguien te escribe, WAHA le avisa a tu página.

Corre **aparte** del sitio web porque tu sitio vive en Vercel, y Vercel apaga
el código apenas termina de responder una visita. WhatsApp necesita lo
contrario: una conexión abierta las 24 horas, sin apagarse nunca. Por eso van
en dos lugares distintos.

En resumen: **Vercel** = el sitio y el panel que tú ves. **Railway** = la
maquinita que mantiene WhatsApp conectado.

---

## 2. Desplegar en Railway

Railway es un servicio donde alquilas un pedacito de servidor. Se paga con
tarjeta y se maneja desde el navegador.

### 2.1 Crear la cuenta y el proyecto

1. Entra a **https://railway.com** y crea tu cuenta (lo más fácil es entrar con
   tu cuenta de GitHub).
2. Suscríbete al plan **Hobby** ($5/mes). El plan gratis no sirve aquí porque no
   permite tener un servicio prendido todo el tiempo.
3. En el panel, dale a **New Project**.
4. Elige **Empty Project** y ponle un nombre, por ejemplo `waha-rentandgo`.

### 2.2 Desplegar la imagen de WhatsApp

1. Dentro del proyecto, dale al botón **+ New** (arriba a la derecha).
2. Elige **Docker Image**.
3. En la cajita que aparece, escribe exactamente:

   ```
   devlikeapro/waha:noweb
   ```

   Dale Enter. Railway va a descargar el programa y arrancarlo. Toma 1 o 2 minutos.

> **Nota técnica (por si alguien te pregunta):** `noweb` es la versión sin
> navegador. Consume la mitad de memoria que la versión normal, lo que en
> Railway significa la mitad del costo y menos reinicios inesperados.

### 2.3 Montar el disco — **EL PASO MÁS IMPORTANTE**

Sin este paso, cada vez que Railway reinicie el servicio (y lo hace solo, por
actualizaciones), **se pierde la conexión de WhatsApp y tienes que volver a
escanear el QR con el teléfono**. Con este paso, la conexión aguanta meses sin
que toques nada.

1. Haz **clic derecho** en el espacio vacío del proyecto (o presiona `Ctrl + K`).
2. Elige **Volume** (o "Add Volume").
3. Railway te va a preguntar a qué servicio conectarlo: elige el servicio de WAHA.
4. Te pide la **Mount Path** (ruta de montaje). Escribe **exactamente** esto,
   con el punto delante de `sessions`:

   ```
   /app/.sessions
   ```

   Si escribes otra cosa, o se te olvida el punto, no sirve de nada.

5. Deja el tamaño en 1 GB. Es de sobra.

### 2.4 Poner las variables

1. Haz clic en el servicio de WAHA y ve a la pestaña **Variables**.
2. Dale a **Raw Editor** (así las pegas todas de un golpe en vez de una por una).
3. Pega este bloque y **cambia los valores que dicen `PON_AQUI_...`**:

   ```
   WHATSAPP_API_HOSTNAME=0.0.0.0
   WHATSAPP_API_PORT=3000
   TZ=America/Santo_Domingo

   WAHA_API_KEY=PON_AQUI_TU_CLAVE_LARGA_1
   WAHA_API_KEY_EXCLUDE_PATH=health,ping

   WAHA_DASHBOARD_ENABLED=true
   WAHA_DASHBOARD_USERNAME=PON_AQUI_UN_USUARIO
   WAHA_DASHBOARD_PASSWORD=PON_AQUI_TU_CLAVE_LARGA_2
   WHATSAPP_SWAGGER_ENABLED=false

   WHATSAPP_DEFAULT_ENGINE=NOWEB
   WHATSAPP_START_SESSION=default
   WHATSAPP_RESTART_ALL_SESSIONS=True
   WAHA_AUTO_START_DELAY_SECONDS=5

   WHATSAPP_HOOK_URL=https://www.rentandgopc.com/api/wa/webhook
   WHATSAPP_HOOK_EVENTS=message
   WHATSAPP_HOOK_HMAC_KEY=PON_AQUI_TU_CLAVE_LARGA_3
   WHATSAPP_HOOK_RETRIES_POLICY=exponential
   WHATSAPP_HOOK_RETRIES_ATTEMPTS=3
   WHATSAPP_HOOK_RETRIES_DELAY_SECONDS=2

   WHATSAPP_FILES_FOLDER=/app/.media
   WHATSAPP_FILES_LIFETIME=180

   WAHA_LOG_LEVEL=info
   WAHA_LOG_FORMAT=JSON
   WAHA_PRINT_QR=True
   ```

4. **Cómo inventar las 3 claves largas.** Tienen que ser tres claves
   **distintas** entre sí, largas y sin sentido. La forma más fácil:
   entra a `https://www.random.org/strings/`, pide cadenas de 32 caracteres y
   pega tres diferentes. Nada de `rentandgo2026` ni tu fecha de nacimiento.

   - **CLAVE_LARGA_1** (`WAHA_API_KEY`): la llave de tu WhatsApp. Quien la
     tenga puede mandar mensajes en tu nombre. Guárdala como la clave del banco.
   - **CLAVE_LARGA_2** (`WAHA_DASHBOARD_PASSWORD`): para entrar al panel de WAHA.
   - **CLAVE_LARGA_3** (`WHATSAPP_HOOK_HMAC_KEY`): la firma de los mensajes que
     WAHA le manda a tu sitio.

5. **Anótalas en un lugar seguro** (un gestor de contraseñas, o escritas en
   papel guardado en tu casa). Las vas a necesitar en el paso 4.

### 2.5 Obtener el dominio público

1. En el mismo servicio, ve a **Settings** → sección **Networking**.
2. Dale a **Generate Domain**.
3. Te va a preguntar el puerto (**target port**): escribe **3000**.
4. Railway te devuelve una dirección tipo
   `https://waha-production-a1b2.up.railway.app`. **Cópiala y guárdala**, esa es
   tu `WAHA_URL`.
5. Vuelve a **Variables** y agrega una más, con esa dirección:

   ```
   WAHA_PUBLIC_URL=https://LA-DIRECCION-QUE-TE-DIO-RAILWAY
   ```

6. Railway va a reiniciar el servicio solo. Espera un minuto.

### 2.6 Cuánto cuesta y cómo ponerle tope

**Costo estimado (precios de Railway 2026):**

| Concepto | Cálculo | Al mes |
|---|---|---|
| Suscripción Hobby | fija | $5.00 |
| Procesador (0.1 vCPU) | $20 por vCPU/mes | $2.00 |
| Memoria (200 MB) | $10 por GB/mes | $2.00 |
| Disco de la sesión (1 GB) | $0.15 por GB/mes | $0.15 |
| Tráfico de salida | $0.05 por GB, poco volumen | ~$0.10 |
| **Uso total** | | **~$4.25** |

La suscripción Hobby de $5 **ya incluye $5 de uso**. Como el uso estimado es
~$4.25, en la práctica **pagas $5/mes y nada más**. Presupuesta **$8 al mes**
por si un mes hay más movimiento.

> Si en algún momento cambias al motor con navegador (`WEBJS`), el consumo sube
> a 0.3 vCPU y 400 MB, o sea unos **$10-12/mes**. Por eso usamos `NOWEB`.

**Ponerle tope de gasto (hazlo hoy mismo, no lo dejes para después):**

1. Entra a `https://railway.com/workspace/usage`.
2. Dale al botón **Set Usage Limits**.
3. Verás dos casillas:
   - **Email alert (aviso por correo):** ponle **$8**. Te avisa, no apaga nada.
   - **Hard limit (tope duro):** ponle **$10**. Es el mínimo que Railway permite.
     Cuando el gasto llegue ahí, Railway **apaga todo** para que no te siga
     cobrando. Te avisa al 75%, al 90% y al 100% antes de apagar.
4. Guarda.

**ATENCIÓN:** si el tope duro se dispara, WhatsApp se apaga y los clientes
dejan de recibir respuesta. Si te llega el correo de aviso del 75%, entra a
revisar qué está consumiendo de más antes de que llegue al 100%.

---

## 3. Vincular el teléfono

Aquí es donde conectas tu WhatsApp de verdad.

> **ATENCIÓN — léelo dos veces.** Este paso hay que hacerlo desde el teléfono
> cuyo número es **+1 809 486 5386**. Ese teléfono, con esa línea puesta, en la
> mano. No sirve el WhatsApp de otro teléfono, ni WhatsApp Web abierto en la
> computadora, ni el número de un empleado. Si vinculas el número equivocado,
> todos los mensajes van a salir desde ese otro número y hay que empezar de cero.

1. En el navegador, abre la dirección que te dio Railway y agrégale `/dashboard`
   al final:

   ```
   https://LA-DIRECCION-QUE-TE-DIO-RAILWAY/dashboard
   ```

2. Te va a pedir usuario y clave: son el `WAHA_DASHBOARD_USERNAME` y el
   `WAHA_DASHBOARD_PASSWORD` que pusiste en el paso 2.4.
3. Vas a ver una sesión llamada `default`. Si está en **STOPPED**, dale a
   **Start**. Espera unos segundos hasta que diga **SCAN_QR_CODE**.
4. Va a aparecer un **código QR** en la pantalla de la computadora.
5. Ahora agarra el teléfono del **+1 809 486 5386** y haz esto en WhatsApp:
   - Abre **WhatsApp**.
   - Toca los **tres puntitos** arriba a la derecha (en iPhone: **Configuración**).
   - Entra a **Dispositivos vinculados**.
   - Toca **Vincular un dispositivo**.
   - Te va a pedir tu huella o el PIN del teléfono.
   - Apunta la cámara del teléfono al código QR de la pantalla.
6. En unos segundos el estado en el panel debe cambiar a **WORKING**. Ya está
   conectado.

**Detalles importantes:**

- El QR **se vence en menos de un minuto**. Si se venció, refresca la página y
  te da uno nuevo. Ten el teléfono en la mano antes de generarlo.
- Después de vincular, **el teléfono tiene que seguir con WhatsApp instalado y
  con la línea activa**. WhatsApp desvincula los dispositivos si el teléfono
  principal pasa más de ~14 días sin conectarse a internet.
- Vas a ver "WAHA" (o similar) en tu lista de **Dispositivos vinculados**. Ese
  es este sistema. **No lo cierres** desde ahí a menos que quieras desconectar
  todo a propósito.

---

## 4. Variables que van en Vercel

Railway ya está listo. Ahora hay que decirle al sitio web cómo hablarle.

> **ATENCIÓN — regla de seguridad, sin excepciones.** Estas claves **las pegas
> tú mismo** en el dashboard de Vercel, desde tu computadora. **Nunca** las
> mandes por WhatsApp, ni por correo, ni por Telegram, ni se las dictes a nadie
> por teléfono, ni las pegues en un chat con un desarrollador o con una IA.
> Quien tenga la `WAHA_API_KEY` puede mandar mensajes desde tu número personal.
> Si sospechas que una clave se filtró, cámbiala en Railway y en Vercel el mismo
> día (paso 7.5).

**Cómo se ponen:**

1. Entra a **https://vercel.com** y abre el proyecto del sitio (`rentandgopc`).
2. Ve a **Settings** → **Environment Variables**.
3. Por cada una de las de abajo: escribe el nombre en **Key**, pega el valor en
   **Value**, marca los tres ambientes (**Production**, **Preview**,
   **Development**) y dale **Save**.

| Nombre (Key) | Qué le pones |
|---|---|
| `WAHA_URL` | La dirección que te dio Railway, con `https://` y **sin barra al final**. Ej: `https://waha-production-a1b2.up.railway.app` |
| `WAHA_API_KEY` | **El mismo valor exacto** de `WAHA_API_KEY` que pusiste en Railway (CLAVE_LARGA_1) |
| `WAHA_SESSION` | `default` — el mismo valor de `WHATSAPP_START_SESSION` en Railway |
| `WAHA_WEBHOOK_SECRET` | **El mismo valor exacto** de `WHATSAPP_HOOK_HMAC_KEY` de Railway (CLAVE_LARGA_3) |
| `PANEL_PASSWORD` | Una clave **nueva**, la que tú vas a escribir para entrar al panel de WhatsApp del sitio. Esta sí la vas a teclear seguido, que sea buena pero que te la aprendas |
| `PANEL_SECRET` | Otra clave larga y aleatoria **nueva**. Es interna: sirve para que el sitio recuerde que ya iniciaste sesión. No la vas a escribir nunca a mano |

4. **Los valores tienen que coincidir carácter por carácter** entre Railway y
   Vercel. Un espacio de más al pegar y no funciona. Ojo con eso.
5. Después de guardar todas, ve a la pestaña **Deployments**, busca el
   despliegue más reciente, dale a los tres puntitos y elige **Redeploy**. Las
   variables nuevas no aplican hasta que se vuelve a publicar el sitio.

---

## 5. Configurar el webhook

El **webhook** es el aviso que WAHA le manda a tu sitio cada vez que alguien te
escribe. Sin esto, puedes mandar mensajes pero el panel nunca se entera de los
que te llegan.

Si seguiste el paso 2.4 al pie de la letra, **ya está configurado** — esas tres
líneas lo hacen:

```
WHATSAPP_HOOK_URL=https://www.rentandgopc.com/api/wa/webhook
WHATSAPP_HOOK_EVENTS=message
WHATSAPP_HOOK_HMAC_KEY=TU_CLAVE_LARGA_3
```

Qué significa cada una:

- **`WHATSAPP_HOOK_URL`** — la puerta de tu sitio donde llegan los avisos.
  Cópiala tal cual, con `www` y con `https`.
- **`WHATSAPP_HOOK_EVENTS=message`** — solo te avisa de los mensajes que te
  escriben. No de "escribiendo...", ni de confirmaciones de lectura, ni de
  cambios de grupo. Menos ruido y menos gasto.
- **`WHATSAPP_HOOK_HMAC_KEY`** — el secreto de la firma. WAHA firma cada aviso
  con este secreto usando HMAC-SHA512 y manda la firma en un encabezado llamado
  `X-Webhook-Hmac`. Tu sitio verifica esa firma antes de creerle. Es lo que
  impide que un extraño le meta mensajes falsos a tu panel.

**Para comprobar que funciona:**

1. Desde **otro** teléfono, mándale un WhatsApp al +1 809 486 5386. Escribe algo
   como "prueba".
2. Entra al panel de tu sitio (`https://www.rentandgopc.com/whatsapp.html`) con
   tu `PANEL_PASSWORD`.
3. El mensaje debe aparecer ahí en menos de 5 segundos.

Si no aparece, ve al paso 7.3.

---

## 6. RIESGO — léelo completo

Esta sección va sin adornos. Léela antes de prender nada.

### 6.1 Esto no es oficial

WAHA **no es un producto de WhatsApp ni de Meta**. Es una herramienta
independiente que se conecta imitando a WhatsApp Web. Meta no la autoriza, no
la soporta, y su política de uso permite cerrar cuentas que usen clientes no
oficiales.

### 6.2 El riesgo concreto

**Automatizar un número de WhatsApp tiene riesgo real de bloqueo permanente.**
No es teórico, pasa. La documentación oficial de WAHA lo dice claro: ser
marcado como spam unas pocas veces (5 a 10 reportes) es suficiente para que te
bloqueen. Y cada vez que le escribes a alguien que no tiene tu número guardado,
WhatsApp le pregunta a esa persona si eso es spam.

**Y este es tu número personal.** El +1 809 486 5386 es la línea con la que
hablas con tu familia, tus clientes de siempre, tus contactos. Si WhatsApp la
bloquea:

- Pierdes el acceso a esa cuenta de WhatsApp. Todos los chats, todos los grupos.
- El bloqueo puede ser **permanente**. Se puede apelar, pero no hay garantía.
- No hay soporte al que llamar. Es un formulario y a esperar.

Si perder esa cuenta te haría un daño grave al negocio o a lo personal,
**no automatices este número.** Lee el 6.4.

### 6.3 Reglas para bajar el riesgo

Ninguna elimina el riesgo. Todas juntas lo bajan bastante. Cúmplelas.

1. **Espera antes de prender el auto-reply.** Deja el sistema conectado varios
   días (mínimo 3-5, mejor una semana) usando el teléfono normalmente, sin
   respuestas automáticas. Un número que se conecta y de una empieza a mandar
   mensajes automáticos es el patrón clásico de bot y es lo que dispara las
   alarmas. Deja que la conexión "envejezca" primero.

2. **Nunca le escribas a quien no te escribió primero.** Esta es la regla de
   oro y es la recomendación textual de la documentación de WAHA: el bot
   **nunca debe iniciar una conversación**, solo debe **responder** a mensajes
   que recibió. Nada de listas, nada de difusión, nada de "le escribo a los 200
   contactos del Excel". Eso te tumba la cuenta.

3. **Respeta el horario.** Que el auto-reply solo conteste en horario de
   trabajo (por ejemplo 8:00 AM a 8:00 PM, hora de Santo Domingo). Un número
   que contesta al instante a las 3 de la mañana es obviamente una máquina.

4. **Tope diario.** Ponle un límite de mensajes automáticos por día en el panel.
   Empieza bajo — 20 o 30 al día la primera semana — y súbelo poco a poco solo
   si hace falta. Nunca más de 4 mensajes por hora a un mismo contacto.

5. **Que responda como gente.** Que no conteste en el mismo segundo (unos
   segundos de espera se ven mucho más naturales), que no mande siempre el
   texto idéntico, y que si la conversación se complica, la pase a ti.

6. **Ten el botón de parada a mano y úsalo.** El panel tiene un interruptor para
   apagar las respuestas automáticas al instante. Si notas algo raro — mensajes
   repetidos, gente respondiendo molesta, la sesión reconectándose sola —
   apágalo primero y averigua después. Ver la sección 8.

### 6.4 La alternativa oficial

Existe la **WhatsApp Cloud API de Meta**. Es 100% oficial, no te pueden
bloquear por usarla, y te da la palomita de negocio verificado.

El precio de entrar: **necesita un número dedicado que NO tenga WhatsApp
instalado**. No puedes usar tu número personal. Tendrías que comprar una línea
nueva (Claro o Altice, unos RD$300-500 al mes), no instalarle WhatsApp nunca, y
registrarla en Meta Business. Además, Meta cobra por conversación después de
cierta cantidad gratis al mes, y para escribirle tú primero a alguien hay que
usar plantillas de mensaje que Meta tiene que aprobar antes.

**Mi recomendación honesta:** si esto va a crecer y volverse el canal principal
de ventas, compra la línea nueva y vete por la Cloud API. Vale la pena el
trabajo extra. WAHA con tu número personal está bien para probar la idea y ver
si el flujo de clientes justifica el esfuerzo — pero sabiendo que estás
apostando tu cuenta de WhatsApp.

---

## 7. Qué hacer si algo falla

### 7.1 La sesión se cayó y pide el QR otra vez

Entras al panel de WAHA y en vez de **WORKING** ves **SCAN_QR_CODE** o
**FAILED**. Esto pasa si WhatsApp cerró la sesión, si desvinculaste el
dispositivo sin querer, o si el disco no estaba bien montado.

**Qué hacer:** primero revisa el disco, porque si ese es el problema te va a
volver a pasar. En Railway, entra al servicio → **Settings** → busca la sección
de **Volumes** y confirma que dice exactamente `/app/.sessions`. Si dice otra
cosa o no hay volumen, arréglalo con el paso 2.3 — eso solo ya te resuelve el
90% de los casos. Después, en el panel de WAHA dale **Restart** a la sesión y
vuelve a escanear el QR siguiendo el paso 3, con el teléfono del
+1 809 486 5386 en la mano. Y antes de escanear, abre WhatsApp en el teléfono →
**Dispositivos vinculados** y borra las entradas viejas de WAHA que estén ahí,
para que no se te acumulen.

### 7.2 Railway se reinició

Railway reinicia los servicios de vez en cuando por mantenimiento, o si el
programa se queda sin memoria. **Con el volumen bien montado esto no es
problema:** la sesión se restaura sola en 1-2 minutos porque pusiste
`WHATSAPP_RESTART_ALL_SESSIONS=True`.

**Qué hacer:** espera dos minutos y refresca el panel de WAHA. Si sigue caído,
entra al servicio en Railway y mira la pestaña **Deployments** → dale al
despliegue activo → **View Logs**. Si ves mensajes de "out of memory" o el
servicio reiniciándose en bucle, hay que darle más memoria: **Settings** →
sección de recursos, sube el límite de memoria a 512 MB. Eso te sube el costo
unos $3 al mes, pero es preferible a estar reconectando. Si los reinicios son
constantes y no es memoria, considera cambiar `WHATSAPP_DEFAULT_ENGINE` a
`WEBJS` y la imagen a `devlikeapro/waha:latest` — es el motor que la
documentación describe como el más estable y predecible, a cambio de consumir
el doble.

### 7.3 El webhook dejó de llegar

Puedes mandar mensajes desde el panel pero los que te escriben no aparecen. El
problema está en el aviso que va de Railway hacia tu sitio.

**Qué hacer:** revisa estas tres cosas en orden. **Primero**, que
`WHATSAPP_HOOK_URL` en Railway diga exactamente
`https://www.rentandgopc.com/api/wa/webhook` — sin espacios al final, con `www`.
**Segundo**, que `WHATSAPP_HOOK_HMAC_KEY` en Railway y `WAHA_WEBHOOK_SECRET` en
Vercel sean **idénticas**. Si no coinciden, tu sitio recibe los mensajes pero
los rechaza por firma inválida, que es el fallo más común. La forma segura de
arreglarlo: genera una clave nueva, pégala en los dos lados, y vuelve a
publicar el sitio en Vercel. **Tercero**, mira los logs de Vercel (proyecto →
**Logs**, filtra por `/api/wa/webhook`) para ver si los avisos están llegando y
siendo rechazados, o si no están llegando del todo. Si no llegan, el problema
es Railway; si llegan y se rechazan, es la clave.

### 7.4 WhatsApp bloqueó el número

Te aparece "Este número está prohibido para usar WhatsApp" o no puedes iniciar
sesión.

**Qué hacer:** primero, **apaga todo de inmediato** (sección 8). Sigue enviando
y empeoras la situación. Después apela: en el teléfono, WhatsApp te muestra un
botón de **"Solicitar revisión"** cuando intentas entrar — úsalo, y explica en
español, corto y honesto, que es un número de negocio pequeño de alquiler
vacacional, sin dar detalles técnicos ni mencionar herramientas. Si no aparece
el botón, escribe a `support@whatsapp.com` desde el correo del negocio con el
número en formato internacional (+18094865386). La respuesta puede tardar días
y **puede ser que no**. Mientras esperas, pon un aviso en el sitio con un
número alterno o el formulario de contacto, para no perder clientes. Y si te
devuelven la cuenta: **no la vuelvas a automatizar**. La segunda vez el bloqueo
suele ser definitivo. Cómprate la línea dedicada y vete por la Cloud API
(sección 6.4).

### 7.5 Se te filtró una clave

Si mandaste una clave por WhatsApp, correo o chat sin querer, o crees que
alguien más la tiene.

**Qué hacer:** cámbiala el mismo día. Genera un valor nuevo, actualízalo en
Railway (Variables), actualízalo en Vercel (Environment Variables), y vuelve a
publicar el sitio (**Redeploy**). Mientras la clave vieja siga activa, cualquiera
que la tenga puede mandar mensajes desde tu número. Si la que se filtró fue
`WAHA_API_KEY`, además revisa en tu WhatsApp si salieron mensajes que tú no
mandaste.

---

## 8. Cómo apagar todo rápido

Tres niveles, del más suave al más drástico. Empieza por el primero.

### Nivel 1 — Apagar solo las respuestas automáticas (segundos)

1. Entra a `https://www.rentandgopc.com/whatsapp.html`.
2. Métete con tu `PANEL_PASSWORD`.
3. Dale al interruptor de **parada / kill switch**.

El sistema deja de responder solo al instante. **Tu WhatsApp sigue funcionando
normal en el teléfono** y tú puedes seguir contestando a mano. Este es el que
usas el 99% de las veces.

### Nivel 2 — Apagar el servicio en Railway (1 minuto)

Si sospechas algo más serio: que alguien tiene tu clave, o que WhatsApp está a
punto de bloquearte.

1. Entra a `https://railway.com` y abre el proyecto `waha-rentandgo`.
2. Haz clic en el servicio de WAHA.
3. Ve a **Settings** y baja hasta abajo del todo.
4. Dale a **Remove Service** si quieres eliminarlo, o mejor: en la pestaña
   **Deployments**, busca el despliegue activo, dale a los tres puntitos y elige
   **Remove**.

El puente con WhatsApp se corta por completo. El sitio deja de poder mandar
mensajes. **El volumen con la sesión se queda guardado**, así que cuando vuelvas
a desplegar no tienes que escanear el QR de nuevo (siempre que no borres el
volumen).

Para volver a prenderlo: **+ New** → **Docker Image** → `devlikeapro/waha:noweb`,
y verifica que el volumen siga montado en `/app/.sessions`.

### Nivel 3 — Desconectar desde el teléfono (el más seguro)

Es el corte definitivo, y no depende de que Railway ni Vercel te respondan.

1. Agarra el teléfono del +1 809 486 5386.
2. Abre **WhatsApp** → **Dispositivos vinculados**.
3. Toca el dispositivo que dice **WAHA** (o el nombre que aparezca).
4. Dale a **Cerrar sesión**.

Listo. Aunque alguien tenga todas tus claves, ya no puede mandar nada desde tu
número: la conexión ya no existe. Para volver a conectar hay que escanear el QR
otra vez con el teléfono en la mano — o sea, contigo presente.

---

## Notas finales

**No subas secretos a GitHub.** Este repositorio es público. El archivo
`.env.example` que está junto a esta guía tiene solo valores falsos y es seguro.
Pero si algún día creas un archivo `.env` de verdad en esta carpeta con tus
claves reales, **verifica que esté en el `.gitignore` antes de hacer commit**.
Si una clave real llega a GitHub, se considera filtrada aunque la borres después
(queda en el historial) — cámbiala siguiendo el paso 7.5.

**Documentación oficial de WAHA:** https://waha.devlike.pro/docs/

**Resumen de dónde va cada cosa:**

| Cosa | Dónde vive |
|---|---|
| El sitio web y el panel | Vercel |
| El puente con WhatsApp | Railway |
| La sesión de WhatsApp | El volumen de Railway, en `/app/.sessions` |
| Tu número | El teléfono +1 809 486 5386 |
