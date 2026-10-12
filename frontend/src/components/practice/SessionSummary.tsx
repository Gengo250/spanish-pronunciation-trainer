import { t } from "../../i18n/en";
import type { useSession } from "../../lib/useSession";
import { scoreBand } from "../../lib/labels";
import { Button } from "../ui/Button";

/**
 * The end of a session.
 *
 * The old interface never finished — cards just kept coming. A closing screen
 * is what turns practice into something you can complete, and it is the one
 * place a score is worth showing at size.
 */

type Props = {
  session: ReturnType<typeof useSession>;
  onAgain: () => void;
  onHome: () => void;
};

export function SessionSummary({ session, onAgain, onHome }: Props) {
  const average = session.average ?? 0;

  return (
    <section className="summary">
      <h1 className="summary__title spanish">¡Hecho!</h1>
      <p className="summary__sub">{t.summary.title}</p>

      <div className="stats">
        <div className="stat">
          <div className="stat__value" data-band={scoreBand(average)}>
            {session.average === null ? "—" : average}
          </div>
          <div className="stat__label label">{t.summary.averageScore}</div>
        </div>
        <div className="stat">
          <div className="stat__value">{session.entries.length}</div>
          <div className="stat__label label">{t.progress.cardsPractised}</div>
        </div>
      </div>

      {session.best && (
        <div className="tile tile--sunk summary__card">
          <span className="label">{t.summary.bestCard}</span>
          <p className="spanish" lang="es">{session.best.text}</p>
        </div>
      )}

      {session.weakest && session.weakest.score < 80 && (
        <div className="tile tile--sunk summary__card">
          <span className="label">{t.summary.reviewCard}</span>
          <p className="spanish" lang="es">{session.weakest.text}</p>
        </div>
      )}

      <div className="summary__actions">
        <Button variant="primary" size="lg" onClick={onAgain}>
          {t.summary.again}
        </Button>
        <Button size="lg" onClick={onHome}>
          {t.summary.home}
        </Button>
      </div>
    </section>
  );
}
