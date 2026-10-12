import { t } from "../../i18n/en";
import { THEMES, useTheme, type Theme } from "../../lib/useTheme";

/**
 * Three explicit states rather than a two-way switch.
 *
 * A plain toggle cannot express "follow my system", which is what most people
 * actually want — and without it, a learner on a machine that flips at sunset
 * would have to flip the app too.
 *
 * Built on the same segmented-control shape as the playback speed selector, so
 * it is one idiom used twice rather than two inventions.
 */

const ICONS: Record<Theme, string> = {
  system: "◐",
  light: "○",
  dark: "●",
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="speed theme-toggle" role="group" aria-label={t.theme.label}>
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={theme === option}
          title={t.theme.options[option]}
          onClick={() => setTheme(option)}
        >
          <span aria-hidden="true">{ICONS[option]}</span>
          <span className="sr-only">{t.theme.options[option]}</span>
        </button>
      ))}
    </div>
  );
}
