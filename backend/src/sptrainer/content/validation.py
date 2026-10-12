"""Validacao de conteudo.

Existe porque material de idioma chega de toda parte -- escrito a mao, importado
de planilha, gerado por LLM -- e conteudo errado ensina errado. A regra do
projeto e explicita: **nao presumir que traducao ou explicacao gramatical gerada
por modelo esteja correta**. Aqui conferimos o que da para conferir
mecanicamente; o resto vira aviso para revisao humana.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..assessment.accents import equivalent
from ..assessment.g2p import G2PError, phonemize_text
from .models import Deck, Flashcard, Level

# Faixas de tamanho esperadas por nivel, em palavras. Limites generosos: servem
# para pegar carta no nivel errado, nao para engessar o conteudo.
LEVEL_WORD_RANGES: dict[Level, tuple[int, int]] = {
    Level.BEGINNER: (1, 6),
    Level.INTERMEDIATE: (2, 14),
    Level.ADVANCED: (3, 30),
}

# Tudo que pode aparecer legitimamente em espanhol escrito. Qualquer coisa fora
# disto e erro de digitacao ou texto de outro idioma que entrou por engano --
# acontece de verdade em importacao de planilha e em conteudo gerado.
ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "áéíóúüñÁÉÍÓÚÜÑ"
    "0123456789"
    " .,;:!?¿¡'\"()-–—…«»/%"
)


@dataclass
class Issue:
    card_id: str
    field_name: str
    message: str
    severity: str = "warning"


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    checked: int = 0

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, card_id: str, field_name: str, message: str, severity: str = "warning"):
        self.issues.append(Issue(card_id, field_name, message, severity))


def validate_deck(deck: Deck, *, check_phonemes: bool = True) -> ValidationReport:
    report = ValidationReport(checked=len(deck.cards))

    # 1. Ids repetidos quebram o progresso do aluno: ele revisaria a carta errada.
    for card_id, count in Counter(c.id for c in deck.cards).items():
        if count > 1:
            report.add(card_id, "id", f"id repetido {count} vezes", "error")

    # 2. Texto repetido com ids diferentes e quase sempre importacao duplicada.
    for text, count in Counter(c.text.strip().lower() for c in deck.cards).items():
        if count > 1:
            report.add(text[:32], "text", f"texto repetido em {count} cartas")

    for card in deck.cards:
        _validate_card(card, report, check_phonemes=check_phonemes)
    return report


def _validate_card(card: Flashcard, report: ValidationReport, *, check_phonemes: bool):
    low, high = LEVEL_WORD_RANGES[card.level]
    if not low <= card.word_count <= high:
        report.add(
            card.id, "level",
            f"nivel {card.level.value} espera {low}-{high} palavras, a carta tem "
            f"{card.word_count}",
        )

    # Espanhol e portugues compartilham muito cognato ("azul", "verde", "carro"),
    # entao traducao identica e suspeita, nao erro.
    if card.text == card.translation:
        report.add(
            card.id, "translation",
            "traducao identica ao texto original -- confirme se e cognato mesmo",
        )

    estranhos = sorted({c for c in card.text if c not in ALLOWED_CHARS})
    if estranhos:
        report.add(
            card.id, "text",
            f"caractere fora do alfabeto espanhol: {' '.join(repr(c) for c in estranhos)}",
            "error",
        )

    if card.card_type.value == "question" and not card.text.strip().endswith("?"):
        report.add(card.id, "text", "carta do tipo pergunta sem '?' final")

    if card.text.strip().startswith("¿") and not card.text.strip().endswith("?"):
        report.add(card.id, "text", "abre '¿' mas nao fecha '?'", "error")

    if card.text.strip().endswith("?") and not card.text.strip().startswith("¿"):
        report.add(card.id, "text", "pergunta em espanhol deve abrir com '¿'")

    # 3. O G2P e a conferencia mecanica mais forte que temos: se o espeak-ng nao
    #    consegue fonemizar, o texto quase certamente nao e espanhol valido.
    if check_phonemes:
        try:
            words = phonemize_text(card.text)
        except G2PError as exc:  # pragma: no cover - depende do espeak
            report.add(card.id, "text", f"espeak-ng falhou: {exc}")
        else:
            if not words:
                report.add(card.id, "text", "nenhum fonema gerado para o texto", "error")
            # A comparacao passa pelas classes de equivalencia porque o G2P roda
            # palavra a palavra e perde a alofonia entre palavras: "dias" isolado
            # da /d/, mas em "buenos dias" a mesma letra soa /ð/. Cobrar o simbolo
            # exato acusaria erro em carta correta.
            produced = {p for w in words for p in w.phonemes}
            for target in card.phoneme_targets:
                if not any(equivalent(target, p) for p in produced):
                    report.add(
                        card.id, "phoneme_targets",
                        f"alvo /{target}/ nao aparece na pronuncia de {card.text!r}",
                    )


def fill_expected_phonemes(deck: Deck, voice: str = "es-419") -> Deck:
    """Preenche `expected_phonemes` com o espeak-ng (nunca com LLM)."""
    for card in deck.cards:
        words = phonemize_text(card.text, voice)
        card.expected_phonemes = [p for w in words for p in w.phonemes]
    return deck
