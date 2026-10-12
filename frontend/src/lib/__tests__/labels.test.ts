import { describe, expect, it } from "vitest";
import type { Assessment } from "../api";
import { cardWords, formatPercent, greeting, headline, hasSoundAnalysis, notes, scoreBand } from "../labels";

/**
 * The interface composes its own copy from structured results rather than
 * echoing the backend. These tests guard the rule that matters most: the words
 * on screen never claim more than was measured.
 */

function assessment(overrides: Partial<Assessment> = {}): Assessment {
  return {
    card_id: "c1",
    expected_text: "Buenos días",
    recognized_text: "Buenos días",
    no_speech_detected: false,
    audio_duration: 1.4,
    scores: { word_accuracy: 1, phoneme_accuracy: 0.9, fluency: 1, practice_score: 96 },
    words: [
      { index: 0, expected: "Buenos", recognized: "buenos", matched: true, mean_gop: -0.1 },
      { index: 1, expected: "días", recognized: "días", matched: true, mean_gop: -0.2 },
    ],
    phonemes: [],
    findings: [],
    capabilities: ["transcript_match", "prosody_analysis", "phoneme_analysis"],
    limitations: [],
    summary: "",
    ...overrides,
  };
}

describe("headline", () => {
  it("celebrates a clean attempt", () => {
    expect(headline(assessment())).toMatch(/Clear all the way/);
  });

  it("stays measured when words were missed", () => {
    const result = assessment({
      scores: { word_accuracy: 0.5, phoneme_accuracy: 0.6, fluency: 1, practice_score: 48 },
      words: [
        { index: 0, expected: "Buenos", recognized: null, matched: false, mean_gop: null },
        { index: 1, expected: "días", recognized: "días", matched: true, mean_gop: -0.2 },
      ],
    });
    expect(headline(result)).toMatch(/Listen once more|did not match/);
  });

  it("asks for another recording when nothing was heard", () => {
    expect(headline(assessment({ no_speech_detected: true }))).toMatch(/did not hear/i);
  });
});

describe("notes", () => {
  it("says how many words came through", () => {
    expect(notes(assessment())[0]).toBe("All 2 words came through.");
  });

  it("uses the singular for a single missed word", () => {
    const result = assessment({
      words: [
        { index: 0, expected: "Buenos", recognized: null, matched: false, mean_gop: null },
        { index: 1, expected: "días", recognized: "días", matched: true, mean_gop: -0.2 },
      ],
    });
    expect(notes(result)).toContain("One word did not come through.");
  });

  it("never mentions a sound when the acoustic analysis did not run", () => {
    const result = assessment({ capabilities: ["transcript_match"], findings: [] });
    expect(hasSoundAnalysis(result)).toBe(false);
    expect(notes(result).join(" ")).not.toMatch(/sound|repeating/i);
  });

  it("names a word only when a measured finding points at it", () => {
    const result = assessment({
      findings: [
        {
          kind: "weak_phoneme",
          message: "",
          evidence: "phoneme_acoustic",
          severity: "minor",
          word: "días",
          word_index: 1,
          score: -3.1,
        },
      ],
    });
    expect(notes(result).join(" ")).toContain("“días”");
  });

  it("reports pacing in the direction that was measured", () => {
    const slow = assessment({
      findings: [
        { kind: "speech_rate", message: "", evidence: "prosody", severity: "minor", word: null, word_index: null, score: 0.5 },
      ],
    });
    expect(notes(slow).join(" ")).toMatch(/more slowly/);

    const fast = assessment({
      findings: [
        { kind: "speech_rate", message: "", evidence: "prosody", severity: "minor", word: null, word_index: null, score: 1.8 },
      ],
    });
    expect(notes(fast).join(" ")).toMatch(/faster/);
  });

  it("produces nothing to read when no speech was detected", () => {
    expect(notes(assessment({ no_speech_detected: true }))).toEqual([]);
  });
});

describe("scoreBand", () => {
  it("matches the thresholds used for colour", () => {
    expect(scoreBand(96)).toBe("high");
    expect(scoreBand(80)).toBe("high");
    expect(scoreBand(60)).toBe("mid");
    expect(scoreBand(20)).toBe("low");
  });
});

describe("cardWords", () => {
  it("strips Spanish punctuation so words align with the sound strip", () => {
    expect(cardWords({ text: "¿Cómo estás?" })).toEqual(["Cómo", "estás"]);
  });
});

describe("greeting", () => {
  it("is Spanish, because it is content rather than interface", () => {
    expect(greeting(new Date(2026, 0, 1, 9))).toBe("Buenos días");
    expect(greeting(new Date(2026, 0, 1, 15))).toBe("Buenas tardes");
    expect(greeting(new Date(2026, 0, 1, 22))).toBe("Buenas noches");
  });
});

describe("formatPercent", () => {
  it("shows a dash when a measurement is absent", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(0.9)).toBe("90%");
  });
});
