import { useTheme } from "../context/ThemeContext";
import { Sun, Moon } from "lucide-react";

export const ThemeToggle = ({ className = "" }) => {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      data-testid="theme-toggle"
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle theme"
      className={`inline-flex items-center justify-center w-9 h-9 rounded-md border border-border text-muted-foreground hover:text-brand hover:border-brand transition-colors ${className}`}
    >
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
};
