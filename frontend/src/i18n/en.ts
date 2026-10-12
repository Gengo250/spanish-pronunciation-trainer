/**
 * Every user-facing string in the interface.
 *
 * Two languages live in this product and they must never blur: the INTERFACE is
 * English, the CONTENT being learned is Spanish. Nothing in this file is ever
 * Spanish — card text, translations and phonemes all arrive from the backend.
 *
 * Centralised so a second interface language is a new file, not a search across
 * components. Backend messages are not rendered directly; the UI composes its
 * own copy from the structured fields of a result, which keeps wording
 * consistent and lets the same payload read differently in different places.
 */

export const en = {
  app: {
    name: "Hablar",
    tagline: "Spanish pronunciation practice",
  },

  theme: {
    label: "Colour theme",
    options: {
      system: "Match system",
      light: "Light",
      dark: "Dark",
    },
  },

  nav: {
    home: "Home",
    practice: "Practice",
    progress: "Progress",
    skipToContent: "Skip to main content",
  },

  home: {
    greetingMorning: "Buenos días",
    greetingAfternoon: "Buenas tardes",
    greetingEvening: "Buenas noches",
    headline: "Practise Spanish out loud.",
    subtitleNew: "Hear a phrase, say it back, and see which sounds landed.",
    subtitleReturning: "Pick up where you left off.",
    continueTitle: "Start practising",
    continueAction: "Start a session",
    continueHint: (cards: number) => `${cards} cards in this session`,
    levelsTitle: "Choose a level",
    topicsTitle: "Pick a topic",
    topicsAll: "All topics",
    clearTopic: "Clear topic",
    anyLevel: "Any level",
    cardsCount: (done: number, total: number) => `${done} of ${total} cards practised`,
    levelCards: (n: number) => `${n} cards`,
  },

  levels: {
    1: "Beginner",
    2: "Intermediate",
    3: "Advanced",
    descriptions: {
      1: "Greetings, numbers, colours and everyday words.",
      2: "Full sentences, past and present, travel and conversation.",
      3: "Idioms, complex grammar and natural phrasing.",
    },
  },

  /** Card kinds, as the learner should understand them. */
  cardTypes: {
    vocabulary: "Word",
    phrase: "Phrase",
    sentence: "Sentence",
    question: "Question",
    expression: "Expression",
    verb: "Verb",
    pronunciation: "Sound drill",
    intonation: "Intonation",
  },

  topics: {
    greetings: "Greetings",
    numbers: "Numbers",
    colors: "Colours",
    objects: "Objects",
    food: "Food",
    family: "Family",
    travel: "Travel",
    daily_life: "Daily life",
    work: "Work",
    feelings: "Feelings",
    time: "Time",
    grammar: "Grammar",
    idioms: "Idioms",
    culture: "Culture",
    sounds: "Tricky sounds",
  },

  practice: {
    sessionOf: (current: number, total: number) => `Card ${current} of ${total}`,
    endSession: "End session",
    listen: "Listen",
    listenAgain: "Listen again",
    speed: "Playback speed",
    speedLabel: (rate: number) => `${rate}× speed`,
    speak: "Speak",
    stop: "Stop",
    recording: "Recording",
    processing: "Checking your pronunciation",
    playback: "Hear your recording",
    showTranslation: "Show translation",
    hideTranslation: "Hide translation",
    tryAgain: "Try again",
    nextCard: "Next card",
    focusLabel: "Focus",
    loading: "Loading your next card",
    keyboardHint: "Space to record · L to listen · T for translation · N for next",
  },

  recorder: {
    ready: "Ready when you are",
    requesting: "Waiting for microphone access",
    denied: "Microphone blocked. Allow access in your browser, then try again.",
    unsupported: "This browser cannot record audio. Try Chrome, Edge or Firefox.",
    failed: "The recording could not be sent. Try once more.",
  },

  feedback: {
    title: "How that sounded",
    heardLabel: "We heard",
    scoreLabel: "Practice score",
    wordsLabel: "Words",
    soundsLabel: "Sounds",
    paceLabel: "Pace",
    soundDetail: "Sound-by-sound detail",
    soundDetailHide: "Hide detail",
    legendClear: "Clear",
    legendClose: "Close",
    legendWork: "Needs work",
    noSpeech: "We did not hear anything. Check your microphone and record again.",
    /** Headlines are chosen from the measurement, never from a guess. */
    headlineExcellent: "Clear all the way through.",
    headlineGood: "Close. A couple of sounds are worth another pass.",
    headlineMixed: "Some of that came through. Listen once more and repeat.",
    headlinePoor: "That did not match yet. Play the reference and copy it closely.",
    allWordsHeard: (n: number) => `All ${n} words came through.`,
    someWordsMissed: (n: number) =>
      n === 1 ? "One word did not come through." : `${n} words did not come through.`,
    pacingSlow: "You spoke more slowly than the reference.",
    pacingFast: "You spoke faster than the reference.",
    pausedAfter: (word: string) => `You paused after “${word}”.`,
    soundsWeak: (word: string) => `Worth repeating “${word}” slowly.`,
    wordMissed: (word: string) => `“${word}” was not recognised.`,
    methodLink: "How is this measured?",
    methodTitle: "How this is measured",
    methodBody:
      "Your recording is compared with the reference audio for this card, sound by sound. " +
      "A practice score is a study aid — it is not a proficiency assessment, and it does not " +
      "certify anything.",
    methodNoSounds:
      "Sound-by-sound analysis is off for this attempt, so the feedback covers the words and " +
      "your pacing only.",
    methodAccents:
      "Regional Spanish is not marked wrong. Seseo, yeísmo and softened consonants all count " +
      "as correct.",
  },

  summary: {
    title: "Session complete",
    cardsPractised: (n: number) => `${n} cards practised`,
    averageScore: "Average score",
    bestCard: "Strongest card",
    reviewCard: "Worth revisiting",
    again: "Practise again",
    home: "Back to home",
  },

  progress: {
    title: "Your progress",
    subtitle: "Everything you have practised so far.",
    attempts: "Attempts",
    cardsPractised: "Cards practised",
    mastered: "Mastered",
    average: "Average score",
    masteredHint: "A card counts as mastered once you score 80 or above.",
    recentTitle: "Recent attempts",
    recentEmpty: "Nothing here yet. Finish a session and it will show up.",
    mistakesTitle: "Comes up often",
    mistakesEmpty: "No repeated trouble spots yet.",
    deckCoverage: (done: number, total: number) => `${done} of ${total} cards`,
  },

  settings: {
    title: "Practice settings",
    level: "Level",
    topic: "Topic",
    deck: "Cards",
    order: "Order",
    sessionLength: "Session length",
    anyLevel: "Any level",
    anyTopic: "Any topic",
    pools: {
      all: "All cards",
      new: "New to me",
      seen: "Already practised",
      struggling: "Needs more work",
    },
    orders: {
      random: "Shuffled",
      adaptive: "Adapt to me",
      sequential: "In order",
    },
    cards: (n: number) => `${n} cards`,
  },

  empty: {
    noCardsTitle: "No cards match those choices",
    noCardsBody: "Widen the level or topic and try again.",
    noCardsAction: "Clear filters",
  },

  errors: {
    loadCard: "That card could not be loaded.",
    playAudio: "The reference audio would not play.",
    assess: "Your recording could not be checked.",
    generic: "Something went wrong.",
    retry: "Try again",
  },

  a11y: {
    sessionProgress: "Session progress",
    soundStrip: "Expected pronunciation, sound by sound",
    recordButton: "Record your pronunciation",
    stopButton: "Stop recording and check",
    playReference: "Play the reference pronunciation",
    playOwn: "Play your own recording",
    scoreOutOf: (score: number) => `Practice score ${score} out of 100`,
  },
} as const;

export type Strings = typeof en;
export const t = en;
