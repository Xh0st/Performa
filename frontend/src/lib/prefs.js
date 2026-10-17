import { createContext, useContext, useEffect, useState, useCallback } from "react";

const PrefsCtx = createContext(null);

export function PrefsProvider({ children }) {
  const [lang, setLang] = useState(localStorage.getItem("erp_lang") || "ro");
  const [theme, setTheme] = useState(localStorage.getItem("erp_theme") || "dark");
  useEffect(() => {
    localStorage.setItem("erp_lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);
  useEffect(() => {
    localStorage.setItem("erp_theme", theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  const tr = useCallback((ro, en) => (lang === "ro" ? ro : en ?? ro), [lang]);
  return <PrefsCtx.Provider value={{ lang, setLang, theme, setTheme, tr }}>{children}</PrefsCtx.Provider>;
}

export const useLang = () => useContext(PrefsCtx);
