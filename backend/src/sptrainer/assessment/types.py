"""Contrato da avaliacao de pronuncia.

A regra que organiza este modulo: **toda afirmacao carrega a evidencia que a
sustenta**. Se o modelo acustico de fonemas estiver desligado, ausente ou falhar,
as conclusoes de nivel fonetico simplesmente nao existem no resultado -- elas nao
sao adivinhadas, nem preenchidas por estimativa.

`AssessmentResult.capabilities` diz o que esta rodando de fato, e `limitations`
diz, em portugues, o que esta analise nao consegue afirmar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Evidence(str, Enum):
    """De onde veio a conclusao. Sem isso, nenhum finding entra no resultado."""

    TRANSCRIPT = "transcript"
    """Comparacao do texto reconhecido pelo Whisper com o texto esperado."""

    PHONEME_ACOUSTIC = "phoneme_acoustic"
    """Posteriors por fonema do wav2vec2 alinhados a sequencia esperada (GOP)."""

    PROSODY = "prosody"
    """Duracao, ritmo e pausas medidos nos timestamps por palavra."""


class Capability(str, Enum):
    TRANSCRIPT_MATCH = "transcript_match"
    PHONEME_ANALYSIS = "phoneme_analysis"
    PROSODY_ANALYSIS = "prosody_analysis"


class Severity(str, Enum):
    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"


@dataclass
class Finding:
    """Uma observacao isolada e rastreavel sobre a fala do aluno."""

    kind: str
    message: str
    evidence: Evidence
    severity: Severity = Severity.INFO
    word: str | None = None
    word_index: int | None = None
    expected: str | None = None
    heard: str | None = None
    score: float | None = None
    """Valor bruto que gerou a conclusao (GOP, probabilidade, segundos...)."""


@dataclass
class PhonemeScore:
    """Um som esperado e o quanto o audio o sustentou.

    E o que a interface desenha na fita de fonemas. `status` ja vem resolvido
    aqui para que a tela nao precise reimplementar os limiares -- e para que
    `unknown` continue sendo `unknown`, em vez de virar "ruim" por omissao.
    """

    index: int
    phone: str
    word_index: int
    gop: float | None = None
    status: str = "unknown"
    """strong | fair | weak | unknown"""


@dataclass
class WordScore:
    index: int
    expected: str
    recognized: str | None
    matched: bool
    phoneme_accuracy: float | None = None
    mean_gop: float | None = None
    start: float | None = None
    end: float | None = None


@dataclass
class Scores:
    """Numeros, todos reproduziveis. As formulas estao em scoring.py e no README."""

    word_accuracy: float
    phoneme_accuracy: float | None = None
    fluency: float | None = None
    practice_score: float = 0.0


@dataclass
class AssessmentResult:
    expected_text: str
    recognized_text: str
    scores: Scores
    words: list[WordScore] = field(default_factory=list)
    phonemes: list[PhonemeScore] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    capabilities: set[Capability] = field(default_factory=set)
    limitations: list[str] = field(default_factory=list)
    no_speech_detected: bool = False
    audio_duration: float = 0.0

    def findings_by_evidence(self, evidence: Evidence) -> list[Finding]:
        return [f for f in self.findings if f.evidence is evidence]

    @property
    def has_phoneme_analysis(self) -> bool:
        return Capability.PHONEME_ANALYSIS in self.capabilities
