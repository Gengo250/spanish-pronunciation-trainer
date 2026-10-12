# Pronunciation Trainer · Spanish

A local Spanish study app built around flashcards, reference audio and
**acoustic pronunciation assessment** — not just transcription.

The interface is entirely in English; the material studied is Spanish. The
separation is deliberate and the code holds it up: every piece of interface text
lives in `frontend/src/i18n/en.ts`, and the typography reinforces it — serif only
for Spanish, sans only for the interface, mono only for measurements.

It runs on modest hardware: all speech analysis happens on the CPU, no GPU and no
PyTorch. The only outbound call is synthesizing the reference audio, once per
card.

```
flashcard ──▶ hear the reference ──▶ record ──▶ sound-by-sound feedback ──▶ repeat
```

---

## What it actually measures

Most trainers compare the transcript against the expected text. That measures
intelligibility: Whisper uses language context and recovers the sentence even
when the sounds came out wrong.

Here there is a second measure. `espeak-ng` produces the expected phonemes and a
wav2vec2 model asks, for each one, **whether the audio supports that sound in
that stretch** (GOP, via CTC forced alignment). Both components use the same
phoneme alphabet, so the comparison is a measurement and not an inference.

There is no language model anywhere along the path: every piece of text the
learner reads comes from a measurement or from hand-written content.

Every observation on screen carries a label for the evidence behind it —
`transcript`, `sound` or `rhythm`. When acoustic analysis is unavailable, the app
**says so** rather than producing conclusions about sounds.

The full reasoning, with the measured numbers and the limitations, is in
[`docs/pronunciation-assessment.md`](docs/pronunciation-assessment.md). Worth
reading before trusting any score.

---

## Requirements

| Component | Version | Note |
|---|---|---|
| Python | ≥ 3.12 | via `uv` |
| Node.js | ≥ 20.19 | npm 12's version warning is cosmetic |
| `ffmpeg` | any | decodes the browser's audio |
| `espeak-ng` | any | **required** — generates the reference phonemes |
| ElevenLabs account | free tier is enough | 10k characters/month suffice, thanks to the cache |

```bash
# Arch
sudo pacman -S espeak-ng ffmpeg
# Debian/Ubuntu
sudo apt install espeak-ng ffmpeg
```

## Install

```bash
cp .env.example .env
$EDITOR .env          # fill in ELEVENLABS_API_KEY
chmod 600 .env

cd backend  && uv sync
cd ../frontend && npm install
```

## Running

The app is two processes: the API on `:8000` and the interface on `:5173`.
`run.sh` starts both.

```bash
./run.sh          # foreground — Ctrl+C brings both down
./run.sh --bg     # background — survives closing the terminal
./run.sh --stop   # stops whatever --bg started
./run.sh --status # what is up
./run.sh --logs   # follow the logs from --bg mode
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend.

**Foreground dies with the terminal.** `uv run uvicorn` and `npm run dev` are
tied to the window: close it and both get SIGHUP and go down. `--bg` puts each
server in its own session (`setsid`), out of that signal's reach — you can close
the terminal, or even log out, and they keep running.

PIDs and logs live in `.run/` (not versioned). If you prefer to start them by
hand, without the script:

```bash
# terminal 1
cd backend && uv run uvicorn sptrainer.api.app:app --reload --port 8000
# terminal 2
cd frontend && npm run dev
```

On the first recording, faster-whisper and the phoneme model are downloaded and
loaded — that attempt takes longer; the following ones do not.

## Tests

```bash
cd backend
uv run pytest                      # full suite, no external service touched
uv run pytest -m "not integration" # explicit
uv run ruff check src tests

cd ../frontend
npm test            # interface logic: the copy shown to the learner
npm run typecheck
```

ElevenLabs is stubbed in every automated test: **running the suite consumes no
credits.**

---

## ElevenLabs cost

The free account gives 10k characters/month (20k on the flash/turbo models). A
card is 10–40 characters.

Three decisions keep usage low:

1. **Content-addressed cache.** Each combination (text, voice, model, format) is
   synthesized exactly once. Responses carry `X-Cache` and
   `X-Characters-Billed`.
2. **Slow playback in the browser.** 0.75× and 0.5× come from `playbackRate`, no
   new audio requested.
3. **`preload="none"`.** Flipping through cards downloads no audio; only the
   *Listen* button does.

To double the quota, switch to the cheaper model in `.env`:

```ini
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
```

---

## Content

95 starter cards across three levels, eight types (vocabulary, phrase, question,
expression, verb, pronunciation, intonation) and fifteen themes.

The levels are **defined by the app** and do not map to CEFR.

```bash
curl 'localhost:8000/api/content/export?fmt=csv' -o deck.csv
curl -F 'file=@deck.csv' localhost:8000/api/content/validate
```

The validator checks for repeated ids, duplicate text, length per level, Spanish
question punctuation (`¿…?`), characters outside the Spanish alphabet, and
whether the target phonemes actually appear in the pronunciation.
Model-generated translations and grammar notes are **not** assumed correct — the
starter dataset was written by hand, and the expected phonemes always come from
`espeak-ng`.

---

## Configuration

Everything in `.env` (see `.env.example`). The most useful ones:

| Variable | Default | What for |
|---|---|---|
| `SPANISH_ACCENT` | `es-419` | `es-419` Latin American, `es` peninsular |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | `eleven_flash_v2_5` costs half |
| `WHISPER_MODEL` | `small` | `base` is faster, `medium` more accurate |
| `PHONEME_ASSESSMENT_ENABLED` | `1` | `0` turns off per-sound analysis |

The accent genuinely changes the reference: `gracias` is `ɡɾasjas` in `es-419`
and `ɡɾaθjas` in `es`. Both variants are accepted — seseo and distinción do not
count as errors.

---

## Trade-offs taken

- **Pronunciation accuracy.** Detection was validated against accented synthetic
  speech, not against recordings of real learners. The thresholds are
  conservative and should be recalibrated with real audio. See
  `docs/pronunciation-assessment.md` §7.
- **Performance.** `small` + int8 instead of larger models: ~137–242 ms per
  utterance for phoneme analysis, ~2–4 s for transcription, on a CPU with no GPU.
- **Cost.** Reference audio comes from the cloud because local synthetic speech
  good enough to serve as a pronunciation model does not fit this hardware
  budget. The cache holds that down to one call per card.
- **No LLM.** A local 4B model was evaluated and removed: it added no fact to the
  feedback and got phonetics and grammar wrong. See `docs/architecture.md` for
  the measurements behind that decision.
- **The scores serve the study.** They do not certify proficiency.

## Model licenses

`wav2vec2-lv-60-espeak-cv-ft` and the int8 ONNX build: Apache-2.0.
`faster-whisper`: MIT. `espeak-ng`: GPLv3 (used as an external process).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — modules, boundaries, degradation
- [`docs/pronunciation-assessment.md`](docs/pronunciation-assessment.md) — measurements, formulas, limitations
