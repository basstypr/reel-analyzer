"""Comando `reel`: procesa uno o varios reels de punta a punta."""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import config, download, frames, index, links, ocr, transcribe
from .errors import LOGIN, STOP_RUN, ReelError

WAIT_RANGE = (8, 20)   # segundos de espera aleatoria entre reels
DEFAULT_MAX = 40       # máximo de reels por corrida


def say(msg: str) -> None:
    print("   " + msg, flush=True)


# ───────────────────────── ayuda de login ─────────────────────────

def login_help(cfg: dict) -> str:
    """Guía paso a paso cuando el problema es el login."""
    browser = cfg.get("browser")
    if browser:
        nombre = browser.split(":")[0].capitalize()
        return (
            "\n🔑 CÓMO ARREGLAR EL LOGIN\n"
            "   Perfil configurado: %s\n"
            "   1. Abre %s en ESE perfil y entra a instagram.com.\n"
            "   2. Revisa que esté logueada tu cuenta SECUNDARIA (si te sacó, vuelve a entrar).\n"
            "   3. CIERRA %s por completo (Cmd+Q): abierto puede bloquear las cookies.\n"
            "   4. Corre: reel doctor   (confirma que el login funciona)\n"
            "   5. Vuelve a correr el mismo comando; los reels ya hechos se saltan solos.\n"
            % (browser, nombre, nombre)
        )
    return (
        "\n🔑 CÓMO ARREGLAR EL LOGIN\n"
        "   Todavía no has configurado de dónde sacar las cookies.\n"
        "   1. Elige un navegador/perfil APARTE (recomendado: Firefox) y entra ahí a\n"
        "      instagram.com con tu cuenta SECUNDARIA.\n"
        "   2. CIERRA ese navegador por completo (Cmd+Q).\n"
        "   3. Corre: reel doctor   (te lista los perfiles y el comando exacto)\n"
        '   4. Configúralo, por ejemplo: reel config --browser "firefox"\n'
        "   5. Vuelve a correr el mismo comando.\n"
        "   Alternativa: exporta un cookies.txt y corre: reel config --cookies-file <ruta>\n"
    )


# ───────────────────────── modelo de Whisper ─────────────────────────

def ensure_model(model: str, assume_yes: bool) -> bool:
    """Avisa del tamaño del modelo antes de bajarlo. False = el usuario dijo que no."""
    if transcribe.model_cached(model):
        return True
    size = transcribe.MODEL_SIZES.get(model, "tamaño desconocido")
    print("\n📦 El modelo de Whisper '%s' no está descargado todavía (~%s, una sola vez)."
          % (model, size))
    if assume_yes:
        print("   Se bajará ahora (--yes).")
        return True
    if not sys.stdin.isatty():
        print("   Vuelve a correr con --yes para aceptar la descarga.")
        return False
    return input("   ¿Lo bajo ahora? [s/N] ").strip().lower() in ("s", "si", "sí")


# ───────────────────────── un reel ─────────────────────────

def process_reel(link: str, code: str, args, cfg: dict, model: str) -> dict:
    """Procesa un reel completo. Devuelve su metadata. Lanza ReelError si no se pudo bajar."""
    folder = config.OUTPUT / code
    if folder.exists():
        shutil.rmtree(folder)  # restos de un intento anterior o --force
    folder.mkdir(parents=True)
    video: Optional[Path] = None
    try:
        # 1-2) Bajar + metadata
        say("⬇️  Bajando el reel…")
        try:
            info, video, metodo = download.download(link, folder, cfg, say)
        except ReelError:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        duracion = float(info.get("duration") or 0) or frames.video_duration(video)
        fecha = ""
        if info.get("timestamp"):
            fecha = datetime.fromtimestamp(info["timestamp"], tz=timezone.utc).isoformat()
        elif info.get("upload_date"):
            d = info["upload_date"]
            fecha = "%s-%s-%s" % (d[:4], d[4:6], d[6:])
        autor = info.get("channel") or info.get("uploader_id") or info.get("uploader") or ""
        say("   @%s · %.0f s · bajado %s" % (autor, duracion, metodo))

        # 3) Transcripción
        say("🎙️  Transcribiendo el audio (Whisper %s)…" % model)
        result = transcribe.transcribe(video, model)
        (folder / "transcript.txt").write_text(
            transcribe.format_transcript(result), encoding="utf-8")
        say("   idioma detectado: %s" % (result["language"] or "sin voz"))

        # 4) Frames + contact sheet
        say("🎞️  Sacando frames…")
        times = frames.pick_times(frames.detect_scenes(video), duracion)
        shots = frames.extract_frames(video, folder / "frames", times)
        frames.make_contact_sheet(shots, folder / "contact_sheet.jpg")
        say("   %d frames + contact_sheet.jpg" % len(shots))

        # 5) OCR
        say("🔤 Leyendo el texto en pantalla…")
        merged = ocr.merge_ocr([(t, ocr.read_frame(p)) for t, p in shots])
        (folder / "onscreen_text.txt").write_text(ocr.format_ocr(merged), encoding="utf-8")
        say("   %d bloques de texto" % len(merged))

        # 6) metadata.json (se escribe al final: su existencia marca "reel terminado")
        meta = {
            "link": link,
            "shortcode": code,
            "autor": autor,
            "autor_nombre": info.get("uploader") or "",
            "caption": info.get("description") or "",
            "duracion_seg": round(duracion, 1),
            "fecha": fecha,
            "idioma": result["language"],
            "modelo_whisper": model,
            "frames": len(shots),
            "descarga": metodo,
            "procesado": datetime.now().isoformat(timespec="seconds"),
        }
        (folder / "metadata.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return meta
    finally:
        # Borrar el video (y cualquier resto de la descarga) salvo --keep-video
        if not args.keep_video:
            for leftover in folder.glob("video.*") if folder.exists() else []:
                leftover.unlink()


# ───────────────────────── corrida ─────────────────────────

def run(args) -> int:
    cfg = config.load_config()

    # Juntar links del comando y del archivo
    raw: List[str] = list(args.links)
    if args.file:
        try:
            raw += links.read_links_file(Path(args.file).expanduser())
        except OSError as exc:
            print("❌ No pude leer el archivo de links: %s" % exc)
            return 2
    todos = links.parse_links(raw)
    if not todos:
        print("No me diste ningún link. Uso: reel <link>   o   reel --file links.txt")
        return 2

    # Separar: inválidos, ya procesados y pendientes
    pendientes = []
    for link in todos:
        code = links.extract_shortcode(link)
        if not code:
            print("⚠️  No parece un link de reel, lo salto: %s" % link)
            continue
        if (config.OUTPUT / code / "metadata.json").exists() and not args.force:
            print("⏭️  %s ya estaba procesado, lo salto (usa --force para rehacerlo)." % code)
            continue
        pendientes.append((links.canonical_link(code), code))

    if not pendientes:
        print("Nada nuevo que procesar.")
        return 0
    if len(pendientes) > args.max:
        print("ℹ️  Hay %d reels pendientes; en esta corrida hago solo %d (límite --max). "
              "Vuelve a correr el comando después para seguir."
              % (len(pendientes), args.max))
        pendientes = pendientes[: args.max]

    model = args.model or transcribe.default_model()
    if not ensure_model(model, args.yes):
        return 1

    ok = fallos = 0
    for n, (link, code) in enumerate(pendientes, 1):
        if n > 1:
            espera = random.uniform(*WAIT_RANGE)
            print("\n⏳ Espero %.0f s antes del siguiente (para no levantar sospechas)…" % espera)
            time.sleep(espera)
        print("\n[%d/%d] %s" % (n, len(pendientes), code))
        try:
            meta = process_reel(link, code, args, cfg, model)
            index.upsert_row(config.INDEX_CSV, link, meta["autor"],
                             "%.0f" % meta["duracion_seg"], meta["idioma"], "ok")
            say("✅ Listo → %s" % (config.OUTPUT / code))
            ok += 1
        except ReelError as err:
            fallos += 1
            index.upsert_row(config.INDEX_CSV, link, estado="error: " + err.info.mensaje)
            say("❌ %s" % err.info.mensaje)
            say("   Qué hacer: %s" % err.info.paso)
            if err.info.kind == LOGIN:
                print(login_help(cfg))
            if err.info.kind in STOP_RUN:
                quedan = len(pendientes) - n
                print("🛑 Paro la corrida aquí para no empeorar las cosas"
                      + (" (quedaron %d reels sin intentar)." % quedan if quedan else "."))
                break
        except KeyboardInterrupt:
            shutil.rmtree(config.OUTPUT / code, ignore_errors=True)
            print("\nCancelado por ti.")
            return 130
        except Exception as exc:  # noqa: BLE001 - un reel roto no debe tumbar la corrida
            fallos += 1
            index.upsert_row(config.INDEX_CSV, link,
                             estado="error: fallo interno (%s)" % type(exc).__name__)
            say("❌ Fallo interno procesando este reel: %s" % exc)

    print("\nResumen: %d ok, %d con error. Índice: %s" % (ok, fallos, config.INDEX_CSV))
    return 0 if fallos == 0 else 1


# ───────────────────────── reel config ─────────────────────────

def cmd_config(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="reel config",
                                description="Configura de dónde sacar las cookies de Instagram.")
    p.add_argument("--browser", help='navegador[:perfil], ej. "firefox" o "chrome:Profile 2"')
    p.add_argument("--no-browser", action="store_true", help="quita el navegador configurado")
    p.add_argument("--cookies-file", help="ruta a un cookies.txt exportado (se copia al proyecto)")
    p.add_argument("--remove-cookies-file", action="store_true", help="borra el cookies.txt guardado")
    args = p.parse_args(argv)
    cfg = config.load_config()

    if args.browser:
        cfg["browser"] = args.browser.strip()
    if args.no_browser:
        cfg["browser"] = None
    if args.browser or args.no_browser:
        config.save_config(cfg)
    if args.cookies_file:
        src = Path(args.cookies_file).expanduser()
        if not src.is_file():
            print("❌ No existe el archivo: %s" % src)
            return 2
        config.install_cookies_file(src)
        print("✅ cookies.txt copiado al proyecto (solo tú puedes leerlo). "
              "Ya puedes borrar el original.")
    if args.remove_cookies_file and config.COOKIES_FILE.exists():
        config.COOKIES_FILE.unlink()

    print("Navegador para cookies: %s" % (cfg.get("browser") or "ninguno"))
    print("Archivo cookies.txt:    %s" % ("sí" if config.COOKIES_FILE.exists() else "no"))
    print("Para probar que funciona: reel doctor")
    return 0


# ───────────────────────── entrada ─────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reel",
        description="Analiza reels de Instagram en local: transcript, texto en pantalla y frames.",
        epilog="Otros comandos:  reel doctor [link] [--fix]   ·   reel config --browser \"firefox\"",
    )
    p.add_argument("links", nargs="*", help="uno o más links de reels")
    p.add_argument("--file", "-f", help="archivo .txt con un link por línea")
    p.add_argument("--force", action="store_true", help="rehacer reels ya procesados")
    p.add_argument("--keep-video", action="store_true", help="no borrar el video al terminar")
    p.add_argument("--max", type=int, default=DEFAULT_MAX,
                   help="máximo de reels por corrida (por defecto %d)" % DEFAULT_MAX)
    p.add_argument("--model", help="modelo de Whisper (por defecto: large-v3-turbo en "
                                   "Apple Silicon, small en Intel)")
    p.add_argument("--yes", "-y", action="store_true",
                   help="aceptar la descarga del modelo sin preguntar")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "doctor":
        from . import doctor
        # `reel doctor <link>`: usa ese reel público para probar el login y lo recuerda
        test_reel = next((a for a in argv[1:] if links.extract_shortcode(a)), None)
        if test_reel:
            cfg = config.load_config()
            cfg["reel_de_prueba"] = links.canonical_link(links.extract_shortcode(test_reel))
            config.save_config(cfg)
        return doctor.run(fix="--fix" in argv)
    if argv and argv[0] == "config":
        return cmd_config(argv[1:])
    try:
        return run(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        print("\nCancelado por ti.")
        return 130
