# reel-analyzer

Analyze Instagram reels **on your own Mac, for free, with no external services**.
No paid APIs, no cloud: everything runs locally.

For each reel you get:

- **Metadata**: author, caption, duration, date
- **Transcript** of the audio (local Whisper, language auto-detected)
- **On-screen text** (OCR with Apple Vision), with repeats merged
- **Frames** (up to 12, picked by scene changes) and a **contact sheet** image

It's handy for studying formats, hooks and trends across many reels without
watching each one ten times.

> 🇪🇸 [Léeme en español](README.es.md). The command-line messages are in Spanish.

## Requirements

- macOS (Apple Silicon recommended; Intel works with a smaller Whisper model)
- Python 3.9+
- ffmpeg: `brew install ffmpeg`

## Install

```bash
git clone https://github.com/basstypr/reel-analyzer.git
cd reel-analyzer
./install.sh
reel doctor
```

`install.sh` creates a virtual environment inside the folder, installs the
Python dependencies and links the `reel` command into `~/.local/bin`. It does
not install anything system-wide.

The first transcription downloads the Whisper model (~1.6 GB on Apple Silicon,
~500 MB on Intel). The tool asks before downloading.

## Usage

```bash
reel https://www.instagram.com/reel/XXXXXXXXXXX/    # one reel
reel --file links.txt                               # many (one link per line)
reel doctor                                         # check that everything works
```

| Option | What it does |
|---|---|
| `--force` | Redo a reel that was already processed |
| `--keep-video` | Keep the video file (deleted by default) |
| `--max 60` | Allow more than 40 reels in one run |
| `--model small` | Use a different Whisper model |
| `--yes` | Accept the model download without asking |

Results go to `output/<shortcode>/`:

| File | Contents |
|---|---|
| `metadata.json` | link, author, caption, duration, date, language |
| `transcript.txt` | what is said (plain text, then with timestamps) |
| `onscreen_text.txt` | text shown on screen, deduplicated |
| `frames/` and `contact_sheet.jpg` | up to 12 frames and a grid with their timestamps |

`output/index.csv` has one row per reel with its status (`ok` or `error: …`).

Between reels the tool waits 8–20 seconds, and if Instagram answers "too many
requests" the run stops by itself. Reels already done are skipped, so you can
re-run the same command to continue.

## Login (only if Instagram asks for it)

Most public reels download without login. When Instagram does ask, the tool
reads the cookies of a browser where you are already logged in.
**It never asks for your username or password and never stores them.**

Use a **secondary account** in a separate browser or profile (a Firefox used
only for this is the easiest).

1. Open that browser, log in to instagram.com with the secondary account.
2. **Quit the browser completely (Cmd+Q).**
3. `reel doctor`: step 6 lists your browser profiles with the exact command.
4. `reel config --browser "firefox"` (or what the doctor suggests, e.g. `"chrome:Profile 2"`).
5. `reel doctor <link to any public reel>`: step 7 should say "Login funciona".

Plan B: export a `cookies.txt` (Netscape format) with a browser extension and
run `reel config --cookies-file ~/Downloads/cookies.txt`. It is copied into the
project readable only by you, and it is git-ignored.

## Privacy

- Nothing leaves your Mac except the requests to Instagram to download each
  reel, and the one-time model download from Hugging Face.
- `config.json`, `cookies.txt`, `links.txt` and `output/` are git-ignored.
- Cookie contents are never printed.

## Use responsibly

This tool is for personal analysis of publicly available content. You are
responsible for complying with Instagram's Terms of Use and with copyright law.
Do not republish other people's content, keep the volume low, and use a
secondary account. This project is not affiliated with Instagram or Meta.

## Tests

```bash
.venv/bin/python -m pytest
```

## License

[MIT](LICENSE)
