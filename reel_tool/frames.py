"""Sacar frames del video con ffmpeg y armar el contact sheet."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Sequence, Tuple

MAX_FRAMES = 12
MIN_FRAMES = 8


def video_duration(video: Path) -> float:
    """Duración en segundos según ffprobe (0 si no se puede leer)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def detect_scenes(video: Path, threshold: float = 0.30) -> List[float]:
    """Segundos donde ffmpeg detecta un cambio de escena."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(video),
         "-vf", "scale=320:-2,select='gt(scene,%s)',showinfo" % threshold,
         "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", out.stderr)]


def pick_times(scene_times: Sequence[float], duration: float,
               max_frames: int = MAX_FRAMES, min_frames: int = MIN_FRAMES) -> List[float]:
    """Elige en qué segundos sacar frames.

    - Siempre uno al principio (el "gancho" del reel).
    - Uno por cada cambio de escena.
    - Si sobran, se reparten parejo hasta `max_frames`.
    - Si faltan, se completa con frames repartidos parejo hasta `min_frames`.
    """
    if duration <= 0:
        return [0.0]
    last = max(duration - 0.1, 0.0)
    gap = max(0.4, duration / (max_frames * 2.0))  # separación mínima entre frames
    times: List[float] = []

    def add(t: float) -> bool:
        t = round(min(max(t, 0.0), last), 2)
        if all(abs(t - x) >= gap for x in times):
            times.append(t)
            return True
        return False

    add(min(0.5, duration / 2.0))
    for t in sorted(scene_times):
        add(t + 0.1)  # un pelín después del corte, para no agarrar la transición
    times.sort()

    if len(times) > max_frames:
        # Demasiados cortes: nos quedamos con una muestra repartida pareja
        idx = sorted({round(i * (len(times) - 1) / (max_frames - 1))
                      for i in range(max_frames)})
        return [times[i] for i in idx]

    # Pocos cortes: rellenar los huecos más grandes con puntos de una rejilla pareja
    grid = [duration * (i + 0.5) / max_frames for i in range(max_frames)]
    while len(times) < min_frames:
        best = max(grid, key=lambda g: min(abs(g - x) for x in times))
        if not add(best):
            break  # el video es muy corto: ya no cabe otro frame distinto
    return sorted(times)


def extract_frames(video: Path, out_dir: Path, times: Sequence[float]) -> List[Tuple[float, Path]]:
    """Guarda un JPG por cada tiempo. Devuelve [(segundo, ruta)]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, t in enumerate(times, 1):
        path = out_dir / ("frame_%02d_%06.1fs.jpg" % (i, t))
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
             "-ss", "%.2f" % t, "-i", str(video), "-frames:v", "1",
             "-vf", "scale=720:-2", "-q:v", "3", str(path)],
            capture_output=True,
        )
        if path.exists() and path.stat().st_size > 0:
            frames.append((t, path))
    return frames


def make_contact_sheet(frames: Sequence[Tuple[float, Path]], out_path: Path,
                       cols: int = 4, thumb_w: int = 300) -> None:
    """Cuadrícula con todos los frames y su segundo marcado."""
    from PIL import Image, ImageDraw, ImageFont

    if not frames:
        return
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:  # Pillow viejo
        font = ImageFont.load_default()

    thumbs = []
    for t, path in frames:
        with Image.open(path) as img:
            img = img.convert("RGB")
            h = int(img.height * thumb_w / img.width)
            thumbs.append((t, img.resize((thumb_w, h))))

    pad = 8
    cell_h = max(th.height for _, th in thumbs)
    cols = min(cols, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new(
        "RGB",
        (cols * thumb_w + (cols + 1) * pad, rows * cell_h + (rows + 1) * pad),
        (20, 20, 20),
    )
    draw = ImageDraw.Draw(sheet)
    for i, (t, thumb) in enumerate(thumbs):
        x = pad + (i % cols) * (thumb_w + pad)
        y = pad + (i // cols) * (cell_h + pad)
        sheet.paste(thumb, (x, y))
        label = "#%d  %d:%04.1f" % (i + 1, int(t // 60), t % 60)
        box = draw.textbbox((x + 6, y + 4), label, font=font)
        draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill=(0, 0, 0))
        draw.text((x + 6, y + 4), label, fill=(255, 230, 0), font=font)
    sheet.save(out_path, quality=88)
