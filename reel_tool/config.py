"""Rutas del proyecto y configuración guardada en config.json.

Aquí NUNCA se guardan usuario ni contraseña de Instagram: solo de qué
navegador/perfil sacar las cookies.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

# Carpeta del proyecto (donde clonaste el repositorio)
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
INDEX_CSV = OUTPUT / "index.csv"
CONFIG_FILE = ROOT / "config.json"
COOKIES_FILE = ROOT / "cookies.txt"

DEFAULTS = {
    # Ejemplos: "firefox", "chrome:Profile 2", "firefox:abcd1234.default-release"
    "browser": None,
    # Reel público que usa `reel doctor` para probar el login. Se guarda la
    # primera vez que corres `reel doctor <link>`.
    "reel_de_prueba": None,
}


def load_config() -> dict:
    """Lee config.json; si no existe o está roto, devuelve los valores por defecto."""
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def secure_cookies_file() -> None:
    """Deja cookies.txt con permisos solo para el dueño (600)."""
    if COOKIES_FILE.exists():
        os.chmod(COOKIES_FILE, 0o600)


def install_cookies_file(source: Path) -> None:
    """Copia un cookies.txt exportado al proyecto, con permisos 600."""
    shutil.copyfile(source, COOKIES_FILE)
    secure_cookies_file()
