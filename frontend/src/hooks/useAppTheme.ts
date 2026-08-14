import { useCallback, useEffect, useState } from "react";

const THEME_KEY = "qa_tester_theme";
export type AppTheme = "dark" | "light";

function getInitialTheme(): AppTheme {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === "light" ? "light" : "dark";
}

export function useAppTheme() {
  const [theme, setTheme] = useState<AppTheme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-app-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggleTheme };
}
