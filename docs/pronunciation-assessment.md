# Pronunciation assessment: what is measured, how, and what cannot be claimed

This is the most important document in the project. It exists because the easy
part of a pronunciation trainer is showing a number, and the hard part is making
that number mean something.

The rule that organizes everything below: **no claim about the learner's speech
without measured evidence behind it.** When the measurement does not exist, the
result says so instead of estimating.

---

## 1. The pipeline

```
                     ┌─ espeak-ng (es-419 | es) ──▶ expected phonemes ─┐
flashcard text ──────┤                                                 │
                     └─ ElevenLabs (cached) ──────▶ reference audio ───┤
                                                           │           │
                                                           ▼           ▼
                                                  reference profile (GOP + rhythm)
                                                                       │
learner recording ──▶ ffmpeg ──▶ 16 kHz PCM ──┬──▶ faster-whisper ──▶ words + timings
                                              │                        │
                                              └──▶ wav2vec2 CTC ──▶ per-phoneme GOP
                                                                       │
                                                                       ▼
                                                       relative comparison ──▶ result
```

| Stage | Where it runs | Cost |
|---|---|---|
| G2P (`espeak-ng`) | local | none |
| Reference audio (ElevenLabs) | **cloud** | credits, **once per card** |
| Decoding (`ffmpeg`) | local | none |
| Transcription (faster-whisper `small`) | local | CPU |
| Phonemes (wav2vec2 int8 ONNX) | local | CPU |

ElevenLabs is the only component that leaves the machine, and only the first
time each card is heard.

---

## 2. Why two models, and not Whisper alone

Transcription does not measure pronunciation. Whisper uses language context and
recovers the sentence even when the sounds came out wrong — it is trained for
exactly that. A score based only on the transcript measures *intelligibility*,
not pronunciation.

The second model answers a different question. Instead of "what sounds are
these?", it asks "does the audio support the sound /x/ **in this stretch**?".
That is the **GOP** (*Goodness of Pronunciation*): the expected sequence is
aligned to the audio by CTC *forced alignment* and the mean log-posterior of each
phoneme is read off.

The piece that makes this possible without a GPU: `espeak-ng` emits espeak
phoneme labels, and the `wav2vec2-lv-60-espeak-cv-ft` model **emits the same
labels**. Expected and recognized land in the same alphabet, so comparing is
measuring, not inferring.

Verified coverage: 397 phonemes generated from 75 words, across both variants —
**100% of the espeak-ng symbols exist in the model's 392-token vocabulary, none
unmapped.** Spanish uses 31–33 distinct phonemes.

---

## 3. Three results that changed the design

### 3.1 Free decoding does not work — it has to be restricted to Spanish

The model is multilingual over 392 symbols. Decoding freely, it reads Spanish as
if it were Mandarin:

```
expected: x  w  a  n  t  ɾ  a  x  o   ...     ("Juan trajo jamón…")
heard:    s. u5 w ɑ5 n t  l ɑ5 ɕ onɡ5 ...    ← phonemes carrying tone marks
```

Masking the logits down to the Spanish inventory before the `argmax` dropped the
PER from **85.7% to 46.4%** on the same audio. The mask is not an optimization:
without it the module does not work.

### 3.2 Synthetic speech is no good for calibration

The first round used audio from `espeak-ng` itself. Result: even *correct*
pronunciation scored 28–88% PER. `espeak-ng` is robotic formant synthesis, and
wav2vec2 was trained on human voice. Repeating with natural audio:

| phrase | synthetic → natural PER | natural GOP | accented GOP |
|---|---|---|---|
| Me gustaría aprender español | 28.0% → **8.0%** | −0.21 | −1.67 |
| El perro corre rápido… | 19.2% → **19.2%** | −0.18 | −5.12 |
| Juan trajo jamón… | 46.4% → **28.6%** | −0.70 | −3.71 |

With natural voice the GOP separates right from wrong consistently across all
three phrases; with synthetic voice it got the sign wrong in 2 of 5.

### 3.3 An absolute threshold flags errors in correct pronunciation

One serious problem remained: the ElevenLabs reference audio — correct by
construction — produced accusations like *"in 'aprender', the audio poorly
supports the sound /a/"*.

The causes are phonetic, not random:

- **Synalepha.** In `gustaría aprender` the two /a/ merge into a single vowel.
  That is correct Spanish; the expected /a/ has no independent acoustic support.
- **Intervocalic approximants.** /β ð ɣ/ are low-energy by nature.
- **Unstressed words.** The /d/ in `de` is weak even in a perfect reading.

Measured over 79 phonemes:

| criterion | false positives on the reference | detections on the accent |
|---|---|---|
| absolute −2.0 | 5/79 | 45/79 |
| absolute −2.5 | 1/79 | 42/79 |
| **relative, Δ < −2.0** | **0/79 by construction** | **45/79** |

**Decision: compare the learner against the reference of the same sentence,
sound by sound.** What is intrinsically weak is weak on both sides, the
difference stays near zero and does not become an error. Same detection
capability, zero false positives — and it absorbs synalepha, approximants and
unstressed words for free, with no special rule for each case.

The absolute threshold (−2.5, more conservative) only kicks in when there is no
reference.

---

## 4. Valid accent is not an error

Equivalences are applied before any comparison. They dropped the PER of correct
speech from 18.6% to 3.9%, leaving heavily accented speech practically untouched
(60.0% → 58.7%) — they suppress a representation artifact, not a real error.

| class | pairs | why |
|---|---|---|
| allophony | b~β, d~ð, ɡ~ɣ, n~ŋ | mandatory in Spanish |
| regional | s~θ, ʝ~ʎ, ʝ~j, s~h, x~h | seseo/distinción, yeísmo, aspiration |
| artifact | ɾ~r, x~k | measured limitation of the recognizer |

**The equivalence is non-transitive, on purpose.** `s~h` holds and `x~h` holds,
but chaining the two would make *casa* and *caja* indistinguishable. For the same
reason `n~ŋ` is in and `n~m` is out: *cama* and *cana* are a real minimal pair.

The /x/~/k/ confusion counts toward the score — otherwise every word with a jota
loses points — but **never becomes per-sound feedback**: in that direction there
is no way to separate the learner's error from the model's.

---

## 5. The formulas

All in `assessment/scoring.py`, pure and tested.

```
word_accuracy    = 1 − WER(expected, recognized)
                   lowercased words, no punctuation, no accents — but "ñ"
                   preserved, because "ano" and "año" are different words

phoneme_accuracy = 1 − PER(expected, heard)
                   after equivalences and geminate collapsing

fluency          = rhythm × pauses
                   rhythm = 1.0 between 0.75× and 1.30× of the reference,
                            falling off outside that
                   pauses = 1 − max(0, total_paused − 0.6s) / 3s
                   None when there is no reference or the card has 1 word

practice_score   = 100 × weighted mean of the available components
                   word 0.50 · phoneme 0.35 · fluency 0.15
                   a missing component is excluded and the weights renormalized
```

A practice score **is not a certification**. There is no mapping to CEFR. It is
there for the learner to compare attempts at the same card.

---

## 6. Measured performance (Intel Alder Lake-P, 12 threads, no GPU)

| stage | time |
|---|---|
| wav2vec2 int8 (2–3 s utterance) | **137–242 ms** (RTF ≈ 0.08) |
| faster-whisper `small` | ~2–4 s |
| reference profile | ~160 ms, once per card |

No PyTorch: ONNX Runtime (~50 MB) in place of a ~900 MB wheel.

---

## 7. Limitations — read before trusting the numbers

1. **The negative class was not validated on human speech.** The "accented"
   examples are synthesis in a Portuguese voice, not recordings of real learners.
   Detection capability is demonstrated against that stand-in, **not** against
   real human error. The thresholds should be recalibrated with real recordings.
2. **Small sample.** 79 phonemes, 3 phrases, one reference voice.
3. **/x/ vs /k/ is not reported** (section 4).
4. **Intonation only coarsely.** F0 comes from autocorrelation and supports only
   "rises / falls / flat" at the end of the utterance. Nothing finer is claimed.
5. **Without a reference, the analysis is more conservative** — absolute
   threshold, fewer detections.
6. **G2P runs word by word** and therefore does not see allophony across words
   (`días` in isolation gives /d/; in `buenos días` it sounds /ð/). The
   equivalence classes cover the case.
7. **The score measures what was measured.** With no acoustic model it comes only
   from words and rhythm, and the result declares that in `capabilities` and
   `limitations`.
