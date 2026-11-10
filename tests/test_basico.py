"""Pruebas básicas: links, shortcode, traducción de errores, CSV y selección de frames."""
from reel_tool import errors, index, links
from reel_tool.download import parse_browser_spec
from reel_tool.frames import pick_times
from reel_tool.ocr import merge_ocr
from reel_tool.transcribe import clean_segments


# ── shortcode ──

def test_shortcode_de_distintos_formatos():
    assert links.extract_shortcode("https://www.instagram.com/reels/DAbc123XyZ_/") == "DAbc123XyZ_"
    assert links.extract_shortcode("https://www.instagram.com/reel/Cabc-12_x/?igsh=xyz") == "Cabc-12_x"
    assert links.extract_shortcode("https://instagram.com/p/ABC123/") == "ABC123"
    assert links.extract_shortcode("https://www.instagram.com/usuario/reel/ABC123/") == "ABC123"


def test_shortcode_invalido():
    assert links.extract_shortcode("https://www.youtube.com/watch?v=abc") is None
    assert links.extract_shortcode("https://www.instagram.com/usuario/") is None
    assert links.extract_shortcode("") is None


# ── leer links ──

def test_parse_links_limpia_y_quita_repetidos():
    lineas = [
        "# mis reels",
        "",
        "  https://www.instagram.com/reel/AAA111/  ",
        "https://www.instagram.com/reels/AAA111/?igsh=otro",  # mismo reel
        "https://www.instagram.com/reel/BBB222/ nota al lado",
    ]
    assert links.parse_links(lineas) == [
        "https://www.instagram.com/reel/AAA111/",
        "https://www.instagram.com/reel/BBB222/",
    ]


def test_read_links_file(tmp_path):
    archivo = tmp_path / "links.txt"
    archivo.write_text("https://www.instagram.com/reel/AAA111/\n\n# x\n"
                       "https://www.instagram.com/reel/BBB222/\n", encoding="utf-8")
    assert len(links.read_links_file(archivo)) == 2


# ── traducir errores ──

AMBIGUO = ("ERROR: [Instagram] X: Requested content is not available, rate-limit "
           "reached or login required. Use --cookies-from-browser")


def test_error_login():
    assert errors.translate_error(AMBIGUO).kind == errors.LOGIN
    assert errors.translate_error("Instagram sent an empty media response").kind == errors.LOGIN
    assert "login" in errors.translate_error("login required").mensaje.lower()
    # Reel restringido por audiencia: sin login no se ve, hay que probar con cookies
    restringido = "This content isn't available to everyone: It can't be seen by certain audiences."
    assert errors.translate_error(restringido).kind == errors.LOGIN


def test_error_ambiguo_con_cookies_es_rate_limit():
    assert errors.translate_error(AMBIGUO, used_cookies=True).kind == errors.RATE_LIMIT


def test_error_rate_limit():
    info = errors.translate_error("HTTP Error 429: Too Many Requests")
    assert info.kind == errors.RATE_LIMIT
    assert errors.RATE_LIMIT in errors.STOP_RUN


def test_error_privado_o_borrado():
    assert errors.translate_error("HTTP Error 404: Not Found").kind == errors.NOT_FOUND
    assert errors.translate_error("This account is private").kind == errors.NOT_FOUND


def test_error_desactualizado():
    info = errors.translate_error("Unable to extract video url; please report this issue")
    assert info.kind == errors.OUTDATED
    assert "pip install -U yt-dlp" in info.paso


def test_error_cookies_y_red_y_desconocido():
    assert errors.translate_error("could not find firefox cookies database").kind == errors.COOKIES
    assert errors.translate_error("nodename nor servname provided").kind == errors.NETWORK
    assert errors.translate_error("algo rarísimo").kind == errors.UNKNOWN


# ── CSV ──

def test_csv_agrega_filas_numeradas(tmp_path):
    csv_path = tmp_path / "index.csv"
    assert index.upsert_row(csv_path, "link1", "ana", "30", "es", "ok") == 1
    assert index.upsert_row(csv_path, "link2", estado="error: Instagram pide login") == 2
    rows = index.read_rows(csv_path)
    assert list(rows[0].keys()) == index.COLUMNS
    assert rows[0]["autor"] == "ana" and rows[1]["estado"].startswith("error")


def test_csv_actualiza_en_vez_de_duplicar(tmp_path):
    csv_path = tmp_path / "index.csv"
    index.upsert_row(csv_path, "link1", estado="error: Instagram pide login")
    index.upsert_row(csv_path, "link2", "bob", "10", "en", "ok")
    assert index.upsert_row(csv_path, "link1", "ana", "30", "es", "ok") == 1
    rows = index.read_rows(csv_path)
    assert len(rows) == 2
    assert rows[0]["estado"] == "ok" and rows[0]["autor"] == "ana"


def test_csv_con_comas_y_saltos_en_los_datos(tmp_path):
    csv_path = tmp_path / "index.csv"
    index.upsert_row(csv_path, "link1", 'ana, "la mejor"', "30", "es", "ok")
    assert index.read_rows(csv_path)[0]["autor"] == 'ana, "la mejor"'


# ── frames ──

def test_frames_pocos_cortes_se_completa_parejo():
    times = pick_times([10.0], duration=60.0)
    assert len(times) == 8
    assert times == sorted(times) and times[-1] < 60


def test_frames_muchos_cortes_se_limita_a_12():
    times = pick_times([i * 1.5 for i in range(1, 40)], duration=60.0)
    assert len(times) == 12


def test_frames_video_muy_corto_no_se_cuelga():
    times = pick_times([], duration=1.5)
    assert 1 <= len(times) <= 8


# ── OCR y navegador ──

def test_ocr_junta_texto_repetido():
    merged = merge_ocr([
        (0.5, ["3 errores al invertir"]),
        (2.0, ["3 errores al invertir", "Error #1"]),
        (4.0, ["3 errores al invertlr"]),  # mismo cartel con un error del OCR
    ])
    assert merged == [(0.5, ["3 errores al invertir"]), (2.0, ["Error #1"])]


def test_parse_browser_spec():
    assert parse_browser_spec("firefox") == ("firefox", None, None, None)
    assert parse_browser_spec("chrome:Profile 2") == ("chrome", "Profile 2", None, None)


# ── transcripción ──

def test_whisper_descarta_texto_inventado():
    base = {"start": 0.0, "end": 2.0, "no_speech_prob": 0.01,
            "avg_logprob": -0.3, "compression_ratio": 1.2}
    segmentos = [
        dict(base, text=" Hola, hoy les cuento algo."),          # voz real
        dict(base, text=" 1", avg_logprob=-1.84, compression_ratio=5.8),  # música
        dict(base, text=" ruido", no_speech_prob=0.9),            # silencio
        dict(base, text=" Thanks for watching!"),                 # relleno típico
    ]
    assert [s["text"] for s in clean_segments(segmentos)] == ["Hola, hoy les cuento algo."]
