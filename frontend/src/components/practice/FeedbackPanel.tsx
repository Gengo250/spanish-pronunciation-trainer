import { useState } from "react";
import { t } from "../../i18n/en";
import type { Assessment } from "../../lib/api";
import { hasSoundAnalysis, headline, notes, scoreBand } from "../../lib/labels";
import { Button } from "../ui/Button";
import { Notice } from "../ui/Notice";
import { SoundStrip } from "./SoundStrip";

/**
 * What the learner reads after speaking.
 *
 * Ordered by what helps most: a plain sentence first, then which words came
 * through, then — only on request — the sound-by-sound detail. The score is
 * present but small; it informs without turning practice into a test.
 *
 * Nothing uncertain is shown as a definitive error. Sound-level marks appear
 * only when the acoustic analysis actually ran, and the method note says so
 * when it did not.
 */

type Props = {
  result: Assessment;
  words: string[];
  onRetry: () => void;
  onNext: () => void;
  canReplay: boolean;
  onReplay: () => void;
};

export function FeedbackPanel({ result, words, onRetry, onNext, canReplay, onReplay }: Props) {
  const [showDetail, setShowDetail] = useState(false);
  const [showMethod, setShowMethod] = useState(false);

  if (result.no_speech_detected) {
    return (
      <section className="feedback">
        <Notice tone="error" role="status">
          {t.feedback.noSpeech}
        </Notice>
        <div className="feedback__actions">
          <Button variant="primary" onClick={onRetry} shortcut="R">
            {t.practice.tryAgain}
          </Button>
        </div>
      </section>
    );
  }

  const score = Math.round(result.scores.practice_score);
  const sounds = hasSoundAnalysis(result);
  const missedWords = new Set(result.words.filter((w) => !w.matched).map((w) => w.index));

  return (
    <section className="feedback" aria-label={t.feedback.title}>
      <p className="feedback__headline">{headline(result)}</p>

      <div className="verdict">
        <div
          className="verdict__score"
          data-band={scoreBand(score)}
          aria-label={t.a11y.scoreOutOf(score)}
        >
          {score}
        </div>
        <ul className="verdict__notes">
          {notes(result).map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      </div>

      {result.recognized_text && (
        <div className="heard">
          <span className="label">{t.feedback.heardLabel}</span>
          <p className="heard__text spanish">{result.recognized_text}</p>
        </div>
      )}

      <div className="words">
        {result.words.map((word) => (
          <span key={word.index} className="word spanish" data-matched={word.matched}>
            {word.expected}
          </span>
        ))}
      </div>

      <div className="disclosure">
        {sounds && (
          <button
            type="button"
            className="disclosure__toggle"
            onClick={() => setShowDetail((open) => !open)}
            aria-expanded={showDetail}
          >
            {showDetail ? t.feedback.soundDetailHide : t.feedback.soundDetail}
          </button>
        )}

        {showDetail && sounds && (
          <SoundStrip
            phonemes={result.phonemes}
            words={words}
            missedWords={missedWords}
            scored
          />
        )}

        <div className="disclosure__body">
          <button
            type="button"
            className="disclosure__toggle"
            onClick={() => setShowMethod((open) => !open)}
            aria-expanded={showMethod}
          >
            {t.feedback.methodLink}
          </button>
          {showMethod && (
            <>
              <p>{t.feedback.methodBody}</p>
              <p>{t.feedback.methodAccents}</p>
              {!sounds && <p>{t.feedback.methodNoSounds}</p>}
            </>
          )}
        </div>
      </div>

      <div className="feedback__actions">
        <Button variant="primary" onClick={onNext} shortcut="N">
          {t.practice.nextCard}
        </Button>
        <Button onClick={onRetry} shortcut="R">
          {t.practice.tryAgain}
        </Button>
        {canReplay && <Button variant="quiet" onClick={onReplay}>{t.practice.playback}</Button>}
      </div>
    </section>
  );
}
