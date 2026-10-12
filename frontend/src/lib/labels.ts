/**
 * Turns backend codes into the words a learner reads.
 *
 * Kept apart from the strings file because this is mapping logic, not copy:
 * the wording lives in `i18n/en.ts`, and these helpers only decide which of it
 * applies.
 */

import { t } from "../i18n/en";
import type { Assessment, Card, Finding } from "./api";

export function levelName(level: number): string {
  return t.levels[level as 1 | 2 | 3] ?? `Level ${level}`;
}

export function levelDescription(level: number): string {
  return t.levels.descriptions[level as 1 | 2 | 3] ?? "";
}

export function cardTypeName(code: string): string {
  return (t.cardTypes as Record<string, string>)[code] ?? humanise(code);
}

export function topicName(code: string): string {
  return (t.topics as Record<string, string>)[code] ?? humanise(code);
}

function humanise(code: string): string {
  const spaced = code.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Spanish greeting on the home screen, chosen by the hour. */
export function greeting(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return t.home.greetingMorning;
  if (hour < 20) return t.home.greetingAfternoon;
  return t.home.greetingEvening;
}

export type ScoreBand = "high" | "mid" | "low";

export function scoreBand(score: number): ScoreBand {
  if (score >= 80) return "high";
  if (score >= 55) return "mid";
  return "low";
}

/**
 * One sentence describing the attempt.
 *
 * Driven by what was actually measured — never a guess. The thresholds match
 * the bands used elsewhere so the headline and the score never disagree.
 */
export function headline(result: Assessment): string {
  if (result.no_speech_detected) return t.feedback.noSpeech;
  const missed = result.words.filter((w) => !w.matched).length;
  const score = result.scores.practice_score;
  if (missed === 0 && score >= 85) return t.feedback.headlineExcellent;
  if (missed === 0 || score >= 70) return t.feedback.headlineGood;
  if (score >= 40) return t.feedback.headlineMixed;
  return t.feedback.headlinePoor;
}

/**
 * The supporting notes under the headline.
 *
 * Composed from structured findings rather than the backend's own prose, so
 * wording stays in one language and one voice. Sound-level notes are only ever
 * produced when the acoustic analysis actually ran.
 */
export function notes(result: Assessment): string[] {
  if (result.no_speech_detected) return [];

  const out: string[] = [];
  const missed = result.words.filter((w) => !w.matched);
  out.push(
    missed.length === 0
      ? t.feedback.allWordsHeard(result.words.length)
      : t.feedback.someWordsMissed(missed.length),
  );

  const soundFindings = result.findings.filter((f) => f.evidence === "phoneme_acoustic");
  for (const finding of soundFindings.slice(0, 2)) {
    if (finding.word) out.push(t.feedback.soundsWeak(finding.word));
  }

  const rate = result.findings.find((f) => f.kind === "speech_rate");
  if (rate) {
    out.push((rate.score ?? 1) < 1 ? t.feedback.pacingSlow : t.feedback.pacingFast);
  }

  const pause = result.findings.find((f) => f.kind === "pause");
  if (pause?.word) out.push(t.feedback.pausedAfter(pause.word));

  return out;
}

export function hasSoundAnalysis(result: Assessment): boolean {
  return result.capabilities.includes("phoneme_analysis");
}

/** Words of the card, punctuation stripped, aligned with the sound strip. */
export function cardWords(card: Pick<Card, "text">): string[] {
  return card.text
    .replace(/[¿?¡!.,;:]/g, "")
    .split(/\s+/)
    .filter(Boolean);
}

export function findingWords(findings: Finding[], kind: string): string[] {
  return findings.filter((f) => f.kind === kind && f.word).map((f) => f.word as string);
}

export function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function formatWhen(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
