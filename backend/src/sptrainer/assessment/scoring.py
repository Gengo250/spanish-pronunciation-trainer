"""Formulas de pontuacao. Todas puras, deterministas e documentadas.

A regra do projeto: **nenhum numero sem formula reproduzivel**. Cada funcao aqui
e pura (entra lista, sai float), testada com fixtures, e a conta aparece tanto na
docstring quanto no README.

O que estas notas NAO sao: certificacao de proficiencia. Nao ha mapeamento para
CEFR nem pretensao de equivalencia com exame oficial. Sao um instrumento de
estudo -- servem para o aluno ver progresso entre tentativas da mesma carta.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .align import align, error_rate
from .types import Scores

# Pesos da nota de pratica. Somam 1.0 quando os tres componentes existem;
# quando um falta, os demais sao renormalizados (ver `practice_score`).
WEIGHT_WORD = 0.50
WEIGHT_PHONEME = 0.35
WEIGHT_FLUENCY = 0.15

# Faixa de velocidade aceita, como razao da referencia da ElevenLabs.
RATE_COMFORT_LOW = 0.75
RATE_COMFORT_HIGH = 1.30

# Pausa normal entre palavras; acima disso comeca a pesar na fluencia.
PAUSE_BUDGET_S = 0.60

# "ñ" e letra, nao "n" com acento. Precisa sobreviver a remocao de diacriticos.
_ENYE_SENTINEL = ""


def normalize_word(word: str) -> str:
    """Forma canonica para comparar *identidade de palavra*.

    Minusculas, sem pontuacao e sem acento. Acento sai porque o Whisper oscila
    entre "gustaria" e "gustaría" para a mesma fala, e isso nao e erro de
    pronuncia. O "ñ" e preservado: "ano" e "año" sao palavras diferentes.

    Atencao: isto serve so para casar palavras. O G2P sempre recebe o texto
    original, com acento, porque ali o acento define a silaba tonica.
    """
    protected = word.replace("ñ", _ENYE_SENTINEL).replace("Ñ", _ENYE_SENTINEL)
    decomposed = unicodedata.normalize("NFD", protected)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    restored = stripped.replace(_ENYE_SENTINEL, "ñ")
    return "".join(c for c in restored.lower() if c.isalnum() or c == "ñ")


def tokenize_words(text: str) -> list[str]:
    return [w for w in (normalize_word(t) for t in text.split()) if w]


def word_accuracy(expected: str, recognized: str) -> float:
    """`1 - WER`, limitado a [0, 1].

    WER = (substituicoes + delecoes + insercoes) / palavras_esperadas,
    calculado por alinhamento de Levenshtein sobre palavras normalizadas.
    """
    exp, rec = tokenize_words(expected), tokenize_words(recognized)
    if not exp:
        return 1.0 if not rec else 0.0
    errors = sum(1 for p in align(exp, rec) if p.is_error)
    return max(0.0, min(1.0, 1.0 - errors / len(exp)))


def phoneme_accuracy(expected: list[str], heard: list[str]) -> float:
    """`1 - PER`, depois de colapsar equivalencias de sotaque e geminadas."""
    return max(0.0, min(1.0, 1.0 - error_rate(expected, heard)))


def fluency(rate_ratio: float | None, pause_total: float) -> float | None:
    """Nota de fluencia a partir de velocidade e tempo parado.

    Dois componentes multiplicados:

    - ritmo: 1.0 dentro da faixa confortavel (0.75x a 1.30x da referencia),
      caindo linearmente fora dela, com piso em 0.
    - pausas: `1 - max(0, total_pausado - 0.60s) / 3s`, com piso em 0.

    Devolve `None` quando nao ha referencia de velocidade -- sem ela a conta
    nao teria significado, e inventar um valor seria pior que omitir.
    """
    if rate_ratio is None:
        return None
    if rate_ratio < RATE_COMFORT_LOW:
        rhythm = max(0.0, rate_ratio / RATE_COMFORT_LOW)
    elif rate_ratio > RATE_COMFORT_HIGH:
        rhythm = max(0.0, 1.0 - (rate_ratio - RATE_COMFORT_HIGH))
    else:
        rhythm = 1.0
    excess = max(0.0, pause_total - PAUSE_BUDGET_S)
    pause_factor = max(0.0, 1.0 - excess / 3.0)
    return max(0.0, min(1.0, rhythm * pause_factor))


def practice_score(
    word: float, phoneme: float | None = None, fluency_score: float | None = None
) -> float:
    """Nota de pratica 0-100: media ponderada dos componentes disponiveis.

    Pesos: palavra 0.50, fonema 0.35, fluencia 0.15. Componentes ausentes sao
    excluidos e os pesos restantes renormalizados -- uma analise sem fonemas
    continua produzindo nota, so que baseada no que foi realmente medido.
    """
    parts = [(WEIGHT_WORD, word)]
    if phoneme is not None:
        parts.append((WEIGHT_PHONEME, phoneme))
    if fluency_score is not None:
        parts.append((WEIGHT_FLUENCY, fluency_score))
    total_weight = sum(w for w, _ in parts)
    if total_weight <= 0:
        return 0.0
    return round(100.0 * sum(w * v for w, v in parts) / total_weight, 1)


@dataclass
class ScoreInputs:
    expected_text: str
    recognized_text: str
    expected_phonemes: list[str] | None = None
    heard_phonemes: list[str] | None = None
    rate_ratio: float | None = None
    pause_total: float = 0.0


def compute(inputs: ScoreInputs) -> Scores:
    word = word_accuracy(inputs.expected_text, inputs.recognized_text)
    phoneme = (
        phoneme_accuracy(inputs.expected_phonemes, inputs.heard_phonemes)
        if inputs.expected_phonemes is not None and inputs.heard_phonemes is not None
        else None
    )
    flu = fluency(inputs.rate_ratio, inputs.pause_total)
    return Scores(
        word_accuracy=word,
        phoneme_accuracy=phoneme,
        fluency=flu,
        practice_score=practice_score(word, phoneme, flu),
    )
