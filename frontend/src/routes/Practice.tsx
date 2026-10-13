import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { t } from "../i18n/en";
import { api, ApiError, type Assessment, type Card } from "../lib/api";
import { cardTypeName, cardWords, levelName, topicName } from "../lib/labels";
import { useRecorder } from "../lib/useRecorder";
import { DEFAULT_SESSION_LENGTH, useSession } from "../lib/useSession";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { Notice } from "../components/ui/Notice";
import { FeedbackPanel } from "../components/practice/FeedbackPanel";
import { RecordControl } from "../components/practice/RecordControl";
import { SoundStrip } from "../components/practice/SoundStrip";
import { SessionSummary } from "../components/practice/SessionSummary";

const SPEEDS = [1, 0.75, 0.5] as const;

/**
 * The practice loop: listen, speak, read the feedback, move on.
 *
 * Slower playback is applied in the browser rather than asked of the speech
 * service, so practising a phrase slowly costs nothing.
 */
export default function Practice() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const query = useMemo(
    () => ({
      level: params.get("level") ? Number(params.get("level")) : null,
      category: params.get("topic"),
      pool: params.get("pool") ?? "all",
      order: params.get("order") ?? "adaptive",
    }),
    [params],
  );
  const length = Number(params.get("length")) || DEFAULT_SESSION_LENGTH;

  const session = useSession(length);
  const recorder = useRecorder();

  const [card, setCard] = useState<Card | null>(null);
  const [result, setResult] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTranslation, setShowTranslation] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [ownAudio, setOwnAudio] = useState<string | null>(null);

  const referenceRef = useRef<HTMLAudioElement | null>(null);
  const ownRef = useRef<HTMLAudioElement | null>(null);

  const releaseOwnAudio = useCallback(() => {
    setOwnAudio((url) => {
      if (url) URL.revokeObjectURL(url);
      return null;
    });
  }, []);

  const loadCard = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setShowTranslation(false);
    releaseOwnAudio();
    recorder.reset();
    try {
      setCard(await api.nextCard(query));
    } catch (err) {
      setCard(null);
      setError(err instanceof ApiError ? err.message : t.errors.loadCard);
    } finally {
      setLoading(false);
    }
  }, [query, releaseOwnAudio, recorder]);

  useEffect(() => {
    void loadCard();
    // Only when the session's filters change; loadCard is stable per query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  // Revoke the last recording when leaving the screen.
  useEffect(() => releaseOwnAudio, [releaseOwnAudio]);

  const playReference = useCallback(() => {
    const audio = referenceRef.current;
    if (!audio) return;
    audio.playbackRate = speed;
    audio.currentTime = 0;
    audio.play().catch(() => setError(t.errors.playAudio));
  }, [speed]);

  const submit = useCallback(
    async (blob: Blob) => {
      if (!card) return;
      setProcessing(true);
      setError(null);
      try {
        const assessment = await api.submitAttempt(card.id, blob);
        setResult(assessment);
        session.record({
          cardId: card.id,
          text: card.text,
          score: assessment.scores.practice_score,
        });
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t.errors.assess);
      } finally {
        setProcessing(false);
      }
    },
    [card, session],
  );

  const startRecording = useCallback(async () => {
    setError(null);
    releaseOwnAudio();
    await recorder.start();
  }, [recorder, releaseOwnAudio]);

  const stopRecording = useCallback(async () => {
    const blob = await recorder.stop();
    if (!blob) return;
    setOwnAudio(URL.createObjectURL(blob));
    await submit(blob);
  }, [recorder, submit]);

  const retry = useCallback(() => {
    setResult(null);
    setError(null);
    releaseOwnAudio();
  }, [releaseOwnAudio]);

  const next = useCallback(() => {
    session.advance();
    void loadCard();
  }, [session, loadCard]);

  // Keyboard path through the loop. Hundreds of repetitions make this the
  // difference between practising and operating a form.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      // Holding a key down would otherwise start and stop a recording in a loop.
      if (event.repeat) return;

      const key = event.key.toLowerCase();
      if (event.code === "Space") {
        event.preventDefault();
        if (processing) return;
        void (recorder.recording ? stopRecording() : startRecording());
      } else if (key === "l") {
        playReference();
      } else if (key === "t") {
        setShowTranslation((shown) => !shown);
      } else if (key === "n" && result) {
        next();
      } else if (key === "r" && result) {
        retry();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [recorder.recording, processing, result, startRecording, stopRecording, playReference, next, retry]);

  if (session.complete) {
    return (
      <SessionSummary
        session={session}
        onAgain={() => {
          session.restart();
          void loadCard();
        }}
        onHome={() => navigate("/")}
      />
    );
  }

  const words = card ? cardWords(card) : [];
  const missedWords = new Set(
    (result?.words ?? []).filter((w) => !w.matched).map((w) => w.index),
  );
  const phonemes = result?.phonemes.length ? result.phonemes : (card?.phonemes ?? []);

  return (
    <div className="practice" data-phase={result ? "feedback" : "speak"}>
      <div className="session-bar">
        <Link to="/" className="btn btn--quiet">
          {t.practice.endSession}
        </Link>
        <div className="pips" role="progressbar" aria-label={t.a11y.sessionProgress}
             aria-valuenow={session.index} aria-valuemin={0} aria-valuemax={session.length}>
          {Array.from({ length: session.length }, (_, i) => {
            const entry = session.entries[i];
            const state =
              i === session.index ? "current" : entry ? (entry.score >= 80 ? "done" : "review") : "todo";
            return <i key={i} data-state={state} />;
          })}
        </div>
        <span className="session-bar__count">
          {t.practice.sessionOf(session.index + 1, session.length)}
        </span>
      </div>

      {error && <Notice tone="error">{error}</Notice>}
      {recorder.state === "denied" && <Notice tone="error">{t.recorder.denied}</Notice>}
      {recorder.state === "unsupported" && <Notice tone="error">{t.recorder.unsupported}</Notice>}

      {!card && !loading && !error && (
        <EmptyState
          title={t.empty.noCardsTitle}
          body={t.empty.noCardsBody}
          action={
            <Link to="/" className="btn btn--primary">
              {t.empty.noCardsAction}
            </Link>
          }
        />
      )}

      {card && (
        <article className="card-stage">
          <div className="card-stage__eyebrow label">
            <span>{levelName(card.level)}</span>
            <i aria-hidden="true">·</i>
            <span>{topicName(card.category)}</span>
            <i aria-hidden="true">·</i>
            <span>{cardTypeName(card.card_type)}</span>
          </div>

          <h1 className="prompt spanish" lang="es" key={card.id}>
            {card.text}
          </h1>

          <div className="translation">
            {showTranslation ? (
              <div className="translation__pair">
                <span className="label">{t.practice.translationPt}</span>
                <p className="translation__text" lang="pt-BR">{card.translation}</p>
                {card.translation_en && (
                  <>
                    <span className="label">{t.practice.translationEn}</span>
                    <p className="translation__text" lang="en">{card.translation_en}</p>
                  </>
                )}
              </div>
            ) : (
              <Button variant="quiet" onClick={() => setShowTranslation(true)} shortcut="T">
                {t.practice.showTranslation}
              </Button>
            )}
          </div>

          {!result && (
            <SoundStrip
              phonemes={phonemes}
              words={words}
              missedWords={missedWords}
              scored={false}
            />
          )}

          {card.pronunciation_focus && !result && (
            <p className="focus-note">
              <span className="label">{t.practice.focusLabel}</span> {card.pronunciation_focus}
            </p>
          )}

          <div className="controls">
            <div className="controls__secondary">
              <Button onClick={playReference} shortcut="L">
                {t.practice.listen}
              </Button>
              <div className="speed" role="group" aria-label={t.practice.speed}>
                {SPEEDS.map((rate) => (
                  <button
                    key={rate}
                    type="button"
                    aria-pressed={speed === rate}
                    aria-label={t.practice.speedLabel(rate)}
                    onClick={() => setSpeed(rate)}
                  >
                    {rate}×
                  </button>
                ))}
              </div>
            </div>

            <RecordControl
              state={recorder.state}
              elapsed={recorder.elapsed}
              processing={processing}
              disabled={loading}
              onStart={startRecording}
              onStop={stopRecording}
            />
          </div>

          <p className="hint">{t.practice.keyboardHint}</p>

          {result && (
            <FeedbackPanel
              result={result}
              words={words}
              onRetry={retry}
              onNext={next}
              canReplay={Boolean(ownAudio)}
              onReplay={() => ownRef.current?.play()}
            />
          )}

          {/* preload="none" keeps browsing cards from spending speech credits. */}
          <audio ref={referenceRef} src={api.audioUrl(card.id)} preload="none" />
          {ownAudio && <audio ref={ownRef} src={ownAudio} preload="auto" />}
        </article>
      )}
    </div>
  );
}
