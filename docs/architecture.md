# Architecture

## Principle

Ten modules with explicit boundaries. What matters most: **transcription,
pronunciation assessment and LLM know nothing about each other**. Each can be
swapped without touching the others, and two of the three can fail without
taking the lesson down.

```
backend/src/sptrainer/
├── config.py          environment configuration; secrets never reach repr()
├── content/           model, JSON/CSV, validation, starter dataset
├── scheduling/        filters, draw, anti-repetition
├── audio/             browser decoding, signal utilities
├── stt/               faster-whisper + per-word timestamps
├── assessment/        ← the core
│   ├── g2p.py         espeak-ng → expected phonemes
│   ├── phonemes.py    wav2vec2 ONNX → heard phonemes + GOP
│   ├── align.py       Needleman-Wunsch alignment
│   ├── accents.py     accent equivalences (non-transitive)
│   ├── prosody.py     rhythm, pauses, F0
│   ├── scoring.py     pure formulas
│   ├── summary.py     feedback sentence, deterministic
│   └── pipeline.py    orchestrates and decides what may be asserted
├── tts/               ElevenLabs + cache + reference profile
├── progress/          SQLite
└── api/               FastAPI
```

## Local vs. cloud

| Component | Where | Note |
|---|---|---|
| G2P, decoding, transcription, phonemes, prosody, scores, summary | **local** | works offline |
| Reference audio (ElevenLabs) | **cloud** | one call per card, cached afterwards |

## The contract that holds the honesty up

`AssessmentResult` carries `capabilities` and `limitations`, and **every
observation names its evidence** (`transcript`, `phoneme_acoustic`, `prosody`).
If the acoustic model is disabled, missing or fails:

- `PHONEME_ANALYSIS` does not enter `capabilities`;
- no phoneme observation is produced;
- `phoneme_accuracy` is `None` and the score weights are renormalized;
- the limitation shows up as text, on screen.

Nothing is estimated to fill the gap.

## Degradation

| Failure | Consequence |
|---|---|
| No `ELEVENLABS_API_KEY` | cards and recording work; new audio → 503 |
| ElevenLabs quota exhausted | already-cached cards keep playing |
| Phoneme model missing | assessment falls back to transcript + prosody, and declares it |
| `ffmpeg` missing | clear error on recording |
| Silent recording | `no_speech_detected`, **not** a zero score |

## Reuse from the prototype

| Origin (`voice-assistant`) | Destination |
|---|---|
| `ollama_service.py` | not reused — the trainer uses no LLM |
| `speech.py` | `tts/elevenlabs_client.py` — synthesis + error translation; `play_bytes` dropped |
| `transcription.py` | `stt/whisper.py` — `es` + per-word timestamps |
| `audio_input.py` | `audio/utils.py` — only the numpy/wave parts |
| `config.py` | `config.py` — same pattern |
| `llm.py`, `main.py` | not reused (voice conversation loop) |

The microphone and playback left Python and went to the browser: the backend
opens no audio device.

## Decisions and their reasons

1. **ONNX Runtime, not PyTorch.** ~50 MB against ~900 MB; 137–242 ms per utterance on CPU.
2. **GOP relative to the card's own reference.** Zero false positives against
   5/79 from the absolute threshold. See `pronunciation-assessment.md` §3.3.
3. **No LLM.** Evaluated and removed: it added no fact to the feedback and got
   phonetics and grammar wrong. See "Why there is no LLM".
4. **Recording in the browser.** Takes the microphone out of the Python process
   and makes the interface work on any machine.
5. **SQLite with one row per attempt.** Statistics are a query, not a column; no
   new report requires a migration. **Audio is never stored.**
6. **Phonetic equivalence without transitive closure.** Keeps `s~h` + `x~h` from
   making *casa* and *caja* identical.

## Why there is no LLM

A local `qwen3:4b-instruct` was integrated at one point (vocabulary and grammar
explanations, plus an attempt summary rewritten by the model) and then **removed
entirely**. The record of the evaluation stays here because the conclusion is
reusable.

### What was measured on this machine (CPU, no GPU)

| task | `qwen3:4b-instruct` | `qwen3:4b` |
|---|---|---|
| vocabulary explanation | 10.1 s | 27.2 s (hit the token ceiling) |
| grammar explanation | 10.9 s | 20.9 s (same) |
| attempt summary | 7–15 s | — |

### Why it did not pay off

1. **The summary added no information.** To keep it from inventing a diagnosis,
   the model had to be pinned to a closed list of facts, checked by a verifier.
   Pinned that way, it only rewrote what the deterministic summary already said
   — in 15 s instead of 4 s.

2. **The explanations were wrong.** Verified: it said `llave` "is pronounced
   ah-veh" (it is *ya-ve*), called `hubiera tenido` a "past conditional" (it is
   the pluperfect subjunctive) and claimed `rojo` is a false friend of
   Portuguese (it is not). It had to be forbidden from discussing pronunciation
   and every piece of its text stamped as generated — that is, the feature came
   with a disclaimer admitting it could not be trusted.

3. **The cost was real.** 2.5 GB on disk, ~3 GB of RAM once loaded, and the
   service started itself in the background (`OLLAMA_AUTOSTART=1`) whenever
   someone asked for an explanation.

Pronunciation always came from `espeak-ng`, deterministic; the diagnosis always
came from the acoustic measurement. The language model took part in neither.
Removing it cost no core functionality.

What took its place: `assessment/summary.py`, a pure function that assembles the
feedback sentence from the measured observations — instant, and unable to cite
anything that was not measured.

**Where an LLM would still make sense:** generating flashcards in bulk, offline,
passing through the content validator and human review before entering the deck.
There the latency does not matter and the errors are filtered before reaching the
learner. Not implemented.

## Adaptive selection (SRS-lite)

`Order.ADAPTIVE` reweights the draw by each card's best score:

| situation | weight |
|---|---|
| never practised | 2.0 |
| practised, below 80 | 1.0 + 3.0 × (how much is missing) |
| mastered (≥ 80) | 0.3 |

A card scoring 0 weighs 4.0 — roughly thirteen times a mastered one. The unseen
card sits above an "average" card on purpose: new material is worth more than
drilling what already comes out reasonably.

Real spaced repetition schedules by date. This is deliberately simpler and
without temporal state, so it does not force a migration later. The
anti-repetition window still applies and takes precedence over the weight.
