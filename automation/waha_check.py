"""
Diagnostico de punta a punta del panel de WhatsApp.

Se corre DESPUES de desplegar WAHA en Railway y de poner las variables en
Vercel. Revisa la cadena completa en el orden en que se rompe en la practica y,
cuando algo falla, dice que tocar — no solo que fallo.

    python automation/waha_check.py
    python automation/waha_check.py --site https://www.rentandgopc.com

La contrasena del panel sale de PANEL_PASSWORD, o con --pedir-clave te la pide
por teclado (no se ve, no queda en el historial del shell). Preguntar es opt-in
a proposito: ver el comentario en la seccion 3.

No necesita la API key de WAHA ni el secreto del webhook: pregunta a traves del
sitio, que es quien los tiene. Asi un diagnostico nunca es una via para sacar
credenciales.
"""

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_SITE = "https://www.rentandgopc.com"
TIMEOUT = 20

OK, WARN, BAD = "OK  ", "AVISO", "FALLA"


def _request(url: str, method: str = "GET", data: bytes | None = None,
             headers: dict | None = None) -> tuple[int, dict, bytes]:
    """Devuelve (status, headers, body). No lanza por status HTTP."""
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # DNS, TLS, timeout
        return 0, {}, str(e).encode()


def line(state: str, title: str, detail: str = "") -> None:
    print(f"  [{state}] {title}")
    if detail:
        for part in detail.strip().split("\n"):
            print(f"         {part}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnostico del panel de WhatsApp")
    ap.add_argument("--site", default=DEFAULT_SITE, help="URL base del sitio")
    ap.add_argument("--pedir-clave", action="store_true", dest="pedir_clave",
                    help="Pedir la contrasena por teclado (si no, usa PANEL_PASSWORD)")
    args = ap.parse_args()
    site = args.site.rstrip("/")
    problems = 0

    print(f"\nRevisando {site}\n")

    # --- 1. El sitio responde -------------------------------------------
    status, _, _ = _request(site + "/")
    if status == 200:
        line(OK, "El sitio responde")
    else:
        line(BAD, f"El sitio no responde (HTTP {status})",
             "Revisa el deploy en Vercel antes de seguir. Lo demas depende de esto.")
        return 1

    # --- 2. El webhook existe y exige firma ------------------------------
    # Se manda a proposito una firma invalida. La respuesta distingue tres
    # estados sin necesidad de conocer el secreto:
    #   401 -> desplegado y verificando la firma (lo que queremos)
    #   503 -> desplegado pero sin WAHA_WEBHOOK_SECRET en Vercel
    #   404 -> no desplegado
    status, _, _ = _request(
        site + "/api/wa/webhook", method="POST", data=b"{}",
        headers={"Content-Type": "application/json", "x-webhook-hmac": "firma-invalida"},
    )
    if status == 401:
        line(OK, "El webhook esta desplegado y rechaza firmas invalidas")
    elif status == 503:
        problems += 1
        line(BAD, "Falta WAHA_WEBHOOK_SECRET en Vercel",
             "Ponla en Settings -> Environment Variables con el MISMO valor que\n"
             "WHATSAPP_HOOK_HMAC_KEY en Railway, y vuelve a desplegar.")
    elif status == 404:
        problems += 1
        line(BAD, "El webhook no existe (404)", "El deploy no incluyo api/wa/webhook.js.")
    else:
        problems += 1
        line(WARN, f"El webhook respondio HTTP {status}", "Esperaba 401.")

    # --- 3. Entrar al panel ----------------------------------------------
    password = os.environ.get("PANEL_PASSWORD") or ""
    if not password:
        # Preguntar es opt-in (--pedir-clave), no lo automatico.
        #
        # Lo natural seria preguntar salvo que stdin no sea una terminal, pero
        # ese chequeo no es confiable aca: en Git Bash sobre Windows
        # `sys.stdin.isatty()` devuelve True incluso con la entrada cerrada, y
        # getpass en Windows lee la consola directo ignorando la redireccion.
        # Resultado: el script se cuelga para siempre justo en CI, que es donde
        # nadie lo puede rescatar. Con el prompt como opt-in, el peor caso es
        # un mensaje que dice que falta la clave.
        if args.pedir_clave:
            password = getpass.getpass("  Contrasena del panel (no se muestra): ")
        else:
            line(WARN, "Falta la contrasena del panel",
                 "Los chequeos que no necesitan clave ya pasaron. Para el resto:\n"
                 "    PANEL_PASSWORD=tu-clave python automation/waha_check.py\n"
                 "  o, para que te la pida por teclado:\n"
                 "    python automation/waha_check.py --pedir-clave")
            return problems
    if not password:
        line(BAD, "Sin contrasena no puedo revisar el resto")
        return 1

    status, headers, body = _request(
        site + "/api/wa/login", method="POST",
        data=json.dumps({"password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    if status == 503:
        problems += 1
        line(BAD, "Faltan PANEL_PASSWORD o PANEL_SECRET en Vercel",
             "El panel no puede abrir sin las dos. Ponlas y vuelve a desplegar.")
        return problems
    if status != 200:
        problems += 1
        line(BAD, f"No pude entrar al panel (HTTP {status})",
             "Si es 401, la contrasena no coincide con PANEL_PASSWORD en Vercel.")
        return problems

    cookie = headers.get("Set-Cookie", "").split(";")[0]
    if not cookie:
        problems += 1
        line(BAD, "El login no devolvio cookie de sesion")
        return problems
    line(OK, "Entre al panel")
    auth = {"Cookie": cookie}

    # --- 4. Estado de la sesion de WhatsApp -------------------------------
    status, _, body = _request(site + "/api/wa/session", headers=auth)
    if status != 200:
        problems += 1
        line(BAD, f"/api/wa/session respondio HTTP {status}")
        return problems

    try:
        session = json.loads(body)
    except ValueError:
        problems += 1
        line(BAD, "La respuesta de /api/wa/session no es JSON")
        return problems

    state = str(session.get("status", "")).upper()
    if state == "WORKING":
        line(OK, "WhatsApp conectado y funcionando")
    elif state == "SCAN_QR_CODE":
        problems += 1
        line(WARN, "WhatsApp espera que escanees el QR",
             f"Abre {site}/whatsapp.html y escanealo desde el telefono del\n"
             "numero +1 809 486 5386: WhatsApp -> Dispositivos vinculados.")
    elif state == "UNREACHABLE":
        problems += 1
        line(BAD, "Vercel no puede hablar con WAHA",
             "Causas tipicas, en orden:\n"
             " 1. WAHA_URL en Vercel esta mal o le falta https://\n"
             " 2. El servicio en Railway esta apagado o dormido\n"
             " 3. WAHA_API_KEY no coincide entre Railway y Vercel")
    elif state in ("STOPPED", "FAILED"):
        problems += 1
        line(BAD, f"La sesion de WhatsApp esta en {state}",
             "Reinicia el servicio en Railway y vuelve a correr esto.")
    else:
        line(WARN, f"Estado de sesion desconocido: {state or '(vacio)'}")

    # --- 5. La bandeja carga ----------------------------------------------
    status, _, body = _request(site + "/api/wa/threads", headers=auth)
    if status == 200:
        try:
            data = json.loads(body)
            n = len(data.get("threads", []))
            cfg = data.get("config", {})
            line(OK, f"La bandeja carga ({n} conversacion(es))")
            if cfg.get("autoReplyEnabled"):
                line(WARN, "La auto-respuesta esta ENCENDIDA",
                     "Recomendado: dejarla apagada los primeros dias, usando el\n"
                     "telefono normal, antes de encenderla.")
            else:
                line(OK, "La auto-respuesta esta apagada (como debe empezar)")
        except ValueError:
            problems += 1
            line(BAD, "La bandeja no devolvio JSON valido")
    else:
        problems += 1
        line(BAD, f"La bandeja respondio HTTP {status}")

    # --- 6. La cola de grupos ---------------------------------------------
    status, _, body = _request(site + "/api/groups/plan", headers=auth)
    if status == 200:
        try:
            plan = json.loads(body)
            asgs = plan.get("assignments", [])
            camp = plan.get("campaign") or {}
            if asgs:
                where = camp.get("propertyName") or "varias propiedades"
                line(OK, f"La cola de grupos tiene {len(asgs)} asignacion(es) hoy: {where}")
            else:
                line(WARN, "La cola de grupos no tiene nada para hoy",
                     str(plan.get("reason") or "Puede ser que todos los grupos esten en descanso."))
        except ValueError:
            problems += 1
            line(BAD, "La cola de grupos no devolvio JSON valido")
    else:
        problems += 1
        line(BAD, f"La cola de grupos respondio HTTP {status}")

    # --- Resumen -----------------------------------------------------------
    print()
    if problems == 0:
        print("  Todo en orden. El panel esta listo para recibir mensajes.\n")
    else:
        print(f"  {problems} cosa(s) por resolver. Arregla de arriba hacia abajo:\n"
              "  cada paso depende del anterior.\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
