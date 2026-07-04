import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { formatApiError } from "../lib/api";
import { useI18n } from "../context/I18nContext";
import { LanguageToggle } from "../components/LanguageToggle";
import { ThemeToggle } from "../components/ThemeToggle";
import { Film } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const u = await login(email, password);
      navigate(u.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:block lg:w-1/2 relative">
        <img src="https://images.unsplash.com/photo-1655841439659-0afc60676b70?crop=entropy&cs=srgb&fm=jpg&q=85" alt="" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-background/60" />
        <div className="relative z-10 p-12 flex flex-col h-full">
          <div className="flex items-center gap-2"><Film className="text-brand" size={22} /><span className="font-display font-black text-lg">MirrorStream</span></div>
          <div className="mt-auto">
            <h2 className="font-display font-black text-3xl leading-tight">{t("auth.loginPromoTitle")}</h2>
            <p className="mt-3 text-slate-300 max-w-md">{t("auth.loginPromoDesc")}</p>
          </div>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-background relative">
        <div className="absolute top-6 right-6 flex items-center gap-2"><LanguageToggle /><ThemeToggle /></div>
        <form onSubmit={submit} className="w-full max-w-sm animate-fade-up">
          <h1 className="font-display font-black text-3xl">{t("auth.welcomeBack")}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{t("auth.loginSubtitle")}</p>
          {error && <p data-testid="login-error" className="mt-4 text-sm text-offline bg-offline/10 border border-offline/30 rounded-md px-3 py-2">{error}</p>}
          <div className="mt-6 space-y-4">
            <div>
              <label className="text-sm text-muted-foreground">{t("auth.email")}</label>
              <input data-testid="login-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{t("auth.password")}</label>
              <input data-testid="login-password-input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
          </div>
          <button data-testid="login-submit-button" disabled={loading} type="submit"
            className="mt-6 w-full py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
            {loading ? t("auth.signingIn") : t("nav.signin")}
          </button>
          <p className="mt-6 text-sm text-center text-muted-foreground">
            {t("auth.noAccount")} <Link to="/register" className="text-brand hover:underline">{t("auth.createOne")}</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
