"""Orquestracao da avaliacao: audio do aluno -> AssessmentResult.

A ordem importa e esta documentada porque cada etapa pode desligar as seguintes:

    audio -> porta de silencio -> Whisper -> G2P -> fonemas -> prosodia -> notas

**A regra que manda neste arquivo:** um finding so e criado quando existe
evidencia medida que o sustente. Se o modelo acustico estiver desligado, ausente
ou falhar, `Capability.PHONEME_ANALYSIS` nao entra em `capabilities`, nenhum
finding de fonema e gerado e a limitacao e declarada em texto. Nada e estimado
"por aproximacao", e o LLM mais adiante so pode reescrever o que esta aqui.
"""

from __future__ import annotations

import logging

import numpy as np

from ..audio.utils import duration_seconds, normalize_for_wav2vec2, rms_level, to_float32
from . import g2p, prosody, scoring
from .accents import is_model_artifact
from .align import Op, align
from .phonemes import NEG_INF, PhonemeRecognizer
from .types import (
    AssessmentResult,
    Capability,
    Evidence,
    Finding,
    PhonemeScore,
    Severity,
    WordScore,
)

logger = logging.getLogger(__name__)

# Abaixo disto nao ha fala suficiente para avaliar coisa alguma.
MIN_DURATION_S = 0.25
MIN_RMS = 0.005

# --- Limiares de pronuncia -------------------------------------------------
# Medidos em 79 fonemas (3 frases), comparando audio de referencia da ElevenLabs
# com fala de sotaque carregado. Os numeros estao em docs/pronunciation-assessment.md.
#
# O limiar RELATIVO e o caminho principal: cada carta tem audio de referencia em
# cache, entao da para perguntar "este som saiu MUITO pior do que na referencia
# desta mesma frase?". Isso absorve de graca a sinalefa, as aproximantes fracas
# e as palavras atonas -- justamente os casos em que o limiar absoluto acusava
# erro em audio comprovadamente correto.
#
#   absoluto -2.0 -> 5/79 falsos positivos na referencia | 45/79 detectados
#   absoluto -2.5 -> 1/79 falsos positivos               | 42/79 detectados
#   relativo -2.0 -> 0/79 por construcao                 | 45/79 detectados
GOP_RELATIVE_MARGIN = -2.0

# Usado so quando nao ha referencia (carta nunca sintetizada). Mais conservador
# de proposito: sem base de comparacao, e melhor calar do que acusar errado.
GOP_ABSOLUTE_FLOOR = -2.5

# Acima deste GOP o som saiu claramente bem; entre ele e o limiar de erro, fica
# "razoavel". Serve so para colorir a fita de fonemas na tela.
GOP_STRONG = -1.0

# Teto de observacoes por tentativa. Nao e estatistica, e didatica: uma lista de
# quinze sons errados nao ensina ninguem. Mostramos as piores palavras.
MAX_PHONEME_FINDINGS = 3

LIMITATION_NO_PHONEMES = (
    "Sound-by-sound analysis is off: the feedback covers the recognised words, "
    "the pacing and the pauses only. It cannot say which sound came out wrong."
)
LIMITATION_CALIBRATION = (
    "Pronunciation thresholds were calibrated on synthetic speech and a small "
    "sample. Treat sound-level observations as study guidance, not as a verdict."
)
LIMITATION_NO_REFERENCE = (
    "Without reference audio for this card the pacing cannot be compared, so the "
    "fluency score is left out."
)
LIMITATION_JOTA = (
    "Swaps between /x/ (the jota) and /k/ are not reported: the recogniser "
    "confuses the two on its own, so a learner error cannot be told apart from a "
    "model error."
)


class AssessmentPipeline:
    """Junta transcricao, fonemas e prosodia em um unico resultado."""

    def __init__(
        self,
        transcriber,
        recognizer: PhonemeRecognizer | None = None,
        espeak_voice: str = "es-419",
        absolute_floor: float = GOP_ABSOLUTE_FLOOR,
        phonemes_enabled: bool = True,
    ) -> None:
        self.transcriber = transcriber
        self.recognizer = recognizer
        self.espeak_voice = espeak_voice
        self.absolute_floor = absolute_floor
        self.phonemes_enabled = phonemes_enabled

    # ------------------------------------------------------------------ #

    def assess(
        self,
        audio: np.ndarray,
        expected_text: str,
        sample_rate: int = 16000,
        reference_rate: float | None = None,
        reference_gop: list[float] | None = None,
    ) -> AssessmentResult:
        samples = to_float32(audio)
        duration = duration_seconds(samples, sample_rate)

        # 1. Porta de silencio. Gravacao muda devolve "nao ouvi", nunca nota zero:
        #    zero diria ao aluno que ele errou tudo, quando o microfone e que falhou.
        if duration < MIN_DURATION_S or rms_level(samples) < MIN_RMS:
            return AssessmentResult(
                expected_text=expected_text,
                recognized_text="",
                scores=scoring.Scores(word_accuracy=0.0, practice_score=0.0),
                no_speech_detected=True,
                audio_duration=duration,
                limitations=["No speech was detected in the recording."],
                findings=[
                    Finding(
                        kind="no_speech",
                        message="We did not hear anything. Check your microphone and record again.",
                        evidence=Evidence.TRANSCRIPT,
                        severity=Severity.INFO,
                    )
                ],
            )

        # 2. Transcricao.
        transcript = self.transcriber.transcribe(samples, sample_rate=sample_rate)
        capabilities = {Capability.TRANSCRIPT_MATCH}
        limitations: list[str] = []
        findings: list[Finding] = []

        # 3. Fonemas esperados, palavra por palavra (ver g2p.py).
        expected_words = g2p.phonemize_text(expected_text, self.espeak_voice)
        expected_phones = g2p.flatten(expected_words)
        phone_to_word = g2p.phoneme_word_map(expected_words)

        # 4. Analise acustica por fonema -- so se realmente disponivel.
        heard_phones: list[str] | None = None
        gop: list[float] | None = None
        if self.phonemes_enabled and self.recognizer is not None and expected_phones:
            try:
                recognition = self.recognizer.recognize(
                    normalize_for_wav2vec2(samples), expected_phones
                )
                heard_phones, gop = recognition.phonemes, recognition.gop
                capabilities.add(Capability.PHONEME_ANALYSIS)
                limitations.append(LIMITATION_CALIBRATION)
                limitations.append(LIMITATION_JOTA)
            except Exception as exc:  # noqa: BLE001 - ver docstring do modulo
                # A aula nao pode cair porque o modelo acustico falhou: a
                # avaliacao degrada para transcricao + prosodia e diz isso.
                logger.warning("analise de fonemas falhou, seguindo sem ela: %s", exc)
                limitations.append(LIMITATION_NO_PHONEMES)
        else:
            limitations.append(LIMITATION_NO_PHONEMES)

        # 5. Prosodia.
        prosody_result = prosody.analyse(
            samples, transcript.words, sample_rate, reference_rate
        )
        if transcript.words:
            capabilities.add(Capability.PROSODY_ANALYSIS)
        if reference_rate is None:
            limitations.append(LIMITATION_NO_REFERENCE)

        # 6. Notas.
        pause_total = sum(p.duration for p in prosody_result.pauses)
        scores = scoring.compute(
            scoring.ScoreInputs(
                expected_text=expected_text,
                recognized_text=transcript.text,
                expected_phonemes=expected_phones if heard_phones is not None else None,
                heard_phonemes=heard_phones,
                rate_ratio=prosody_result.rate_ratio,
                pause_total=pause_total,
            )
        )

        # 7. Findings, cada um amarrado a sua evidencia.
        words = self._word_scores(expected_words, transcript, gop, phone_to_word)
        phoneme_scores = self._phoneme_scores(
            expected_phones, phone_to_word, gop, reference_gop
        )
        findings.extend(self._word_findings(words))
        if gop is not None:
            findings.extend(
                self._phoneme_findings(
                    expected_words, expected_phones, gop, phone_to_word,
                    heard_phones or [], reference_gop,
                )
            )
        findings.extend(self._prosody_findings(prosody_result))

        return AssessmentResult(
            expected_text=expected_text,
            recognized_text=transcript.text,
            scores=scores,
            words=words,
            phonemes=phoneme_scores,
            findings=findings,
            capabilities=capabilities,
            limitations=limitations,
            audio_duration=duration,
        )

    # ------------------------------------------------------------------ #
    # Resultado por fonema
    # ------------------------------------------------------------------ #

    def _phoneme_scores(
        self, expected_phones, phone_to_word, gop, reference_gop
    ) -> list[PhonemeScore]:
        """Monta a fita de fonemas que a interface desenha.

        Sem analise acustica todos os sons ficam `unknown` -- a tela mostra a
        fita apagada em vez de inventar cores.
        """
        usable_reference = reference_gop is not None and len(reference_gop) == len(
            gop or []
        )
        scores: list[PhonemeScore] = []
        for i, phone in enumerate(expected_phones):
            if gop is None or i >= len(gop) or gop[i] <= NEG_INF:
                scores.append(
                    PhonemeScore(index=i, phone=phone, word_index=phone_to_word[i])
                )
                continue
            value = gop[i]
            if usable_reference:
                delta = value - reference_gop[i]
                status = (
                    "weak" if delta < GOP_RELATIVE_MARGIN
                    else "fair" if delta < GOP_RELATIVE_MARGIN / 2
                    else "strong"
                )
            else:
                status = (
                    "weak" if value < self.absolute_floor
                    else "fair" if value < GOP_STRONG
                    else "strong"
                )
            scores.append(
                PhonemeScore(index=i, phone=phone, word_index=phone_to_word[i],
                             gop=round(value, 3), status=status)
            )
        return scores

    # ------------------------------------------------------------------ #
    # Findings
    # ------------------------------------------------------------------ #

    def _word_scores(self, expected_words, transcript, gop, phone_to_word) -> list[WordScore]:
        recognized = scoring.tokenize_words(transcript.text)
        expected_tokens = [scoring.normalize_word(w.word) for w in expected_words]
        pairs = align(expected_tokens, recognized)

        matched: dict[int, str | None] = {}
        for pair in pairs:
            if pair.expected_index is None:
                continue
            matched[pair.expected_index] = (
                pair.heard if pair.op in (Op.MATCH, Op.EQUIVALENT) else None
            )

        per_word_gop: dict[int, list[float]] = {}
        if gop is not None:
            for phone_index, word_index in enumerate(phone_to_word):
                if phone_index < len(gop) and gop[phone_index] > NEG_INF:
                    per_word_gop.setdefault(word_index, []).append(gop[phone_index])

        out: list[WordScore] = []
        for i, word in enumerate(expected_words):
            timings = transcript.words[i] if i < len(transcript.words) else None
            scores_for_word = per_word_gop.get(i)
            out.append(
                WordScore(
                    index=i,
                    expected=word.word,
                    recognized=matched.get(i),
                    matched=matched.get(i) is not None,
                    mean_gop=float(np.mean(scores_for_word)) if scores_for_word else None,
                    start=timings.start if timings else None,
                    end=timings.end if timings else None,
                )
            )
        return out

    def _word_findings(self, words: list[WordScore]) -> list[Finding]:
        missing = [w for w in words if not w.matched]
        return [
            Finding(
                kind="word_not_recognized",
                message=f"“{w.expected}” was not recognised.",
                evidence=Evidence.TRANSCRIPT,
                severity=Severity.MAJOR,
                word=w.expected,
                word_index=w.index,
            )
            for w in missing
        ]

    def _phoneme_findings(
        self, expected_words, expected_phones, gop, phone_to_word, heard_phones,
        reference_gop: list[float] | None = None,
    ) -> list[Finding]:
        """Sons mal sustentados pelo audio.

        Tres filtros, todos necessarios para nao inventar problema:

        1. o fonema tem de ficar abaixo do limiar -- relativo a referencia da
           propria carta quando ela existe, absoluto (mais severo) quando nao;
        2. a troca nao pode ser confusao conhecida do reconhecedor (jota);
        3. so as piores `MAX_PHONEME_FINDINGS` palavras viram texto.
        """
        usable_reference = (
            reference_gop is not None and len(reference_gop) == len(gop)
        )
        by_word: dict[int, list[tuple[str, float]]] = {}
        for phone_index, score in enumerate(gop):
            if score <= NEG_INF:
                continue
            if usable_reference:
                baseline = reference_gop[phone_index]
                if baseline <= NEG_INF or score - baseline >= GOP_RELATIVE_MARGIN:
                    continue
            elif score >= self.absolute_floor:
                continue
            phone = expected_phones[phone_index]
            word_index = phone_to_word[phone_index]
            if any(is_model_artifact(phone, h) for h in heard_phones):
                continue
            by_word.setdefault(word_index, []).append((phone, score))

        # As piores palavras primeiro, para caber no teto didatico.
        ranked = sorted(by_word.items(), key=lambda kv: min(s for _, s in kv[1]))

        findings: list[Finding] = []
        for word_index, bad in ranked[:MAX_PHONEME_FINDINGS]:
            word = expected_words[word_index]
            sounds = ", ".join(f"/{p}/" for p, _ in bad)
            worst = min(score for _, score in bad)
            findings.append(
                Finding(
                    kind="weak_phoneme",
                    message=(
                        f"In “{word.word}”, the audio weakly supports "
                        f"{'the sound' if len(bad) == 1 else 'the sounds'} {sounds}. "
                        "Listen to the reference and repeat slowly."
                    ),
                    evidence=Evidence.PHONEME_ACOUSTIC,
                    severity=Severity.MINOR if len(bad) == 1 else Severity.MAJOR,
                    word=word.word,
                    word_index=word_index,
                    expected="".join(p for p, _ in bad),
                    score=worst,
                )
            )
        return findings

    def _prosody_findings(self, result: prosody.ProsodyResult) -> list[Finding]:
        findings: list[Finding] = []
        ratio = result.rate_ratio
        if ratio is not None:
            if ratio < scoring.RATE_COMFORT_LOW:
                findings.append(
                    Finding(
                        kind="speech_rate",
                        message="You spoke more slowly than the reference.",
                        evidence=Evidence.PROSODY,
                        severity=Severity.MINOR,
                        score=ratio,
                    )
                )
            elif ratio > scoring.RATE_COMFORT_HIGH:
                findings.append(
                    Finding(
                        kind="speech_rate",
                        message="You spoke faster than the reference.",
                        evidence=Evidence.PROSODY,
                        severity=Severity.MINOR,
                        score=ratio,
                    )
                )
        for pause in result.pauses:
            findings.append(
                Finding(
                    kind="pause",
                    message=(
                        f"There was a {pause.duration:.1f}s pause after "
                        f"“{pause.after_word}”."
                    ),
                    evidence=Evidence.PROSODY,
                    severity=Severity.INFO,
                    word=pause.after_word,
                    word_index=pause.after_index,
                    score=pause.duration,
                )
            )
        return findings
