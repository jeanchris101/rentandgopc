# Cache del sitio

Notas sobre las reglas de `vercel.json`. Van aqui y no ahi porque `vercel.json`
se valida contra un esquema y **rechaza cualquier clave que no reconozca** — un
comentario metido como `_comentario` tumba el despliegue entero, sin tocar el
sitio en vivo. Nos paso el 21 de agosto de 2026.

## Por que las reglas son distintas por tipo

Antes habia una sola regla, `max-age=3600` para todo. Hacia dano en las dos
direcciones a la vez:

- **Las fotos** son 2.9 MB de la portada y no cambian nunca, pero se volvian a
  descargar cada hora en el celular de quien volvia al sitio.
- **El HTML** si cambia, y una hora es lo que tardaba en verse un precio nuevo.
  El dia que cambiamos dos precios, esa hora era exactamente el problema.

Ahora:

| Que | Cache | Por que |
|---|---|---|
| `/images/*` | 7 dias, y hasta 30 sirviendo mientras revalida | No cambian |
| `.css` / `.js` | 1 dia, hasta 7 revalidando | Cambian poco |
| HTML | **sin regla** | Cae en el default de Vercel: `max-age=0, must-revalidate` |
| `robots.txt`, `sitemap.xml`, `llms.txt` | 1 hora | Los leen robots, no personas |

El HTML sin regla es deliberado. El CDN de Vercel igual lo sirve desde el borde
y se purga solo en cada despliegue, asi que un cambio de precio se ve al
recargar, sin esperar.

## La trampa de los nombres de archivo

Los nombres de las fotos **no llevan hash de contenido**. `pool-wide.jpg` es
siempre `pool-wide.jpg`.

Eso significa que si reemplazas una foto con el mismo nombre, quien ya la tenia
en cache puede seguir viendo la vieja **hasta una semana**.

Para que un cambio de foto se vea al instante: **cambia el nombre del archivo**
y actualiza la referencia en `properties.json` y en la ficha.
