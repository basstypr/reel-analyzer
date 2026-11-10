"""index.csv: una fila por reel con su estado."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

COLUMNS = ["#", "link", "autor", "duracion", "idioma", "estado"]


def read_rows(csv_path: Path) -> List[Dict[str, str]]:
    """Lee el CSV; si no existe devuelve lista vacía."""
    if not Path(csv_path).exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def upsert_row(csv_path: Path, link: str, autor: str = "", duracion: str = "",
               idioma: str = "", estado: str = "ok") -> int:
    """Agrega una fila, o actualiza la que ya exista para ese link.

    Devuelve el número (#) de la fila. Así, al reintentar un reel que había
    fallado, no quedan filas duplicadas.
    """
    csv_path = Path(csv_path)
    rows = read_rows(csv_path)
    nueva = {"link": link, "autor": autor, "duracion": duracion,
             "idioma": idioma, "estado": estado}

    for row in rows:
        if row.get("link") == link:
            row.update(nueva)
            numero = int(row["#"])
            break
    else:
        numero = max([int(r["#"]) for r in rows] or [0]) + 1
        rows.append(dict(nueva, **{"#": str(numero)}))

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return numero
