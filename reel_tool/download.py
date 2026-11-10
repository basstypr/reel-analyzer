"""Bajar el reel con yt-dlp: primero sin login, luego con cookies.

Las cookies solo se le pasan a yt-dlp; este módulo nunca las imprime ni las guarda.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import config
from .errors import COOKIES, LOGIN, ErrorInfo, ReelError, translate_error


class _SilentLogger:
    """Logger mudo para que yt-dlp no llene la pantalla."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def parse_browser_spec(spec: str) -> tuple:
    """'chrome:Profile 2' -> ('chrome', 'Profile 2', None, None) (formato de yt-dlp)."""
    browser, _, profile = spec.partition(":")
    return (browser.strip().lower(), profile.strip() or None, None, None)


def cookie_methods(cfg: dict) -> List[Tuple[str, dict]]:
    """Formas de login disponibles, en el orden en que se intentan."""
    methods = []
    if cfg.get("browser"):
        methods.append((
            "cookies del navegador (%s)" % cfg["browser"],
            {"cookiesfrombrowser": parse_browser_spec(cfg["browser"])},
        ))
    if config.COOKIES_FILE.exists():
        config.secure_cookies_file()
        methods.append(("archivo cookies.txt", {"cookiefile": str(config.COOKIES_FILE)}))
    return methods


def _base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _SilentLogger(),
        "playlist_items": "1",  # si el post trae varios videos, solo el primero
        "retries": 2,
        "socket_timeout": 30,
    }


def _error_text(exc: BaseException) -> str:
    """Mensaje del error más el de su causa (yt-dlp a veces lo envuelve)."""
    parts = [str(exc)]
    if exc.__cause__ is not None:
        parts.append(str(exc.__cause__))
    return " | ".join(parts)


def _run(url: str, extra: dict, download: bool, dest: Optional[Path] = None) -> dict:
    """Una llamada a yt-dlp. Lanza la excepción original si falla."""
    import yt_dlp

    opts = _base_opts()
    opts.update(extra)
    if dest is not None:
        opts["outtmpl"] = str(dest / "video.%(ext)s")
        opts["merge_output_format"] = "mp4"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=download)
    # Un post con varios videos llega como "playlist": nos quedamos con el primero
    if info and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if entries:
            info = entries[0]
    return info or {}


def probe(url: str, extra: dict) -> Optional[ErrorInfo]:
    """Prueba (sin bajar el video) si un reel es accesible. None = funciona."""
    try:
        _run(url, extra, download=False)
        return None
    except Exception as exc:  # noqa: BLE001 - queremos traducir cualquier fallo
        return translate_error(_error_text(exc), used_cookies=bool(extra))


def download(url: str, dest: Path, cfg: dict,
             say: Callable[[str], None]) -> Tuple[dict, Path, str]:
    """Baja el reel a `dest`. Devuelve (metadata, ruta del video, método usado).

    Orden: 1) sin login, 2) cookies del navegador, 3) cookies.txt.
    Solo se pasa al siguiente intento si el problema es de login/cookies.
    """
    attempts = [("sin login", {})] + cookie_methods(cfg)
    last: Optional[ReelError] = None

    for label, extra in attempts:
        if extra:
            say("Instagram pide login → intento con %s" % label)
        try:
            info = _run(url, extra, download=True, dest=dest)
        except Exception as exc:  # noqa: BLE001
            raw = _error_text(exc)
            info_err = translate_error(raw, used_cookies=bool(extra))
            last = ReelError(info_err, raw)
            if info_err.kind in (LOGIN, COOKIES):
                continue  # probar el siguiente método de login
            raise last
        videos = [p for p in dest.glob("video.*") if p.suffix != ".part"]
        if not videos:
            raise ReelError(translate_error("no video formats found"), "sin archivo")
        return info, videos[0], label

    # Se acabaron los intentos. Si el último fallo fue leer cookies, el problema
    # de fondo sigue siendo el login.
    assert last is not None
    if last.info.kind == COOKIES and len(attempts) > 1:
        last.info.kind = LOGIN
    raise last
