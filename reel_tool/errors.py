"""Traduce los errores crudos de yt-dlp a mensajes claros en español."""
from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass

# Tipos de error
LOGIN = "login"            # Instagram pide login
RATE_LIMIT = "rate_limit"  # demasiadas descargas
NOT_FOUND = "not_found"    # privado o borrado
OUTDATED = "outdated"      # yt-dlp desactualizado
COOKIES = "cookies"        # no se pudieron leer las cookies del navegador
NETWORK = "network"        # sin internet
NOT_VIDEO = "not_video"    # el post no tiene video
UNKNOWN = "unknown"

# Errores que hacen parar toda la corrida (seguir intentando solo empeora las cosas)
STOP_RUN = {RATE_LIMIT, LOGIN}

# Comando para actualizar yt-dlp con el mismo Python que corre el programa
PIP_UPDATE = "%s -m pip install -U yt-dlp" % shlex.quote(sys.executable)


@dataclass
class ErrorInfo:
    kind: str     # uno de los tipos de arriba
    mensaje: str  # qué pasó, en claro
    paso: str     # qué hacer ahora


class ReelError(Exception):
    """Error ya traducido, listo para mostrar."""

    def __init__(self, info: ErrorInfo, detalle: str = ""):
        super().__init__(info.mensaje)
        self.info = info
        self.detalle = detalle


def _has(text: str, *needles: str) -> bool:
    return any(n in text for n in needles)


def translate_error(raw: str, used_cookies: bool = False) -> ErrorInfo:
    """Clasifica un mensaje de error de yt-dlp.

    `used_cookies` indica si el intento ya iba con login: el mismo mensaje de
    Instagram ("rate-limit reached or login required") significa cosas
    distintas según el caso.
    """
    t = (raw or "").lower()

    # 1) No se pudieron LEER las cookies (antes de hablar con Instagram)
    if _has(t, "cookies database", "failed to decrypt", "could not copy",
            "database is locked", "failed to load cookies", "unsupported browser",
            "could not find", "operation not permitted", "permission denied",
            "keyring", "keychain"):
        return ErrorInfo(
            COOKIES,
            "No pude leer las cookies del navegador configurado",
            "Cierra ese navegador por completo (Cmd+Q) y vuelve a intentar. "
            "Si sigue igual, corre: reel doctor",
        )

    # 2) Demasiadas descargas (claro)
    if _has(t, "429", "too many requests", "wait a few minutes", "try again later"):
        return ErrorInfo(
            RATE_LIMIT,
            "Demasiadas descargas: Instagram te está frenando",
            "Espera un buen rato (mínimo 1 hora) antes de volver a intentar.",
        )

    # 3) Mensaje ambiguo de Instagram: "rate-limit reached or login required"
    if "rate-limit" in t or "rate limit" in t:
        if used_cookies:
            return ErrorInfo(
                RATE_LIMIT,
                "Instagram bloqueó la descarga aun con login "
                "(demasiadas descargas o la sesión venció)",
                "Espera 1 hora. Si sigue fallando, abre Instagram en el perfil "
                "configurado, revisa que la cuenta secundaria siga logueada y "
                "corre: reel doctor",
            )
        return ErrorInfo(
            LOGIN,
            "Instagram pide login",
            "Configura las cookies de tu cuenta secundaria: reel doctor",
        )

    # 4) Pide login (incluye reels restringidos por edad/audiencia, que
    #    Instagram solo muestra a cuentas logueadas)
    if _has(t, "login required", "login_required", "log in", "logged-in",
            "logged in", "empty media response", "use --cookies",
            "checkpoint", "challenge", "available to everyone",
            "certain audiences", "age-restricted", "restricted video"):
        if used_cookies:
            return ErrorInfo(
                LOGIN,
                "Instagram pide login y las cookies configuradas no sirvieron "
                "(sesión cerrada o vencida)",
                "Abre Instagram en ese perfil, entra con la cuenta secundaria, "
                "cierra el navegador y corre: reel doctor",
            )
        return ErrorInfo(
            LOGIN,
            "Instagram pide login",
            "Configura las cookies de tu cuenta secundaria: reel doctor",
        )

    # 5) El post no es un video
    if _has(t, "no video formats", "no video in this post", "there is no video"):
        return ErrorInfo(
            NOT_VIDEO,
            "Ese link no tiene video (parece una foto o carrusel de fotos)",
            "Quítalo de la lista; el programa solo analiza reels/videos.",
        )

    # 6) Privado o borrado
    if _has(t, "private", "404", "not found", "does not exist", "removed",
            "unavailable", "not available"):
        return ErrorInfo(
            NOT_FOUND,
            "El reel es privado o lo borraron",
            "Abre el link en el navegador para confirmar. Si es de una cuenta "
            "privada, la cuenta secundaria tiene que seguirla.",
        )

    # 7) yt-dlp roto por cambios de Instagram
    if _has(t, "unable to extract", "unsupported url", "latest version",
            "update yt-dlp", "please report this issue", "keyerror", "jsondecodeerror"):
        return ErrorInfo(
            OUTDATED,
            "yt-dlp está desactualizado (Instagram cambió algo)",
            "Actualízalo: " + PIP_UPDATE,
        )

    # 8) Internet
    if _has(t, "getaddrinfo", "name resolution", "nodename nor servname",
            "timed out", "connection reset", "network is unreachable",
            "connection refused", "ssl"):
        return ErrorInfo(
            NETWORK,
            "Problema de conexión a internet",
            "Revisa tu internet y vuelve a intentar.",
        )

    return ErrorInfo(
        UNKNOWN,
        "Error que no reconozco",
        "Corre `reel doctor`. Si todo sale bien ahí, actualiza yt-dlp: " + PIP_UPDATE,
    )
