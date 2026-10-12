"""Acoustic phoneme recognition (wav2vec2 CTC, int8 ONNX).

This is the module that lets us talk about *sounds*, and not only about
recognized words. It does two distinct things with the same set of logits:

1. **Restricted decoding** -- which phoneme sequence the audio contains.
   The model is multilingual (392 symbols, several languages). Decoding freely,
   it literally reads Spanish as Mandarin: the M0 spike produced
   `s. u5 ɑ5 onɡ5 ɕ ts.` for "Juan trajo jamon". Restricting the logits to the
   Spanish inventory before the argmax dropped the PER from 85.7% to 46.4% on
   the same audio. That is why the mask is not an optimization detail: without
   it the module does not work.

2. **GOP (Goodness of Pronunciation)** -- how well the audio supports each
   *expected* phoneme. Here the question is not "what sounds are these?" but
   "does the audio back /x/ in this stretch?". The expected sequence is aligned
   by CTC forced alignment and the mean log-posterior of each phoneme is read
   off. It is the more robust of the two measures: in the spike it separated
   correct speech from heavily accented speech consistently (-0.2 vs -5.1),
   while free PER got the sign wrong in 2 of 5 phrases.

Everything runs on ONNX Runtime on the CPU: ~157 ms for a 2-3 s utterance on
this machine (RTF ~0.08). There is no PyTorch anywhere in the project.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Spanish phonetic inventory, collected with espeak-ng across both variants
# (es, es-419). Outside it the model starts hallucinating other languages.
SPANISH_PHONES: frozenset[str] = frozenset({
    # vowels
    "a", "e", "i", "o", "u", "ɛ", "ʊ",
    # semivowels
    "j", "w",
    # stops
    "p", "b", "t", "d", "k", "ɡ",
    # approximants (allophones of b, d, ɡ between vowels)
    "β", "ð", "ɣ",
    # fricatives (θ = peninsular distincion; h = aspiration/Caribbean jota)
    "f", "s", "θ", "x", "h",
    # affricate
    "tʃ",
    # nasals
    "m", "n", "ɲ", "ŋ",
    # laterals and palatal
    "l", "ʎ", "ʝ",
    # tap and trill
    "ɾ", "r",
})

NEG_INF = -1e30


class PhonemeModelUnavailable(RuntimeError):
    """The acoustic model could not be loaded or used."""


@dataclass
class PhonemeRecognition:
    """Recognizer output for one stretch of audio."""

    phonemes: list[str] = field(default_factory=list)
    """Decoding restricted to the Spanish inventory."""

    gop: list[float] = field(default_factory=list)
    """Mean log-posterior per *expected* phoneme, in the order requested."""

    frames: int = 0
    inference_ms: float = 0.0


class PhonemeRecognizer:
    """Loads the model on demand and returns phonemes + GOP."""

    def __init__(
        self,
        repo_id: str = "duyentq/sonari-wav2vec2-phoneme-int8",
        filename: str = "wav2vec2_int8.onnx",
        vocab_repo_id: str = "facebook/wav2vec2-lv-60-espeak-cv-ft",
        vocab_filename: str = "vocab.json",
        inventory: frozenset[str] = SPANISH_PHONES,
    ) -> None:
        self.repo_id = repo_id
        self.filename = filename
        self.vocab_repo_id = vocab_repo_id
        self.vocab_filename = vocab_filename
        self.inventory = inventory
        self._session = None
        self._vocab: dict[str, int] | None = None
        self._id2tok: dict[int, str] | None = None
        self._blank: int = 0
        self._mask: np.ndarray | None = None

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    def available(self) -> bool:
        """True when the model is usable. Never raises."""
        try:
            self.load()
            return True
        except Exception as exc:  # noqa: BLE001 - degrading is the intended behaviour
            # Any failure (network, disk, ONNX) means 'carry on without phonemes'.
            logger.warning("phoneme model unavailable: %s", exc)
            return False

    def load(self):
        if self._session is not None:
            return self._session
        try:
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
        except ImportError as exc:  # pragma: no cover
            raise PhonemeModelUnavailable(
                "onnxruntime/huggingface-hub are not installed. Run: uv sync"
            ) from exc
        try:
            model_path = hf_hub_download(self.repo_id, self.filename)
            vocab_path = hf_hub_download(self.vocab_repo_id, self.vocab_filename)
        except Exception as exc:
            raise PhonemeModelUnavailable(
                f"could not download the phoneme model ({self.repo_id}): {exc}"
            ) from exc

        self._vocab = json.loads(Path(vocab_path).read_text(encoding="utf-8"))
        self._id2tok = {v: k for k, v in self._vocab.items()}
        self._blank = self._vocab.get("<pad>", 0)

        size = len(self._vocab)
        mask = np.full(size, NEG_INF, dtype=np.float32)
        for phone in self.inventory:
            idx = self._vocab.get(phone)
            if idx is not None:
                mask[idx] = 0.0
        mask[self._blank] = 0.0
        self._mask = mask

        self._session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
        return self._session

    @property
    def vocab(self) -> dict[str, int]:
        self.load()
        assert self._vocab is not None
        return self._vocab

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #

    def log_posteriors(self, audio: np.ndarray) -> tuple[np.ndarray, float]:
        """Runs the model and returns `(log_softmax[T, V], elapsed_ms)`."""
        import time

        session = self.load()
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            raise PhonemeModelUnavailable("empty audio.")
        started = time.perf_counter()
        logits = session.run(["logits"], {"input_values": samples[None, :]})[0][0]
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logits = logits - logits.max(axis=-1, keepdims=True)
        log_probs = logits - np.log(np.exp(logits).sum(axis=-1, keepdims=True))
        return log_probs.astype(np.float32), elapsed_ms

    def decode(self, log_probs: np.ndarray) -> list[str]:
        """CTC greedy, restricted to the Spanish inventory."""
        assert self._mask is not None and self._id2tok is not None
        ids = (log_probs + self._mask).argmax(axis=-1)
        out: list[str] = []
        previous = -1
        for token_id in ids:
            if token_id != previous and token_id != self._blank:
                token = self._id2tok.get(int(token_id))
                if token and not token.startswith("<"):
                    out.append(token)
            previous = int(token_id)
        return out

    def forced_align_gop(
        self, log_probs: np.ndarray, expected: list[str]
    ) -> list[float]:
        """Aligns the expected sequence by CTC and returns the mean GOP per phoneme.

        Classic forced alignment over the blank-extended sequence. Each phoneme's
        value is the mean of the log-posteriors of the frames the alignment
        assigned to it; phonemes with no frame get `NEG_INF`.
        """
        self.load()
        assert self._vocab is not None
        ids = [self._vocab.get(p) for p in expected]
        known = [i for i in ids if i is not None]
        if not known:
            return [NEG_INF] * len(expected)

        blank = self._blank
        extended: list[int] = [blank]
        for token_id in known:
            extended.extend((token_id, blank))

        T, L = log_probs.shape[0], len(extended)
        if T == 0:
            return [NEG_INF] * len(expected)

        ext = np.asarray(extended)
        emit = log_probs[:, ext]                      # [T, L]
        dp = np.full((T, L), NEG_INF, dtype=np.float64)
        bp = np.zeros((T, L), dtype=np.int32)
        dp[0, 0] = emit[0, 0]
        if L > 1:
            dp[0, 1] = emit[0, 1]

        # Skip transition allowed only between distinct phonemes (CTC rule).
        can_skip = np.zeros(L, dtype=bool)
        can_skip[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])

        for t in range(1, T):
            stay = dp[t - 1]
            prev = np.full(L, NEG_INF)
            prev[1:] = dp[t - 1, :-1]
            skip = np.full(L, NEG_INF)
            skip[2:] = np.where(can_skip[2:], dp[t - 1, :-2], NEG_INF)

            stacked = np.vstack((stay, prev, skip))     # [3, L]
            choice = stacked.argmax(axis=0)
            best = stacked.max(axis=0)
            dp[t] = best + emit[t]
            bp[t] = np.arange(L) - choice               # 0/-1/-2 offset

        last = L - 1 if L == 1 or dp[T - 1, L - 1] >= dp[T - 1, L - 2] else L - 2
        sums = np.zeros(len(known))
        counts = np.zeros(len(known))
        position = last
        for t in range(T - 1, -1, -1):
            if ext[position] != blank:
                phone_index = (position - 1) // 2
                sums[phone_index] += log_probs[t, ext[position]]
                counts[phone_index] += 1
            position = int(bp[t, position])

        scores = np.where(counts > 0, sums / np.maximum(counts, 1), NEG_INF)

        out: list[float] = []
        cursor = 0
        for token_id in ids:
            if token_id is None:
                out.append(NEG_INF)
            else:
                out.append(float(scores[cursor]))
                cursor += 1
        return out

    def recognize(self, audio: np.ndarray, expected: list[str]) -> PhonemeRecognition:
        """Decodes and scores in a single pass of the model."""
        log_probs, elapsed_ms = self.log_posteriors(audio)
        return PhonemeRecognition(
            phonemes=self.decode(log_probs),
            gop=self.forced_align_gop(log_probs, expected),
            frames=int(log_probs.shape[0]),
            inference_ms=elapsed_ms,
        )
