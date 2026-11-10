# reel-analyzer

> 🇬🇧 [Read me in English](README.md)

Analiza reels de Instagram **en tu Mac, gratis y sin servicios externos**.
Para cada reel guarda: datos (autor, caption, duración, fecha), transcripción
del audio, texto en pantalla (OCR), frames y una imagen resumen (contact sheet).

## Instalar

Requisitos: macOS, Python 3.9+ y ffmpeg (`brew install ffmpeg`).

```bash
git clone https://github.com/basstypr/reel-analyzer.git
cd reel-analyzer
./install.sh
reel doctor
```

`install.sh` crea un entorno virtual dentro de la carpeta, instala las
dependencias y deja el comando `reel` en `~/.local/bin`. No instala nada en
el sistema.

La primera transcripción baja el modelo de Whisper (~1.6 GB en Apple Silicon,
~500 MB en Intel). El programa avisa antes de bajarlo.

## Usar

```bash
reel https://www.instagram.com/reel/XXXXXXXX/     # un reel
reel --file links.txt                             # varios (un link por línea)
reel doctor                                       # revisa que todo funcione
```

Opciones: `--force` (rehacer uno ya hecho), `--keep-video` (no borrar el video),
`--max 60` (más de 40 por corrida), `--model small` (otro modelo de Whisper),
`--yes` (aceptar la descarga del modelo sin preguntar).

Resultados en `output/<shortcode>/`:

| Archivo | Qué tiene |
|---|---|
| `metadata.json` | link, autor, caption, duración, fecha, idioma |
| `transcript.txt` | lo que se dice (texto corrido y con tiempos) |
| `onscreen_text.txt` | texto que aparece en pantalla, sin repetidos |
| `frames/` y `contact_sheet.jpg` | hasta 12 frames y la cuadrícula con sus segundos |

`output/index.csv` lleva una fila por reel con su estado (`ok` o `error: …`).

Entre reel y reel espera 8–20 segundos, y si Instagram dice "demasiadas
descargas" la corrida se detiene sola. Los reels ya hechos se saltan, así que
puedes volver a correr el mismo comando para continuar.

## Arreglar el login

El programa **nunca pide usuario ni contraseña**: solo lee las cookies de un
navegador donde ya iniciaste sesión. Usa una **cuenta secundaria** en un
navegador o perfil aparte (recomendado: Firefox solo para esto).

1. Abre ese navegador/perfil, entra a instagram.com con la cuenta secundaria.
2. **Cierra el navegador por completo (Cmd+Q).**
3. `reel doctor` → en el paso 6 lista los perfiles con el comando exacto.
4. `reel config --browser "firefox"` (o el que te indique el doctor,
   por ejemplo `"chrome:Profile 2"`).
5. `reel doctor <link de cualquier reel público>`: el paso 7 debe decir "Login funciona".

Plan B: exporta un `cookies.txt` (formato Netscape) con una extensión del
navegador y corre `reel config --cookies-file ~/Downloads/cookies.txt`. Se copia
al proyecto con permisos solo para ti y está en `.gitignore`.

| Mensaje | Qué hacer |
|---|---|
| Instagram pide login | Los 5 pasos de arriba |
| No pude leer las cookies | Cierra el navegador (Cmd+Q) y reintenta |
| Demasiadas descargas | Espera al menos 1 hora |
| El reel es privado o lo borraron | Ábrelo en el navegador para confirmar |
| yt-dlp está desactualizado | `reel doctor --fix` |

## Privacidad

- Nada sale de tu Mac, salvo las peticiones a Instagram para bajar cada reel
  y la descarga única del modelo desde Hugging Face.
- `config.json`, `cookies.txt`, `links.txt` y `output/` están en `.gitignore`.
- El contenido de las cookies nunca se imprime.

## Uso responsable

Esta herramienta es para análisis personal de contenido público. Tú eres
responsable de cumplir los Términos de Uso de Instagram y las leyes de derechos
de autor. No republiques contenido ajeno, mantén el volumen bajo y usa una
cuenta secundaria. Este proyecto no está afiliado a Instagram ni a Meta.

## Pruebas

```bash
.venv/bin/python -m pytest
```

## Licencia

[MIT](LICENSE)
