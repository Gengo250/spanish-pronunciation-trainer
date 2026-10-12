import { useCallback, useEffect, useState } from "react";

/**
 * Light, dark, or whatever the system is doing.
 *
 * "system" is the default and is represented by the ABSENCE of `data-theme`,
 * so the `prefers-color-scheme` rule in the stylesheet takes over. The two
 * explicit choices set the attribute and therefore win over the OS — which is
 * the whole point of offering the control.
 *
 * The stored value is read again by a small inline script in index.html before
 * the first paint. Without that, a learner who picked dark would get a flash of
 * the light palette on every reload.
 */

export type Theme = "system" | "light" | "dark";

export const THEME_KEY = "hablar-theme";
export const THEMES: Theme[] = ["system", "light", "dark"];

function read(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read);

  useEffect(() => {
    apply(theme);
    try {
      if (theme === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Private browsing can refuse storage; the choice simply will not persist.
    }
  }, [theme]);

  // While following the system, track changes to it so the page flips with the
  // OS instead of waiting for a reload.
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);

  return {
    theme,
    setTheme,
    /** What is actually on screen right now. */
    resolved: theme === "system" ? (systemDark ? "dark" : "light") : theme,
  };
}
