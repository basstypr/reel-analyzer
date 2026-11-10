"""Transcripción local con Whisper.

Apple Silicon -> mlx-whisper (large-v3-turbo). Intel -> faster-whisper (small).
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Dict, List

# Tamaño aproximado de descarga de cada modelo (para avisar antes de bajarlo)
MODEL_SIZES = {
    "tiny": "75 MB", "base": "150 MB", "small": "500 MB", "medium": "1.5 GB",
    "large-v3": "3 GB", "large-v3-turbo": "1.6 GB",
}


def backend() -> str:
    """'mlx' en Apple Silicon, 'faster' en Intel."""
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mlx"
    return "faster"


def default_model() -> str:
    return "large-v3-turbo" if backend() == "mlx" else "small"


def resolve_repo(model: str) -> str:
    """Nombre corto del modelo -> repositorio de Hugging Face de donde se baja."""
    if "/" in model:
        return model  # ya es un repositorio completo
    if backend() == "mlx":
        if model == "large-v3-turbo":
            return "mlx-community/whisper-large-v3-turbo"
        return "mlx-community/whisper-%s-mlx" % model
    return "Systran/faster-whisper-%s" % model


def model_cached(model: str) -> bool:
    """¿El modelo ya está bajado en el caché de Hugging Face?"""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except Exception:  # noqa: BLE001
        HF_HUB_CACHE = str(Path.home() / ".cache/huggingface/hub")
    folder = Path(HF_HUB_CACHE) / ("models--" + resolve_repo(model).replace("/", "--"))
    return folder.exists() and any(folder.glob("snapshots/*/*"))


def has_audio(video: Path) -> bool:
    """¿El video tiene pista de audio?"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return "audio" in out.stdout


# Frases que Whisper suele inventar cuando solo hay música o silencio
_FRASES_INVENTADAS = (
    "amara.org", "thanks for watching", "thank you for watching",
    "gracias por ver", "suscríbete", "subscribe to",
)


def clean_segments(segments: List[Dict]) -> List[Dict]:
    """Quita los segmentos que Whisper inventó (música o silencio, sin voz).

    Señales de texto inventado, según las métricas que da el propio Whisper:
    - avg_logprob muy bajo: el modelo no está nada seguro de lo que "oyó";
    - compression_ratio alto: texto muy repetitivo ("1 1 1 1…");
    - no_speech_prob alto: el modelo cree que ahí no hay voz;
    - frases típicas de relleno ("Thanks for watching", "Amara.org"…).
    """
    limpios = []
    for seg in segments:
        texto = seg.get("text", "").strip()
        if not texto:
            continue
        if seg.get("avg_logprob", 0.0) < -1.0:
            continue
        if seg.get("compression_ratio", 0.0) > 2.4:
            continue
        if seg.get("no_speech_prob", 0.0) > 0.6:
            continue
        if any(f in texto.casefold() for f in _FRASES_INVENTADAS):
            continue
        limpios.append({"start": seg["start"], "end": seg["end"], "text": texto})
    return limpios


def _resultado(segments: List[Dict], language: str) -> Dict:
    """Arma el resultado final a partir de los segmentos ya filtrados."""
    limpios = clean_segments(segments)
    if not limpios:  # sin voz real: tampoco hay idioma confiable
        return {"text": "", "language": "", "segments": []}
    return {"text": " ".join(s["text"] for s in limpios),
            "language": language, "segments": limpios}


def transcribe(video: Path, model: str) -> Dict:
    """Transcribe el audio. Devuelve {'text', 'language', 'segments'}.

    El idioma se detecta solo (no se fuerza), para que funcione con español,
    inglés o spanglish.
    """
    if not has_audio(video):
        return {"text": "", "language": "", "segments": []}

    if backend() == "mlx":
        import mlx_whisper

        result = mlx_whisper.transcribe(
            str(video),
            path_or_hf_repo=resolve_repo(model),
            verbose=None,
            # Evita que un error se arrastre y se repita en bucle
            condition_on_previous_text=False,
        )
        return _resultado(result.get("segments", []), result.get("language", ""))

    # Intel: faster-whisper en CPU
    from faster_whisper import WhisperModel

    wm = WhisperModel(model, device="cpu", compute_type="int8")
    segs, info = wm.transcribe(str(video), condition_on_previous_text=False)
    segments = [{"start": s.start, "end": s.end, "text": s.text,
                 "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob,
                 "compression_ratio": s.compression_ratio} for s in segs]
    return _resultado(segments, info.language)


def fmt_time(seconds: float) -> str:
    """83.4 -> '1:23'"""
    seconds = int(seconds)
    return "%d:%02d" % (seconds // 60, seconds % 60)


def format_transcript(result: Dict) -> str:
    """Texto de transcript.txt: primero todo corrido, luego con tiempos."""
    if not result["text"]:
        return "(sin voz detectada o el reel no tiene audio)\n"
    lines = [result["text"], "", "--- Con tiempos ---"]
    for seg in result["segments"]:
        if seg["text"]:
            lines.append("[%s] %s" % (fmt_time(seg["start"]), seg["text"]))
    return "\n".join(lines) + "\n"
