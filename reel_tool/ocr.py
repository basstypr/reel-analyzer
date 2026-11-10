"""Leer el texto en pantalla de cada frame (OCR local).

Primero Apple Vision (paquete ocrmac); si no funciona, tesseract.
"""
from __future__ import annotations

import difflib
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


def available_engine() -> Optional[str]:
    """'vision', 'tesseract' o None si no hay ningún OCR."""
    try:
        from ocrmac import ocrmac  # noqa: F401
        return "vision"
    except Exception:  # noqa: BLE001
        pass
    return "tesseract" if shutil.which("tesseract") else None


def _ocr_vision(path: Path) -> List[str]:
    from ocrmac import ocrmac

    results = ocrmac.OCR(str(path), language_preference=["es-ES", "en-US"]).recognize()
    # Cada resultado es (texto, confianza, caja). Descartamos lo muy dudoso.
    return [text.strip() for text, conf, _ in results if conf >= 0.3 and text.strip()]


def _ocr_tesseract(path: Path) -> List[str]:
    out = subprocess.run(
        ["tesseract", str(path), "-", "-l", "spa+eng"], capture_output=True, text=True
    )
    if out.returncode != 0:  # puede faltar el idioma español: probar solo inglés
        out = subprocess.run(["tesseract", str(path), "-"], capture_output=True, text=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def read_frame(path: Path) -> List[str]:
    """Líneas de texto de un frame. Vision primero, tesseract de respaldo."""
    try:
        return _ocr_vision(path)
    except Exception:  # noqa: BLE001
        if shutil.which("tesseract"):
            return _ocr_tesseract(path)
        raise


def _normalize(line: str) -> str:
    """Para comparar: minúsculas y sin signos ni espacios de más."""
    return re.sub(r"[\W_]+", " ", line.casefold()).strip()


def merge_ocr(frames: Sequence[Tuple[float, List[str]]]) -> List[Tuple[float, List[str]]]:
    """Junta el texto repetido entre frames.

    Un mismo cartel suele salir en varios frames seguidos; cada línea se deja
    solo la primera vez que aparece (comparación tolerante a pequeños errores
    del OCR). Devuelve [(segundo, líneas nuevas)] solo para frames con algo nuevo.
    """
    seen: List[str] = []
    merged = []
    for t, lines in frames:
        new = []
        for line in lines:
            norm = _normalize(line)
            if len(norm) < 2:
                continue
            if any(norm == s or difflib.SequenceMatcher(None, norm, s).ratio() >= 0.85
                   for s in seen):
                continue
            seen.append(norm)
            new.append(line)
        if new:
            merged.append((t, new))
    return merged


def format_ocr(merged: Sequence[Tuple[float, List[str]]]) -> str:
    """Texto de onscreen_text.txt."""
    if not merged:
        return "(no se detectó texto en pantalla)\n"
    blocks = []
    for t, lines in merged:
        blocks.append("[%d:%02d]\n%s" % (int(t // 60), int(t % 60), "\n".join(lines)))
    return "\n\n".join(blocks) + "\n"
