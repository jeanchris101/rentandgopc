# Asistente de grupos — Rent & Go PC

Extension de Chrome para publicar en los 18 grupos de Facebook sin equivocarte
de grupo, de propiedad, de idioma ni de foto.

> Nota de estilo: este archivo va sin acentos, igual que el resto de los
> comentarios y datos del proyecto, para que copiar y pegar entre el panel,
> Facebook y WhatsApp no dependa del encoding de nadie.

---

## Lo que es y lo que NO es

**ES** un llenador de formularios contigo delante. Abres el grupo, la extension
mira la cola (la misma de `group-queue.html`), te dice que toca publicar ahi y
te escribe el texto en el compositor de un clic. **Tu lo lees, lo arreglas si
quieres, y TU aprietas el boton Publicar de Facebook.**

**NO ES** un bot:

- No publica sola. Nunca hace clic en Publicar.
- No recorre grupos en tanda.
- No programa envios ni tiene temporizadores.
- No corre si tu no estas delante: todo arranca con un clic tuyo.

### Por que esa linea, y por que no se cruza

Automatizar el **envio** de posts a grupos viola los Terminos de Meta. Quien
paga eso no es "la extension": es tu cuenta personal de Facebook, la misma que
administra la Pagina de Rent & Go. Si Meta te la tumba, se va la Pagina, se van
los grupos y se va el canal. No hay ahorro de tiempo que pague ese riesgo.

Llenar un campo que un humano revisa y manda **no** es eso. Es lo mismo que
copiar y pegar con Ctrl+V, solo que sin equivocarte de grupo y sin gastar 10
minutos armando el texto. La accion que Facebook cuenta como "publicar" —
apretar el boton — la sigues haciendo tu, con los ojos en el texto.

Por eso, dentro del codigo:

- La unica funcion que hace clic es `safeClick()` en `content.js`, y **se niega
  en seco** si el nombre del control se parece a Publicar / Publish / Publier /
  Compartir / Enviar. Lo unico que llega a clicar es la caja "Escribe algo..."
  para abrir el compositor.
- No hay `setInterval` ni `setTimeout` que dispare un envio. El unico intervalo
  que existe compara la URL cada segundo, porque Facebook cambia de pagina sin
  recargar.
- El boton **"Ya lo publique"** lo aprietas **despues** de publicar. No publica:
  anota en el historial para que arranque el cooldown de 7 dias y para que el
  `ref` sirva de atribucion a los 30 dias.

Si algun dia alguien viene a "automatizar el ultimo clic": ese es exactamente
el clic que no se automatiza.

---

## Instalarla (no esta en la tienda de Chrome)

1. Abre Chrome y ve a `chrome://extensions`.
2. Arriba a la derecha, prende **Modo de desarrollador**.
3. Dale a **Cargar descomprimida**.
4. Escoge la carpeta `extension/` de este repo (la que tiene `manifest.json`).
5. Te aparece "Rent & Go PC — Asistente de grupos". Fijala en la barra con el
   pin del icono de piezas, para tenerla a mano.

El icono es el generico de Chrome: no hay PNG en el repo a proposito (esto es un
repo publico y no vale la pena meter binarios por un icono). Identificala por el
nombre.

Cuando cambies algo del codigo: vuelve a `chrome://extensions` y dale al boton
de recargar de la tarjeta. Si tenias Facebook abierto, recarga tambien esa
pestana.

---

## El token (se hace una vez)

La cookie del panel es `SameSite=Strict` a proposito, asi que **no viaja** en
las peticiones que salen desde la extension. Por eso hay un secreto aparte, solo
para los dos endpoints de grupos.

### 1. Generalo

```bash
openssl rand -hex 32
```

Minimo 24 caracteres; el servidor rechaza cualquier cosa mas corta. Con `-hex 32`
salen 64, que esta bien.

### 2. Ponlo en Vercel

Proyecto → **Settings → Environment Variables** → nueva variable:

- Nombre: `EXTENSION_TOKEN`
- Valor: lo que salio del comando
- Entornos: Production (y Preview si pruebas ahi)

Redespliega para que la variable exista en las funciones.

### 3. Pegalo en la extension

Clic en el icono de la extension → **Ajustes**:

- **URL del sitio**: `https://www.rentandgopc.com` (sin barra al final)
- **Token de la extension**: pega el valor
- **Guardar**

Arriba deberias ver el punto verde: _"Conectado. Hoy toca N grupos."_

**El token no va en este repo, que es publico.** Vive en Vercel y en el
`chrome.storage.local` de tu navegador, nada mas. Si se te filtra, cambias la
variable en Vercel, redespliegas y lo pegas de nuevo en el popup: no tienes que
tocar la clave del panel ni cerrar sesion en ningun lado.

---

## El dia a dia

1. **Abre el popup** (icono de la extension). Ahi ves los 2-3 grupos que tocan
   hoy, con la propiedad, el precio y el idioma de cada uno. Cada nombre es un
   enlace: dale y se abre el grupo.
2. **Ya en el grupo**, abajo a la derecha sale el panel verde con:
   - la propiedad asignada, el precio y el idioma
   - la vista previa del texto exacto que va
   - los botones
3. **"Llenar el post"** → te abre el compositor si hace falta y te escribe el
   texto dentro.
4. **Lee lo que quedo.** Si algo no te cuadra, arreglalo ahi mismo, es tu post.
5. **"Bajar la foto"** → cae en `Descargas/rentandgo/`. **Arrastrala** al
   compositor, o dale a Foto/video y buscala. (La extension no la adjunta sola,
   ver mas abajo.)
6. **Aprietas Publicar tu.** La extension no lo hace y no lo va a hacer.
7. **"Ya lo publique"** → queda anotado. El grupo entra en cooldown de 7 dias.
8. **Espera unos minutos** y recien ahi dale a **"Copiar comentario"** y pega el
   link de wa.me en el **primer comentario**.

### Por que esperar para el comentario

Visto en produccion: los comentarios con link de `wa.me` puestos al instante de
publicar, Facebook los esconde. Espera unos minutos y pegalo. La extension te lo
recuerda pero **no** te pone un temporizador ni lo hace por ti: eso ya seria un
envio automatico.

### Lo que el panel te dice sin que preguntes

- **Grupo en cooldown**: "Este grupo recibio X el 12 jul. Hoy NO toca publicar
  aqui. Se libera el 19 jul." Y no te ofrece llenar nada.
- **Grupo que no toca hoy**: te lista los que si tocan, con enlace.
- **Ya publicaste hoy aqui**: te deja copiar el comentario y ya.
- **Grupo que no esta en los 18**: el panel **no aparece**. Ni un pixel.

El panel se contrae con el `−`, se cierra por hoy con la `×`, y se acuerda de
como lo dejaste.

---

## Si el llenado falla (Facebook cambia el DOM cada rato)

El compositor de Facebook corre sobre **Lexical**. Escribir en `textContent` no
sirve: Lexical mantiene su propio estado y en el siguiente render te borra lo que
metiste. La extension intenta tres cosas, en este orden, y **verifica** despues
de cada una leyendo lo que quedo en el compositor:

1. `document.execCommand('insertText')` linea por linea — el navegador escribe y
   dispara los mismos eventos que una tecla de verdad.
2. Un evento `paste` sintetico con su propio `DataTransfer`.
3. `InputEvent('beforeinput', {inputType:'insertText'})` a mano.

Si los tres fallan, **no se inventa nada**: te copia el texto al portapapeles y
te lo dice, para que pegues con Ctrl+V.

**Que hacer segun el mensaje:**

| Lo que ves | Que paso | Que haces |
| --- | --- | --- |
| "No encontre el compositor" | Facebook cambio el HTML o la caja no cargo | Abre el compositor tu (dale a "Escribe algo...") y dale otra vez a Llenar. Si el texto ya esta copiado, pega con Ctrl+V. |
| "No pude escribir dentro del compositor" | Encontro la caja pero Lexical no acepto el texto | Haz clic dentro de la caja y pega con Ctrl+V (ya te lo copio). |
| "El compositor ya tiene texto tuyo" | Habia algo escrito y no te lo piso | Borra lo que hay y dale a Llenar otra vez. |
| El panel no sale en un grupo de los 18 | No hay plan (token malo, sin internet) | Abre el popup: ahi esta el estado de conexion con el error de verdad. |

**Si deja de funcionar del todo**: siempre te queda `group-queue.html` en el
sitio, que hace lo mismo con copiar y pegar. La extension es el atajo, no el
unico camino. El enlace esta abajo en el popup.

**Para arreglarlo de raiz** (o para quien meta mano en el codigo): los selectores
estan todos juntos arriba en `content.js`, en `COMPOSER_SELECTORS` y
`OPENER_RE`. Casi siempre alcanza con agregar un selector nuevo a la lista; el
mas estable es `div[data-lexical-editor="true"][contenteditable="true"]`, que lo
pone Lexical y no el equipo de diseno de Facebook.

---

## La foto: por que no se adjunta sola

Se podria intentar con `DataTransfer` y un `drop` sintetico sobre el compositor,
pero **no se puede garantizar** que Facebook lo acepte, y una foto que "casi" se
adjunta es peor que ninguna: publicas sin foto sin darte cuenta. Asi que la
extension hace lo que si es seguro: te la baja a `Descargas/rentandgo/` con
`chrome.downloads` y te avisa que la arrastres. Dos segundos, cero sorpresas.

Si algun dia se comprueba que el adjunto programatico funciona parejo, se agrega
**con la descarga de respaldo**, no en su lugar.

---

## Permisos, uno por uno

| Permiso | Para que | Por que no es mas |
| --- | --- | --- |
| `storage` | Guardar el token, la URL del sitio, el cache del plan y si dejaste el panel contraido o cerrado por hoy. | Es `storage.local`: no sincroniza con tu cuenta de Google, o sea que el token no sale de esta maquina. |
| `downloads` | Bajar la foto del post y abrir la carpeta donde cayo. | El service worker solo baja URLs que empiezan con la URL base configurada. Cualquier otra cosa la rechaza. |
| `https://www.facebook.com/groups/*` | Que el content script pueda leer en que grupo estas y escribir en el compositor. | Solo `/groups/`. En tu feed, en Marketplace, en Messenger o en cualquier otra parte de Facebook la extension **no corre**. |
| `https://www.rentandgopc.com/*` | Que el service worker pueda llamar a `/api/groups/plan` y `/api/groups/mark`. | Es tu propio sitio. Ademas evita el CORS: como el fetch sale del service worker con este permiso, la API no tuvo que abrirse a facebook.com. |

**Lo que NO se pide, a proposito:**

- `tabs` / `activeTab` — no hace falta. Los enlaces del popup son enlaces
  normales, y el content script ya sabe en que pagina esta.
- `<all_urls>` — jamas. La extension solo existe en grupos de Facebook.
- `scripting` — el content script se declara en el manifest; no se inyecta nada
  a mano.
- `alarms` — no hay nada programado. Si hubiera `alarms`, deberias sospechar.

---

## Como esta hecha

| Archivo | Que hace |
| --- | --- |
| `manifest.json` | Manifest V3. Permisos y donde corre cada cosa. |
| `background.js` | Service worker. El **unico** que habla con el sitio y el unico que ve el token. Cachea el plan 5 minutos. |
| `content.js` | El panel dentro del grupo + el llenado del compositor. Nunca recibe el token. |
| `popup.html` / `popup.js` | Ajustes, estado de conexion y el plan de hoy. |
| `styles.css` | Estilos del panel y del popup. Todo con prefijo `rgpc-`. |

Sin frameworks, sin dependencias, sin CDN. JavaScript puro.

### Dos decisiones que vale la pena saber

**El token nunca entra a facebook.com.** El content script no lo recibe ni lo
lee: le pide las cosas al service worker por mensajes. Aunque Facebook se
tomara la pagina entera, el token no esta ahi.

**Cero `innerHTML` con datos dinamicos.** Todo el panel se arma con
`createElement` y `textContent`. Es un panel inyectado en facebook.com: un XSS
ahi no seria un bug feo, seria tu cuenta.

---

## Problemas comunes

**"Falta el token"** → No lo guardaste, o le diste a Guardar con el campo vacio.
Popup → Ajustes → pegalo → Guardar.

**"El token no sirve" (401)** → El de la extension y el de Vercel no son el
mismo. Ojo con los espacios al copiar. Si acabas de cambiar la variable en
Vercel, hace falta redesplegar.

**"El servidor dice que le falta EXTENSION_TOKEN" (503)** → La variable no
existe en el entorno donde estas pegando, o mide menos de 24 caracteres.

**"No hay conexion"** → O estas sin internet, o la URL base esta mal escrita.
Tiene que ser exactamente `https://www.rentandgopc.com`, sin barra final y con
el `www`.

**El panel salio con datos viejos** → Te lo dice: "Plan sin actualizar". Es el
cache sirviendo la ultima copia buena porque la red fallo. Popup → Probar
conexion.

**Cerre el panel sin querer** → La `×` lo cierra **por hoy**. Recarga la pagina
manana, o abre el popup y dale a Probar conexion despues de medianoche (hora de
Santo Domingo, que es con la que trabaja la cola).

---

## Las reglas que la cola respeta (y la extension no se salta)

Vienen de `hybrid-facebook-strategy.md` y las aplica el servidor, no la
extension. Aqui solo se muestran:

1. Un post de listado por grupo **por semana** (cooldown de 7 dias).
2. Maximo **2-3 grupos por dia**.
3. La misma propiedad **no** va a dos grupos el mismo dia.
4. El idioma lo decide el grupo, no la fecha.
5. El link de `wa.me` va en el **primer comentario**, nunca en el cuerpo del
   post.

Si el panel te dice que hoy no toca, hoy no toca. Ese dia toca comentar y
aportar en los grupos, que es lo que hace que cuando si publiques no te lean
como spam.
