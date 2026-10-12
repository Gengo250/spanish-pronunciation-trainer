import { NavLink, Outlet } from "react-router-dom";
import { t } from "../../i18n/en";
import { ThemeToggle } from "./ThemeToggle";

/**
 * The frame every screen sits in.
 *
 * The mark is four azulejo tiles rather than a logo image — the same tile
 * vocabulary used by the sound strip and the session progress, so the product
 * reads as one thing.
 */
export function AppShell() {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t.nav.skipToContent}
      </a>

      <header className="masthead">
        <div className="page masthead__inner">
          <NavLink to="/" className="wordmark">
            <span className="wordmark__tiles" aria-hidden="true">
              <i /><i /><i /><i />
            </span>
            {t.app.name}
          </NavLink>

          <div className="masthead__right">
            <nav className="nav" aria-label="Main">
              <NavLink to="/" end className="nav__link">
                {t.nav.home}
              </NavLink>
              <NavLink to="/practice" className="nav__link">
                {t.nav.practice}
              </NavLink>
              <NavLink to="/progress" className="nav__link">
                {t.nav.progress}
              </NavLink>
            </nav>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main id="main" className="main">
        <div className="page">
          <Outlet />
        </div>
      </main>

      <footer className="colophon">
        <div className="page colophon__inner">
          <span>{t.app.tagline}</span>
          <span>Practice scores support study. They do not certify proficiency.</span>
        </div>
      </footer>
    </div>
  );
}
