"""
Renombra un lote de fotos recien guardadas a los nombres que espera el sitio.

El problema que resuelve: al guardar fotos desde un chat quedan como
"imagen (1).jpg", "descarga.jpg", "WhatsApp Image 2026-08-21 at...".
El sitio y properties.json las buscan por nombre exacto, y renombrar 19 a mano
es donde se cuela el error.

    # 1. guarda las fotos EN ORDEN en una carpeta vacia
    # 2. mira el mapeo sin tocar nada:
    python automation/name_photos.py costa-bavaro-garden ~/Downloads/costa

    # 3. si el orden cuadra, aplicalo (copia a images/, no mueve):
    python automation/name_photos.py costa-bavaro-garden ~/Downloads/costa --aplicar

Las fotos se ordenan por fecha de modificacion, que es el orden en que se
guardaron. Si una quedo fuera de sitio, renombrala a mano despues: el mapeo se
imprime siempre antes de copiar nada.

Despues de aplicar, `npm test` dice si falta alguna.
"""

import argparse
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# El orden es el de la galeria de la ficha. Guarda las fotos en este mismo orden.
ORDEN = {
    "costa-bavaro-garden": (
        "images/costa-garden",
        [
            ("pool-wide.jpg", "La piscina grande de frente, con la pergola y los edificios"),
            ("living-dining.jpg", "Sala y comedor con la pared de listones y el espejo redondo"),
            ("living-balcony-open.jpg", "Sala con el balcon abierto, el TV y la puerta de la habitacion"),
            ("living-wide.jpg", "Sala completa con el abanico de techo y el espejo"),
            ("living-entry.jpg", "Sala desde la puerta de entrada: sofa azul y mesa de centro"),
            ("balcony-pool-view.jpg", "La vista desde el balcon: piscina, palmas y edificios"),
            ("kitchen-island.jpg", "Cocina desde el comedor: peninsula, estufa, campana y microondas"),
            ("kitchen-window.jpg", "Cocina con el fregadero doble bajo la ventana"),
            ("kitchen-fridge.jpg", "Cocina con la nevera LG y los banquitos"),
            ("master-bedroom.jpg", "Habitacion principal, cama queen, cortinas floreadas"),
            ("bedroom-twins.jpg", "Segunda habitacion, dos camas individuales y closet empotrado"),
            ("bedroom-twins-bath.jpg", "Segunda habitacion con el bano abierto y el espejo de cuerpo entero"),
            ("pool-aerial.jpg", "Piscina rectangular y piscina de ninos vistas desde arriba"),
            ("pool-loungers.jpg", "Sillones de cuerda bajo techo, la piscina al fondo"),
            ("social-area.jpg", "Mesas y sillas bajo techo, con la piscina detras"),
            ("gym-wide.jpg", "Gimnasio: trotadoras, maquinas y ventanales a la piscina"),
            ("gym-machines.jpg", "Gimnasio de cerca: maquina de poleas, mancuernas y espejos"),
            ("coworking.jpg", "La sala de coworking con los escritorios y el mapa del mundo"),
            ("playground.jpg", "El area de juegos, el arbol grande y la grama"),
        ],
    ),
    "karen-los-corales": (
        "images/karen-los-corales",
        [
            ("entrance-parking.jpg", "La fachada con el letrero GALERIA y los parqueos"),
            ("unit-door.jpg", "La puerta 1D con el numero y la cerradura digital"),
            ("gym-weights.jpg", "El gimnasio de cerca: mancuernas y discos sobre el piso de goma"),
            ("living-tv-wall.jpg", "La sala con la TV encendida (reemplaza la que tiene la clave del wifi)"),
        ],
    ),
}


def main():
    ap = argparse.ArgumentParser(description="Renombra fotos al formato del sitio")
    ap.add_argument("propiedad", choices=sorted(ORDEN), help="slug de la propiedad")
    ap.add_argument("carpeta", help="carpeta donde guardaste las fotos")
    ap.add_argument("--aplicar", action="store_true", help="copiar de verdad (sin esto solo muestra)")
    args = ap.parse_args()

    destino_rel, nombres = ORDEN[args.propiedad]
    destino = REPO_DIR / destino_rel

    origen = Path(args.carpeta).expanduser()
    if not origen.is_dir():
        print(f"No existe la carpeta: {origen}", file=sys.stderr)
        return 1

    fotos = sorted(
        (f for f in origen.iterdir() if f.is_file() and f.suffix.lower() in EXTENSIONS),
        key=lambda f: f.stat().st_mtime,
    )

    if not fotos:
        print(f"No hay imagenes en {origen}", file=sys.stderr)
        return 1

    print(f"{len(fotos)} foto(s) en {origen}")
    print(f"{len(nombres)} nombre(s) esperados para {args.propiedad}")
    if len(fotos) != len(nombres):
        print(
            f"\nOJO: no cuadran las cantidades. Se mapean las primeras "
            f"{min(len(fotos), len(nombres))} y el resto se queda fuera.",
        )
    print()

    plan = []
    for foto, (nombre, descripcion) in zip(fotos, nombres):
        plan.append((foto, destino / nombre))
        marca = " " if (destino / nombre).exists() else "+"
        print(f"  {marca} {foto.name}")
        print(f"      -> {destino_rel}/{nombre}   ({descripcion})")

    sobran = fotos[len(nombres):]
    for foto in sobran:
        print(f"  - {foto.name}   (sobra, no se copia)")

    if not args.aplicar:
        print("\nEsto es solo la vista previa. Si el orden cuadra, repite con --aplicar.")
        return 0

    destino.mkdir(parents=True, exist_ok=True)
    for origen_f, destino_f in plan:
        shutil.copy2(origen_f, destino_f)
    print(f"\nCopiadas {len(plan)} a {destino_rel}/. Corre `npm test` para confirmar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
