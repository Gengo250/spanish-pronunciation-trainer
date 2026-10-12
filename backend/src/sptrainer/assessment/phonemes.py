"""Reconhecimento acustico de fonemas (wav2vec2 CTC, int8 ONNX).

Este e o modulo que permite falar sobre *sons*, e nao apenas sobre palavras
reconhecidas. Ele faz duas coisas distintas com o mesmo conjunto de logits:

1. **Decodificacao restrita** -- qual sequencia de fonemas o audio contem.
   O modelo e multilingue (392 simbolos, varias linguas). Em decodificacao livre
   ele literalmente interpreta espanhol como mandarim: no spike M0 saiu
   `s. u5 ɑ5 onɡ5 ɕ ts.` para "Juan trajo jamon". Restringir os logits ao
   inventario do espanhol antes do argmax derrubou o PER de 85.7% para 46.4% no
   mesmo audio. Por isso a mascara nao e um detalhe de otimizacao: sem ela o
   modulo nao funciona.

2. **GOP (Goodness of Pronunciation)** -- quao bem o audio sustenta cada fonema
   *esperado*. Aqui nao se pergunta "que sons sao estes?", e sim "o audio apoia
   /x/ neste trecho?". Alinha-se a sequencia esperada por CTC forced alignment e
   le-se o log-posterior medio de cada fonema. E a medida mais robusta das duas:
   no spike ela separou fala correta de fala com sotaque carregado de forma
   consistente (-0.2 vs -5.1), enquanto o PER livre errava o sinal em 2 de 5
   frases.

Tudo roda em ONNX Runtime na CPU: ~157 ms para um trecho de 2-3 s nesta maquina
(RTF ~0.08). Nao ha PyTorch em lugar nenhum do projeto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Inventario fonetico do espanhol, levantado com espeak-ng sobre as duas
# variantes (es, es-419). Fora daqui o modelo comeca a alucinar outras linguas.
SPANISH_PHONES: frozenset[str] = frozenset({
    # vogais
    "a", "e", "i", "o", "u", "ɛ", "ʊ",
    # semivogais
    "j", "w",
    # oclusivas
    "p", "b", "t", "d", "k", "ɡ",
    # aproximantes (alofones de b, d, ɡ entre vogais)
    "β", "ð", "ɣ",
    # fricativas  (θ = distincion peninsular; h = aspiracao/jota caribenha)
    "f", "s", "θ", "x", "h",
    # africada
    "tʃ",
    # nasais
    "m", "n", "ɲ", "ŋ",
    # laterais e palatal
    "l", "ʎ", "ʝ",
    # tap e vibrante
    "ɾ", "r",
})

NEG_INF = -1e30


class PhonemeModelUnavailable(RuntimeError):
    """O modelo acustico nao pode ser carregado ou usado."""


@dataclass
class PhonemeRecognition:
    """Saida do reconhecedor para um trecho de audio."""

    phonemes: list[str] = field(default_factory=list)
    """Decodificacao restrita ao inventario do espanhol."""

    gop: list[float] = field(default_factory=list)
    """Log-posterior medio por fonema *esperado*, na ordem em que foram pedidos."""

    frames: int = 0
    inference_ms: float = 0.0


class PhonemeRecognizer:
    """Carrega o modelo sob demanda e devolve fonemas + GOP."""

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
    # Carregamento
    # ------------------------------------------------------------------ #

    def available(self) -> bool:
        """True quando da para usar o modelo. Nunca levanta excecao."""
        try:
            self.load()
            return True
        except Exception as exc:  # noqa: BLE001 - degradar e o comportamento desejado
            # Qualquer falha (rede, disco, ONNX) significa 'siga sem fonemas'.
            logger.warning("modelo de fonemas indisponivel: %s", exc)
            return False

    def load(self):
        if self._session is not None:
            return self._session
        try:
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
        except ImportError as exc:  # pragma: no cover
            raise PhonemeModelUnavailable(
                "onnxruntime/huggingface-hub nao instalados. Rode: uv sync"
            ) from exc
        try:
            model_path = hf_hub_download(self.repo_id, self.filename)
            vocab_path = hf_hub_download(self.vocab_repo_id, self.vocab_filename)
        except Exception as exc:
            raise PhonemeModelUnavailable(
                f"nao foi possivel baixar o modelo de fonemas ({self.repo_id}): {exc}"
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
    # Inferencia
    # ------------------------------------------------------------------ #

    def log_posteriors(self, audio: np.ndarray) -> tuple[np.ndarray, float]:
        """Roda o modelo e devolve `(log_softmax[T, V], tempo_ms)`."""
        import time

        session = self.load()
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            raise PhonemeModelUnavailable("audio vazio.")
        started = time.perf_counter()
        logits = session.run(["logits"], {"input_values": samples[None, :]})[0][0]
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logits = logits - logits.max(axis=-1, keepdims=True)
        log_probs = logits - np.log(np.exp(logits).sum(axis=-1, keepdims=True))
        return log_probs.astype(np.float32), elapsed_ms

    def decode(self, log_probs: np.ndarray) -> list[str]:
        """CTC greedy, restrito ao inventario do espanhol."""
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
        """Alinha a sequencia esperada por CTC e devolve o GOP medio por fonema.

        Forced alignment classico sobre a sequencia estendida com blanks. O valor
        de cada fonema e a media dos log-posteriors dos frames que o alinhamento
        atribuiu a ele; fonemas sem frame recebem `NEG_INF`.
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

        # Transicao de salto permitida apenas entre fonemas distintos (regra CTC).
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
            bp[t] = np.arange(L) - choice               # 0/-1/-2 deslocamento

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
        """Decodifica e pontua em uma unica passada do modelo."""
        log_probs, elapsed_ms = self.log_posteriors(audio)
        return PhonemeRecognition(
            phonemes=self.decode(log_probs),
            gop=self.forced_align_gop(log_probs, expected),
            frames=int(log_probs.shape[0]),
            inference_ms=elapsed_ms,
        )
