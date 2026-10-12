import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { t } from "../i18n/en";
import { api, type Card, type Meta, type Summary } from "../lib/api";
import { greeting, levelDescription, levelName, topicName } from "../lib/labels";
import { DEFAULT_SESSION_LENGTH } from "../lib/useSession";
import { Button } from "../components/ui/Button";
import { ProgressBar } from "../components/ui/ProgressBar";
import { Stat } from "../components/ui/Stat";

const LEVELS = [1, 2, 3] as const;

/**
 * Home answers one question: what should I practise right now?
 *
 * Deliberately not an analytics dashboard. Two ways in, and they compose: a
 * topic chip narrows the deck and is reflected in the start panel, while a
 * level tile begins immediately with that narrowing applied. Whatever is
 * selected, the panel states exactly what the primary button will start —
 * nothing on the page starts something the page did not describe.
 */
export default function Home() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [topic, setTopic] = useState<string | null>(null);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => undefined);
    api.meta().then(setMeta).catch(() => undefined);
    // One deck fetch gives each level tile a real card count, so the choice is
    // informed rather than three identical-looking buttons.
    api.deck().then((deck) => setCards(deck.cards)).catch(() => undefined);
  }, []);

  const hello = useMemo(() => greeting(new Date()), []);
  const returning = (summary?.total_attempts ?? 0) > 0;

  const countFor = (level?: number) =>
    cards.filter((c) => (!level || c.level === level) && (!topic || c.category === topic)).length;

  const start = (level?: number) => {
    const params = new URLSearchParams({
      pool: "all",
      order: "adaptive",
      length: String(DEFAULT_SESSION_LENGTH),
    });
    if (level) params.set("level", String(level));
    if (topic) params.set("topic", topic);
    navigate(`/practice?${params}`);
  };

  const selection = [topic ? topicName(topic) : t.home.topicsAll].join(" · ");

  return (
    <>
      <section className="hero">
        <p className="hero__greeting spanish" lang="es">
          {hello}
        </p>
        <h1 className="hero__headline">{t.home.headline}</h1>
        <p className="hero__sub">
          {returning ? t.home.subtitleReturning : t.home.subtitleNew}
        </p>
      </section>

      <div className="home-grid">
        <section className="tile start-panel">
          <span className="label">{t.home.continueTitle}</span>
          <p className="start-panel__selection">
            {t.home.anyLevel} <span aria-hidden="true">·</span> {selection}
          </p>

          {summary && (
            <div className="start-panel__progress">
              <ProgressBar
                value={summary.cards_practised}
                max={summary.deck_size}
                label={t.home.cardsCount(summary.cards_practised, summary.deck_size)}
              />
              <p className="start-panel__meta">
                {t.home.cardsCount(summary.cards_practised, summary.deck_size)}
              </p>
            </div>
          )}

          <Button variant="primary" size="lg" onClick={() => start()}>
            {t.home.continueAction}
          </Button>
        </section>

        <div className="stats">
          <Stat value={summary?.total_attempts ?? "—"} label={t.progress.attempts} />
          <Stat value={summary?.cards_mastered ?? "—"} label={t.progress.mastered} />
          <Stat value={summary?.average_score ?? "—"} label={t.progress.average} />
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="label">{t.home.levelsTitle}</h2>
        </div>
        <div className="levels">
          {LEVELS.map((level) => (
            <button
              key={level}
              className="tile tile--action level-tile"
              onClick={() => start(level)}
            >
              <div className="level-tile__top">
                <span className="level-tile__name">{levelName(level)}</span>
                <span className="depth" data-level={level} aria-hidden="true">
                  <i /><i /><i />
                </span>
              </div>
              <p className="level-tile__desc">{levelDescription(level)}</p>
              {cards.length > 0 && (
                <span className="level-tile__count measure">
                  {t.home.levelCards(countFor(level))}
                </span>
              )}
            </button>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <h2 className="label">{t.home.topicsTitle}</h2>
          {topic && (
            <button className="btn btn--quiet" onClick={() => setTopic(null)}>
              {t.home.clearTopic}
            </button>
          )}
        </div>
        <div className="topics">
          {(meta?.categories ?? []).map((code) => (
            <button
              key={code}
              type="button"
              className="topic"
              aria-pressed={topic === code}
              onClick={() => setTopic(topic === code ? null : code)}
            >
              {topicName(code)}
            </button>
          ))}
        </div>
      </section>
    </>
  );
}
