import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { t } from "../i18n/en";
import { api, type HistoryRow, type MistakeRow, type Summary } from "../lib/api";
import { formatWhen, scoreBand } from "../lib/labels";
import { EmptyState } from "../components/ui/EmptyState";
import { Stat } from "../components/ui/Stat";

/**
 * What has been practised so far — kept to what a learner can act on.
 */
export default function Progress() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [mistakes, setMistakes] = useState<MistakeRow[]>([]);

  const [titles, setTitles] = useState<Record<string, string>>({});

  useEffect(() => {
    api.summary().then(setSummary).catch(() => undefined);
    api.history(20).then(setHistory).catch(() => undefined);
    api.mistakes(8).then(setMistakes).catch(() => undefined);
    // History only carries card ids. One deck fetch turns them into the Spanish
    // the learner actually practised, which is what makes the list readable.
    api
      .deck()
      .then((deck) =>
        setTitles(Object.fromEntries(deck.cards.map((c) => [c.id, c.text]))),
      )
      .catch(() => undefined);
  }, []);

  return (
    <>
      <section className="hero">
        <h1 className="hero__headline">{t.progress.title}</h1>
        <p className="hero__sub">{t.progress.subtitle}</p>
      </section>

      <div className="stats">
        <Stat value={summary?.total_attempts ?? "—"} label={t.progress.attempts} />
        <Stat value={summary?.cards_practised ?? "—"} label={t.progress.cardsPractised} />
        <Stat value={summary?.cards_mastered ?? "—"} label={t.progress.mastered} />
        <Stat value={summary?.average_score ?? "—"} label={t.progress.average} />
      </div>
      <p className="footnote">{t.progress.masteredHint}</p>

      <section className="section">
        <div className="section__head">
          <h2 className="label">{t.progress.recentTitle}</h2>
        </div>
        {history.length === 0 ? (
          <EmptyState
            title={t.progress.recentEmpty}
            body={t.home.subtitleNew}
            action={
              <Link to="/practice" className="btn btn--primary">
                {t.home.continueAction}
              </Link>
            }
          />
        ) : (
          <ol className="history">
            {history.map((row) => (
              <li className="history__row" key={row.id}>
                <span className="history__card spanish" lang="es">
                  {titles[row.card_id] ?? row.card_id}
                </span>
                <span className="history__score" data-band={scoreBand(row.practice_score)}>
                  {Math.round(row.practice_score)}
                </span>
                <span className="history__when">{formatWhen(row.created_at)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="section">
        <div className="section__head">
          <h2 className="label">{t.progress.mistakesTitle}</h2>
        </div>
        {mistakes.length === 0 ? (
          <p className="footnote">{t.progress.mistakesEmpty}</p>
        ) : (
          <ul className="topics">
            {mistakes.map((row, index) => (
              <li key={index} className="topic topic--static">
                <span className="spanish" lang="es">
                  {row.word ?? titles[row.card_id] ?? row.card_id}
                </span>
                <span className="topic__count measure">×{row.total}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
