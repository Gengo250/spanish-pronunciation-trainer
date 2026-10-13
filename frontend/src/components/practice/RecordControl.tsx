import { t } from "../../i18n/en";
import type { RecorderState } from "../../lib/useRecorder";

/**
 * One control, four states, each visibly different.
 *
 * The learner should be able to tell from across a desk whether the microphone
 * is waiting on permission, actually recording, or busy checking. The previous
 * version only toggled a label, so "nothing is happening" and "it is thinking"
 * looked identical.
 */

type Props = {
  state: RecorderState;
  elapsed: number;
  processing: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
};

/** The key that starts and stops a recording, mirrored in the keydown handler. */
const RECORD_KEY = "Space";

export function RecordControl({ state, elapsed, processing, disabled, onStart, onStop }: Props) {
  const visual = processing ? "processing" : state;
  const recording = state === "recording";

  const label =
    visual === "processing"
      ? t.practice.processing
      : visual === "requesting"
        ? t.recorder.requesting
        : recording
          ? t.practice.stop
          : t.practice.speak;

  const busy = visual === "processing" || visual === "requesting";
  // Only on the state the badge describes: while recording the timer has the
  // slot, and while busy the shortcut is ignored anyway.
  const showKey = !busy && !recording;

  return (
    <button
      type="button"
      className="rec"
      data-state={visual}
      disabled={disabled || busy}
      onClick={recording ? onStop : onStart}
      aria-label={recording ? t.a11y.stopButton : t.a11y.recordButton}
      aria-keyshortcuts={RECORD_KEY}
    >
      {visual === "processing" ? (
        <span className="spinner" aria-hidden="true" />
      ) : (
        <span className="rec__dot" aria-hidden="true" />
      )}
      <span>{label}</span>
      {recording && <span className="rec__timer">{elapsed.toFixed(1)}s</span>}
      {showKey && (
        <kbd className="rec__key" aria-hidden="true">
          {RECORD_KEY}
        </kbd>
      )}
    </button>
  );
}
