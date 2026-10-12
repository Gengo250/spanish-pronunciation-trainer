import { t } from "../../i18n/en";
import type { Phoneme } from "../../lib/api";

/**
 * The signature element: the expected pronunciation, one tile per sound.
 *
 * Unglazed before you speak, then each tile takes its colour from the acoustic
 * measurement — left to right, in the rhythm of the phrase. It is the one bold
 * thing on the screen, and it is also the only thing this product can do that
 * an ordinary flashcard app cannot.
 *
 * Tiles stay grey when the analysis did not run. Nothing is coloured on a
 * guess: an unmeasured sound looks unmeasured.
 */

type Props = {
  phonemes: Phoneme[];
  words: string[];
  missedWords: Set<number>;
  scored: boolean;
};

export function SoundStrip({ phonemes, words, missedWords, scored }: Props) {
  if (phonemes.length === 0) return null;

  return (
    <section
      className={`strip${scored ? "" : " strip--preview"}`}
      aria-label={t.a11y.soundStrip}
    >
      {/* Before you speak the strip is unlabelled and muted: it reads as the
          rhythm of the phrase, not as a technical readout. The heading and the
          legend only appear once the tiles carry a measurement. */}
      <div className="strip__head">
        {scored && <span className="label">{t.feedback.soundDetail}</span>}
        {scored && (
          <span className="legend">
            <span>
              <i className="legend__swatch legend__swatch--strong" />
              {t.feedback.legendClear}
            </span>
            <span>
              <i className="legend__swatch legend__swatch--fair" />
              {t.feedback.legendClose}
            </span>
            <span>
              <i className="legend__swatch legend__swatch--weak" />
              {t.feedback.legendWork}
            </span>
          </span>
        )}
      </div>

      <div className="strip__words">
        {words.map((word, wordIndex) => {
          const sounds = phonemes.filter((p) => p.word_index === wordIndex);
          if (sounds.length === 0) return null;
          const missed = missedWords.has(wordIndex);
          return (
            <div className="strip__word" key={`${word}-${wordIndex}`}>
              <div className="strip__tiles">
                {sounds.map((sound) => {
                  const measured = scored && sound.status !== "unknown";
                  const classes = [
                    "glyph",
                    measured ? "glyph--scored" : "",
                    measured ? `glyph--${sound.status}` : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <span
                      key={sound.index}
                      className={classes}
                      style={{ ["--i" as string]: sound.index }}
                    >
                      {sound.phone}
                    </span>
                  );
                })}
              </div>
              <span className={`strip__label${missed ? " strip__label--missed" : ""}`}>
                {word}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
