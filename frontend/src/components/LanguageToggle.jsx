import { useI18n } from "../context/I18nContext";

export const LanguageToggle = ({ className = "" }) => {
  const { lang, setLang } = useI18n();
  return (
    <button
      onClick={() => setLang(lang === "de" ? "en" : "de")}
      data-testid="language-toggle"
      title={lang === "de" ? "Switch to English" : "Zu Deutsch wechseln"}
      aria-label="Toggle language"
      className={`inline-flex items-center justify-center h-9 px-2.5 rounded-md border border-border text-xs font-semibold text-muted-foreground hover:text-brand hover:border-brand transition-colors ${className}`}
    >
      {lang === "de" ? "DE" : "EN"}
    </button>
  );
};
