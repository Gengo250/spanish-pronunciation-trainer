"""Cenarios obrigatorios da avaliacao (secao 13 da especificacao).

Nenhum destes testes carrega o Whisper ou o modelo acustico: o objetivo e provar
a LOGICA -- porta de silencio, palavras faltando, degradacao honesta -- de forma
deterministica e rapida.
"""

import numpy as np
import pytest
from conftest import FakeTranscriber, FakeWord

from sptrainer.assessment.pipeline import AssessmentPipeline
from sptrainer.assessment.types import Capability, Evidence

PHRASE = "Me gustaría aprender español"


def build(text, words=None, recognizer=None, **kw):
    return AssessmentPipeline(
        transcriber=FakeTranscriber(text, words), recognizer=recognizer, **kw
    )


# --- fala correta ----------------------------------------------------------

def test_correct_phrase_scores_full_word_accuracy(speech_audio):
    result = build(PHRASE).assess(speech_audio, PHRASE)
    assert result.scores.word_accuracy == 1.0
    assert result.no_speech_detected is False
    assert not [f for f in result.findings if f.kind == "word_not_recognized"]


def test_accent_marks_do_not_count_as_errors(speech_audio):
    """O Whisper oscila entre 'gustaria' e 'gustaría'; isso nao e erro."""
    result = build("me gustaria aprender español").assess(speech_audio, PHRASE)
    assert result.scores.word_accuracy == 1.0


# --- fala com problemas ----------------------------------------------------

def test_missing_word_is_reported(speech_audio):
    result = build("Me gustaría español").assess(speech_audio, PHRASE)
    missing = [f for f in result.findings if f.kind == "word_not_recognized"]
    assert [f.word for f in missing] == ["aprender"]
    assert all(f.evidence is Evidence.TRANSCRIPT for f in missing)
    assert result.scores.word_accuracy < 1.0


def test_wrong_words_lower_the_score(speech_audio):
    result = build("Me gusta aprender portugués").assess(speech_audio, PHRASE)
    assert result.scores.word_accuracy < 0.6
    assert result.scores.practice_score < 70


def test_completely_different_speech(speech_audio):
    result = build("hola buenos días").assess(speech_audio, PHRASE)
    assert result.scores.word_accuracy == 0.0


# --- gravacoes vazias ou mudas --------------------------------------------

def test_silence_reports_no_speech_instead_of_zero(speech_audio):
    """Microfone mudo nao e erro de pronuncia: nao pode virar nota zero seca."""
    silence = np.zeros(16000 * 2, dtype=np.float32)
    result = build(PHRASE).assess(silence, PHRASE)
    assert result.no_speech_detected is True
    assert [f.kind for f in result.findings] == ["no_speech"]
    assert "microphone" in result.findings[0].message.lower()


def test_empty_recording_is_handled():
    result = build(PHRASE).assess(np.zeros(0, dtype=np.float32), PHRASE)
    assert result.no_speech_detected is True


def test_recording_too_short_is_rejected():
    tiny = (np.random.default_rng(0).standard_normal(1000) * 0.2).astype(np.float32)
    assert build(PHRASE).assess(tiny, PHRASE).no_speech_detected is True


# --- degradacao honesta ----------------------------------------------------

def test_without_the_acoustic_model_there_are_no_phoneme_claims(speech_audio):
    result = build(PHRASE, recognizer=None).assess(speech_audio, PHRASE)
    assert Capability.PHONEME_ANALYSIS not in result.capabilities
    assert result.findings_by_evidence(Evidence.PHONEME_ACOUSTIC) == []
    assert result.scores.phoneme_accuracy is None
    assert any("Sound-by-sound analysis is off" in limit for limit in result.limitations)


def test_a_failing_model_degrades_instead_of_crashing(speech_audio):
    class Broken:
        def recognize(self, audio, expected):
            raise RuntimeError("modelo corrompido")

    result = build(PHRASE, recognizer=Broken()).assess(speech_audio, PHRASE)
    assert Capability.PHONEME_ANALYSIS not in result.capabilities
    assert result.findings_by_evidence(Evidence.PHONEME_ACOUSTIC) == []
    assert result.scores.word_accuracy == 1.0, "a transcricao continua valendo"


def test_phonemes_disabled_by_configuration(speech_audio):
    class Unused:
        def recognize(self, audio, expected):  # pragma: no cover
            raise AssertionError("nao deveria ser chamado")

    result = build(PHRASE, recognizer=Unused(), phonemes_enabled=False).assess(
        speech_audio, PHRASE
    )
    assert Capability.PHONEME_ANALYSIS not in result.capabilities


def test_fluency_is_omitted_without_a_reference(speech_audio):
    result = build(PHRASE).assess(speech_audio, PHRASE)
    assert result.scores.fluency is None
    assert any("reference audio" in limit for limit in result.limitations)


# --- prosodia --------------------------------------------------------------

def test_long_pause_is_reported(speech_audio):
    words = [FakeWord("Me", 0.0, 0.3), FakeWord("gustaría", 1.5, 2.0)]
    result = build("Me gustaría", words).assess(speech_audio, "Me gustaría")
    pauses = [f for f in result.findings if f.kind == "pause"]
    assert len(pauses) == 1
    assert pauses[0].score == pytest.approx(1.2, abs=0.01)
    assert pauses[0].evidence is Evidence.PROSODY


def test_slow_speech_is_reported(speech_audio):
    words = [FakeWord("Me", 0.0, 0.4), FakeWord("gustaría", 0.4, 3.0)]
    result = build("Me gustaría", words).assess(
        speech_audio, "Me gustaría", reference_rate=3.0
    )
    assert any(f.kind == "speech_rate" for f in result.findings)


# --- ritmo so existe com mais de uma palavra -------------------------------

def test_single_word_card_reports_no_speech_rate(speech_audio):
    """Uma palavra tem duracao, nao ritmo.

    Antes desta regra, "Gracias" comparado com a propria referencia acusava
    "muito mais rapido que a referencia" -- contra o audio identico.
    """
    words = [FakeWord("Gracias", 0.2, 0.9)]
    result = build("Gracias", words).assess(
        speech_audio, "Gracias", reference_rate=1.4
    )
    assert result.scores.fluency is None
    assert not [f for f in result.findings if f.kind == "speech_rate"]


def test_two_words_do_get_a_rate(speech_audio):
    words = [FakeWord("Buenos", 0.1, 0.6), FakeWord("días", 0.6, 1.1)]
    result = build("Buenos días", words).assess(
        speech_audio, "Buenos días", reference_rate=2.0
    )
    assert result.scores.fluency is not None


def test_reference_gop_removes_false_positives(speech_audio):
    """Com a referencia como base, som intrinsecamente fraco deixa de virar erro.

    /ð/ e /a/ atono tem GOP baixo mesmo numa pronuncia perfeita. Contra um
    limiar absoluto isso vira acusacao; contra a referencia da propria carta,
    a diferenca e zero e nada e reportado.
    """
    class FixedRecognizer:
        def __init__(self, gop):
            self.gop = gop

        def recognize(self, audio, expected):
            from sptrainer.assessment.phonemes import PhonemeRecognition
            return PhonemeRecognition(phonemes=list(expected), gop=self.gop[: len(expected)])

    expected_len = 20
    weak = [-3.0] * expected_len          # tudo abaixo do piso absoluto
    pipeline = build(PHRASE, recognizer=FixedRecognizer(weak))

    without_reference = pipeline.assess(speech_audio, PHRASE)
    assert without_reference.findings_by_evidence(Evidence.PHONEME_ACOUSTIC)

    with_reference = pipeline.assess(speech_audio, PHRASE, reference_gop=weak)
    assert with_reference.findings_by_evidence(Evidence.PHONEME_ACOUSTIC) == []
