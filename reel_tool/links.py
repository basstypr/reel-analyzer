"""Leer links de reels y sacar su shortcode."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

# Acepta /reel/, /reels/, /p/ y /tv/, con o sin usuario delante.
_SHORTCODE_RE = re.compile(
    r"instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:reels?|p|tv)/([A-Za-z0-9_-]+)"
)


def extract_shortcode(link: str) -> Optional[str]:
    """Devuelve el shortcode del link (ej. 'DAbc123XyZ_') o None si no es un reel."""
    match = _SHORTCODE_RE.search(link or "")
    return match.group(1) if match else None


def canonical_link(shortcode: str) -> str:
    """Link limpio, sin parámetros de rastreo (?igsh=...)."""
    return "https://www.instagram.com/reel/%s/" % shortcode


def parse_links(lines: Iterable[str]) -> List[str]:
    """Limpia una lista de líneas: quita vacías, comentarios (#) y repetidos.

    Los repetidos se detectan por shortcode, así que el mismo reel con
    distinto ?igsh= cuenta como uno solo. Se respeta el orden original.
    """
    seen = set()
    result = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        link = line.split()[0]  # por si hay notas después del link
        key = extract_shortcode(link) or link
        if key in seen:
            continue
        seen.add(key)
        result.append(link)
    return result


def read_links_file(path: Path) -> List[str]:
    """Lee un .txt con un link por línea."""
    return parse_links(Path(path).read_text(encoding="utf-8").splitlines())
