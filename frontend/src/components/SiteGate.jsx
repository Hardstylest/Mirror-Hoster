import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import api from "../lib/api";
import { TurnstileWidget } from "./TurnstileWidget";
import { ShieldCheck } from "lucide-react";

const GATE_KEY = "gate_ok_until";
const GATE_MS = 24 * 60 * 60 * 1000; // 24h

const isGateValid = () => {
  try {
    const until = Number(localStorage.getItem(GATE_KEY) || 0);
    return until > Date.now();
  } catch {
    return false;
  }
};

export function SiteGate() {
  const { settings } = useSettings();
  const { lang } = useI18n();
  const location = useLocation();
  const [passed, setPassed] = useState(isGateValid());
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const de = lang === "de";
  // Never gate the public embed player (it is meant to be embedded elsewhere).
  const path = location.pathname;
  const isEmbed = path.startsWith("/e/") || path.startsWith("/embed/");

  const active =
    !isEmbed &&
    !passed &&
    settings.turnstile_enabled &&
    settings.turnstile_gate &&
    !!settings.turnstile_site_key;

  useEffect(() => {
    if (!active || !token) return;
    let cancelled = false;
    (async () => {
      setSubmitting(true);
      setError("");
      try {
        await api.post("/security/verify-gate", { token });
        if (cancelled) return;
        try { localStorage.setItem(GATE_KEY, String(Date.now() + GATE_MS)); } catch { /* noop */ }
        setPassed(true);
      } catch (e) {
        if (!cancelled) setError(de ? "Verifizierung fehlgeschlagen. Bitte erneut versuchen." : "Verification failed. Please try again.");
        setToken("");
      }
      if (!cancelled) setSubmitting(false);
    })();
    return () => { cancelled = true; };
  }, [token, active, de]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm flex items-center justify-center p-6" data-testid="site-gate">
      <div className="w-full max-w-md bg-card border border-border rounded-xl p-8 text-center shadow-2xl animate-fade-up">
        <div className="mx-auto w-12 h-12 rounded-full bg-brand/15 flex items-center justify-center text-brand">
          <ShieldCheck size={24} />
        </div>
        <h2 className="mt-4 font-display font-black text-2xl">
          {de ? "Kurze Sicherheitsprüfung" : "Quick security check"}
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {de
            ? "Bitte bestätige, dass du kein Bot bist, um fortzufahren."
            : "Please confirm you are human to continue."}
        </p>
        <div className="mt-6 flex justify-center min-h-[70px]">
          <TurnstileWidget siteKey={settings.turnstile_site_key} onToken={setToken} onExpire={() => setToken("")} />
        </div>
        {submitting && <p className="mt-3 text-xs text-muted-foreground">{de ? "Prüfe…" : "Verifying…"}</p>}
        {error && <p className="mt-3 text-xs text-offline" data-testid="site-gate-error">{error}</p>}
      </div>
    </div>
  );
}
