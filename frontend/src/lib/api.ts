/**
 * Backend client and the shapes it returns.
 *
 * The backend speaks in codes (`card_type`, `category`, `capabilities`,
 * finding `kind`). All human wording is composed in the interface from those
 * codes, which is what keeps the product's voice consistent and its copy in
 * one place.
 */

export type PhonemeStatus = "strong" | "fair" | "weak" | "unknown";

export type Phoneme = {
  index: number;
  phone: string;
  word_index: number;
  gop: number | null;
  status: PhonemeStatus;
};

export type Card = {
  id: string;
  text: string;
  translation: string;
  level: number;
  card_type: string;
  category: string;
  grammar_note: string | null;
  pronunciation_focus: string | null;
  example: string | null;
  example_translation: string | null;
  tags: string[];
  attempts: number;
  best_score: number | null;
  phonemes: Phoneme[];
};

export type FindingKind =
  | "word_not_recognized"
  | "weak_phoneme"
  | "speech_rate"
  | "pause"
  | "no_speech";

export type Finding = {
  kind: FindingKind | string;
  message: string;
  evidence: "transcript" | "phoneme_acoustic" | "prosody";
  severity: "info" | "minor" | "major";
  word: string | null;
  word_index: number | null;
  score: number | null;
};

export type AssessedWord = {
  index: number;
  expected: string;
  recognized: string | null;
  matched: boolean;
  mean_gop: number | null;
};

export type Assessment = {
  card_id: string;
  expected_text: string;
  recognized_text: string;
  no_speech_detected: boolean;
  audio_duration: number;
  scores: {
    word_accuracy: number;
    phoneme_accuracy: number | null;
    fluency: number | null;
    practice_score: number;
  };
  words: AssessedWord[];
  phonemes: Phoneme[];
  findings: Finding[];
  capabilities: string[];
  limitations: string[];
  summary: string;
};

export type Meta = {
  levels: { value: number; label: string }[];
  categories: string[];
  card_types: string[];
  pools: string[];
  orders: string[];
};

export type Summary = {
  total_attempts: number;
  cards_practised: number;
  cards_mastered: number;
  average_score: number | null;
  deck_size: number;
};

export type HistoryRow = {
  id: number;
  card_id: string;
  created_at: string;
  practice_score: number;
  word_accuracy: number;
  phoneme_accuracy: number | null;
  recognized_text: string;
  no_speech: number;
};

export type MistakeRow = { card_id: string; kind: string; word: string | null; total: number };

export type Health = {
  status: string;
  deck: string;
  cards: number;
  accent: string;
  tts_configured: boolean;
  phonemes_enabled: boolean;
};

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? `Request failed (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

export type CardQuery = {
  level?: number | null;
  category?: string | null;
  pool?: string;
  order?: string;
};

export function cardQueryToParams(query: CardQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.level) params.set("level", String(query.level));
  if (query.category) params.set("category", query.category);
  if (query.pool && query.pool !== "all") params.set("pool", query.pool);
  if (query.order) params.set("order", query.order);
  return params;
}

export const api = {
  health: async () => json<Health>(await fetch("/api/health")),
  meta: async () => json<Meta>(await fetch("/api/meta")),

  nextCard: async (query: CardQuery) =>
    json<Card>(await fetch(`/api/cards/next?${cardQueryToParams(query)}`)),

  card: async (id: string) => json<Card>(await fetch(`/api/cards/${encodeURIComponent(id)}`)),

  /** Reference audio. Served from cache after the first request for a card. */
  audioUrl: (cardId: string) => `/api/cards/${encodeURIComponent(cardId)}/audio`,

  submitAttempt: async (cardId: string, audio: Blob) => {
    const form = new FormData();
    form.append("audio", audio, "attempt.webm");
    return json<Assessment>(
      await fetch(`/api/cards/${encodeURIComponent(cardId)}/attempt`, {
        method: "POST",
        body: form,
      }),
    );
  },

  /** The whole deck. Used to turn card ids into readable Spanish. */
  deck: async () => json<{ cards: Card[] }>(await fetch("/api/content/export?fmt=json")),

  summary: async () => json<Summary>(await fetch("/api/progress/summary")),
  history: async (limit = 20) =>
    json<HistoryRow[]>(await fetch(`/api/progress/history?limit=${limit}`)),
  mistakes: async (limit = 8) =>
    json<MistakeRow[]>(await fetch(`/api/progress/mistakes?limit=${limit}`)),
};
