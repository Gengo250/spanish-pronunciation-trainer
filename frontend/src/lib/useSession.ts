import { useCallback, useState } from "react";

/**
 * A practice session: a fixed run of cards with an end.
 *
 * The previous interface streamed cards forever — nothing started, nothing
 * finished, and there was no moment of "done". A session gives the learner a
 * visible finish line and a summary worth reaching.
 */

export type SessionEntry = { cardId: string; text: string; score: number };

export const SESSION_LENGTHS = [5, 10, 20] as const;
export const DEFAULT_SESSION_LENGTH = 10;

export function useSession(length: number) {
  const [entries, setEntries] = useState<SessionEntry[]>([]);
  const [index, setIndex] = useState(0);

  const record = useCallback((entry: SessionEntry) => {
    setEntries((previous) =>
      previous.some((e) => e.cardId === entry.cardId)
        ? previous.map((e) => (e.cardId === entry.cardId ? entry : e))
        : [...previous, entry],
    );
  }, []);

  const advance = useCallback(() => setIndex((i) => i + 1), []);

  const restart = useCallback(() => {
    setEntries([]);
    setIndex(0);
  }, []);

  const complete = index >= length;
  const average =
    entries.length === 0
      ? null
      : Math.round((entries.reduce((sum, e) => sum + e.score, 0) / entries.length) * 10) / 10;

  const sorted = [...entries].sort((a, b) => b.score - a.score);

  return {
    entries,
    index,
    length,
    complete,
    average,
    best: sorted[0] ?? null,
    weakest: sorted.length > 1 ? sorted[sorted.length - 1] : null,
    record,
    advance,
    restart,
  };
}
