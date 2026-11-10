"""`reel doctor`: revisa paso a paso que todo esté listo y dice cómo arreglar lo que no."""
from __future__ import annotations

import json
import platform
import shlex
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from . import config, download, ocr, transcribe
from .errors import COOKIES, LOGIN, PIP_UPDATE, RATE_LIMIT

# Comando para (re)instalar las dependencias en el entorno del proyecto
PIP_REQS = "%s -m pip install -r %s" % (
    shlex.quote(sys.executable), shlex.quote(str(config.ROOT / "requirements.txt")))

OK, WARN, BAD = "✅", "⚠️ ", "❌"
APP_SUPPORT = Path.home() / "Library/Application Support"

# Navegadores tipo Chrome: nombre para yt-dlp -> (nombre visible, carpeta de datos, proceso)
CHROMIUM = {
    "chrome": ("Google Chrome", APP_SUPPORT / "Google/Chrome", "Google Chrome"),
    "brave": ("Brave", APP_SUPPORT / "BraveSoftware/Brave-Browser", "Brave Browser"),
    "edge": ("Microsoft Edge", APP_SUPPORT / "Microsoft Edge", "Microsoft Edge"),
    "opera": ("Opera", APP_SUPPORT / "com.operasoftware.Opera", "Opera"),
    "vivaldi": ("Vivaldi", APP_SUPPORT / "Vivaldi", "Vivaldi"),
    "chromium": ("Chromium", APP_SUPPORT / "Chromium", "Chromium"),
}
PROCESS_NAMES = dict({k: v[2] for k, v in CHROMIUM.items()}, firefox="firefox", safari="Safari")


class Report:
    """Va juntando lo que está bien y lo que hay que arreglar para el resumen final."""

    def __init__(self):
        self.good: List[str] = []
        self.fixes: List[Tuple[str, str]] = []  # (problema, comando o paso)

    def ok(self, msg: str) -> None:
        print("   %s %s" % (OK, msg))
        self.good.append(msg)

    def warn(self, msg: str) -> None:
        print("   %s %s" % (WARN, msg))

    def bad(self, msg: str, fix: str) -> None:
        print("   %s %s" % (BAD, msg))
        self.fixes.append((msg, fix))


def _version(cmd: List[str]) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).splitlines()[0].strip()
    except Exception:  # noqa: BLE001
        return None


def _latest_ytdlp() -> Optional[str]:
    """Última versión de yt-dlp publicada en PyPI (None si no hay internet)."""
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=8) as r:
            return json.load(r)["info"]["version"]
    except Exception:  # noqa: BLE001
        return None


def _vtuple(version: str) -> tuple:
    return tuple(int(p) for p in version.split(".") if p.isdigit())


def is_running(browser: str) -> bool:
    """¿Ese navegador está abierto ahora mismo?"""
    name = PROCESS_NAMES.get(browser)
    if not name:
        return False
    return subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0


def _has_instagram_session(extra: dict) -> Optional[bool]:
    """¿Las cookies traen una sesión de Instagram? None = no se pudieron leer.

    Solo mira si EXISTE la cookie de sesión; nunca lee ni muestra su valor.
    """
    try:
        import yt_dlp

        opts = {"quiet": True, "no_warnings": True, "logger": download._SilentLogger()}
        opts.update(extra)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return any(c.name == "sessionid" and "instagram.com" in c.domain
                       for c in ydl.cookiejar)
    except Exception:  # noqa: BLE001
        return None


def list_browser_profiles() -> List[Tuple[str, str, str]]:
    """Perfiles disponibles: [(valor para --browser, descripción, nota)]."""
    found = []

    # Firefox: cada carpeta de Profiles/ con cookies.sqlite es un perfil
    ff_root = APP_SUPPORT / "Firefox/Profiles"
    if ff_root.is_dir():
        for prof in sorted(ff_root.iterdir()):
            if (prof / "cookies.sqlite").exists():
                spec = "firefox:%s" % prof.name
                # Firefox no cifra las cookies: se puede mirar sin pedir permisos
                session = _has_instagram_session(
                    {"cookiesfrombrowser": download.parse_browser_spec(spec)})
                nota = {True: "tiene una sesión de Instagram abierta",
                        False: "sin sesión de Instagram",
                        None: "no pude leerlo"}[session]
                found.append((spec, "Firefox, perfil '%s'" % prof.name.split(".", 1)[-1], nota))

    # Chrome y parientes: carpetas Default / Profile N
    for key, (label, root, _) in CHROMIUM.items():
        if not root.is_dir():
            continue
        names = {}
        try:  # nombres bonitos de los perfiles
            state = json.loads((root / "Local State").read_text(encoding="utf-8"))
            names = {k: v.get("name", k) for k, v in state["profile"]["info_cache"].items()}
        except Exception:  # noqa: BLE001
            pass
        profiles = [p for p in sorted(root.iterdir()) if p.is_dir()
                    and ((p / "Cookies").exists() or (p / "Network/Cookies").exists())]
        for prof in profiles:
            found.append(("%s:%s" % (key, prof.name),
                          "%s, perfil '%s'" % (label, names.get(prof.name) or prof.name),
                          "pedirá permiso del Llavero de macOS la primera vez"))
        if not profiles and ((root / "Cookies").exists() or (root / "Network/Cookies").exists()):
            found.append((key, label, "pedirá permiso del Llavero de macOS la primera vez"))

    # Safari
    if (Path.home() / "Library/Containers/com.apple.Safari").exists():
        found.append(("safari", "Safari",
                      "necesita 'Acceso total al disco' para la Terminal; no recomendado"))
    return found


def run(fix: bool = False) -> int:
    """Corre todas las revisiones. Devuelve 0 si todo está bien, 1 si hay algo que arreglar."""
    rep = Report()
    cfg = config.load_config()
    print("\n🩺 reel doctor — revisión paso a paso\n")

    # 1 ── Computadora
    print("1. Tu computadora")
    chip = "Apple Silicon" if transcribe.backend() == "mlx" else "Intel"
    rep.ok("Chip %s (%s), Python %s" % (chip, platform.machine(), platform.python_version()))

    # 2 ── ffmpeg
    print("\n2. ffmpeg (saca los frames y el audio)")
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        rep.ok(_version(["ffmpeg", "-version"]).split(" Copyright")[0])
    else:
        rep.bad("ffmpeg no está instalado", "brew install ffmpeg")

    # 3 ── yt-dlp
    print("\n3. yt-dlp (baja los reels)")
    try:
        import yt_dlp
        current = yt_dlp.version.__version__
        latest = _latest_ytdlp()
        if latest is None:
            rep.warn("yt-dlp %s instalado, pero no pude consultar si hay versión nueva "
                     "(¿sin internet?)" % current)
        elif _vtuple(current) >= _vtuple(latest):
            rep.ok("yt-dlp %s (es la última versión)" % current)
        else:
            do_update = fix
            if not fix and sys.stdin.isatty():
                print("   %s yt-dlp %s está desactualizado (la última es %s)."
                      % (WARN, current, latest))
                do_update = input("      ¿Lo actualizo ahora? [s/N] ").strip().lower() in ("s", "si", "sí")
            if do_update:
                print("      Actualizando yt-dlp…")
                res = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"])
                if res.returncode == 0:
                    rep.ok("yt-dlp actualizado a %s" % latest)
                else:
                    rep.bad("No pude actualizar yt-dlp", PIP_UPDATE)
            else:
                rep.bad("yt-dlp %s está desactualizado (la última es %s)" % (current, latest),
                        PIP_UPDATE)
    except ImportError:
        rep.bad("yt-dlp no está instalado en el entorno virtual",
                PIP_REQS)

    # 4 ── Whisper
    print("\n4. Whisper (transcribe el audio)")
    model = transcribe.default_model()
    module = "mlx_whisper" if transcribe.backend() == "mlx" else "faster_whisper"
    try:
        from importlib.metadata import version
        __import__(module)
        rep.ok("%s %s" % (module.replace("_", "-"), version(module.replace("_", "-"))))
        if transcribe.model_cached(model):
            rep.ok("Modelo '%s' ya descargado" % model)
        else:
            rep.warn("El modelo '%s' todavía no está descargado: se baja solo la primera "
                     "vez (~%s)." % (model, transcribe.MODEL_SIZES.get(model, "?")))
    except Exception:  # noqa: BLE001
        rep.bad("%s no está instalado" % module,
                PIP_REQS)

    # 5 ── OCR
    print("\n5. OCR (lee el texto en pantalla)")
    engine = ocr.available_engine()
    if engine == "vision":
        rep.ok("Apple Vision (ocrmac) disponible")
    elif engine == "tesseract":
        rep.ok("tesseract disponible (Apple Vision no)")
    else:
        rep.bad("No hay OCR disponible", "brew install tesseract tesseract-lang")

    # 6 ── Navegadores
    print("\n6. Navegadores y perfiles de donde puedo sacar cookies")
    profiles = list_browser_profiles()
    if not profiles:
        rep.warn("No encontré navegadores compatibles.")
    for spec, label, nota in profiles:
        mark = "→" if spec == cfg.get("browser") else " "
        print('   %s %-34s  reel config --browser "%s"' % (mark, label, spec))
        print("       (%s)" % nota)

    # 7 ── Login
    print("\n7. Login de Instagram (cuenta secundaria)")
    methods = download.cookie_methods(cfg)
    browser = (cfg.get("browser") or "").split(":")[0]
    test_url = cfg.get("reel_de_prueba")
    if not test_url:
        rep.warn("No hay reel de prueba, así que no probé el login. Pásame el link de "
                 "cualquier reel público: reel doctor <link>")
        return _resumen(rep, listo=False)

    if cfg.get("browser"):
        print("   Navegador configurado: %s" % cfg["browser"])
        if is_running(browser):
            rep.warn("Ese navegador está ABIERTO. Si las cookies fallan, ciérralo (Cmd+Q).")
    else:
        print("   Navegador configurado: ninguno")
    if config.COOKIES_FILE.exists():
        print("   Archivo cookies.txt: presente (permisos solo para ti)")

    print("   Probando con un reel público, sin login…")
    sin_login = download.probe(test_url, {})
    if sin_login is None:
        rep.ok("Instagram deja bajar reels públicos sin login en este momento")
    else:
        rep.warn("Sin login no funciona: %s" % sin_login.mensaje)

    login_ok = False
    if sin_login is not None and sin_login.kind == RATE_LIMIT:
        rep.bad(sin_login.mensaje, sin_login.paso)
    for label, extra in methods:
        session = _has_instagram_session(extra)
        if session is None:
            rep.bad("No pude leer las %s" % label,
                    "Cierra el navegador (Cmd+Q) y corre de nuevo: reel doctor")
            continue
        if not session:
            rep.bad("Las %s NO tienen una sesión de Instagram" % label,
                    "Abre Instagram en ese perfil, entra con la cuenta secundaria, "
                    "cierra el navegador y corre: reel doctor")
            continue
        print("   Probando UN reel público con %s…" % label)
        err = download.probe(test_url, extra)
        if err is None:
            rep.ok("Login funciona con %s" % label)
            login_ok = True
        else:
            rep.bad("Con %s falló: %s" % (label, err.mensaje), err.paso)

    if not methods:
        paso = ('Elige un perfil de la lista del paso 6 y corre: '
                'reel config --browser "<navegador:perfil>"')
        if sin_login is None:
            rep.warn("No hay login configurado. Por ahora no hace falta, pero Instagram "
                     "lo pide seguido. " + paso)
        elif sin_login.kind in (LOGIN, COOKIES):
            rep.bad("Instagram pide login y no hay cookies configuradas", paso)

    return _resumen(rep, listo=login_ok or sin_login is None)


def _resumen(rep, listo: bool) -> int:
    """Imprime el resumen final. Devuelve 1 si hay algo que arreglar."""
    print("\n" + "─" * 60)
    print("RESUMEN\n")
    print("Está bien:")
    for g in rep.good:
        print("  %s %s" % (OK, g))
    if rep.fixes:
        print("\nTienes que arreglar:")
        for i, (problem, fix_cmd) in enumerate(rep.fixes, 1):
            print("  %d. %s %s\n     → %s" % (i, BAD, problem, fix_cmd))
        print()
        return 1
    if listo:
        print("\n🎉 Todo listo. Prueba con: reel <link>\n")
    return 0
