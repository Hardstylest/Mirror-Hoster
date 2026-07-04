import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { ThemeToggle } from "../components/ThemeToggle";
import { LanguageToggle } from "../components/LanguageToggle";
import { Film, Globe2, LayoutGrid, WifiOff, BarChart3, ArrowRight } from "lucide-react";

const featureDefs = [
  { icon: LayoutGrid, key: "landing.feature1" },
  { icon: Globe2, key: "landing.feature2" },
  { icon: WifiOff, key: "landing.feature3" },
  { icon: BarChart3, key: "landing.feature4" },
];

export default function LandingPage() {
  const { user } = useAuth();
  const { settings } = useSettings();
  const { t } = useI18n();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex items-center justify-between px-6 md:px-12 h-16 border-b border-border">
        <div className="flex items-center gap-2">
          <Film className="text-brand" size={22} />
          <span className="font-display font-black text-lg tracking-tight">{settings.site_name}</span>
        </div>
        <div className="flex items-center gap-3">
          <LanguageToggle />
          <ThemeToggle />
          {user ? (
            <Link to="/dashboard" data-testid="header-dashboard-link" className="px-4 py-2 rounded-md bg-brand text-black font-semibold text-sm hover:bg-brand-hover transition-colors">{t("nav.dashboard")}</Link>
          ) : (
            <>
              <Link to="/login" data-testid="header-login-link" className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors">{t("nav.signin")}</Link>
              <Link to="/register" data-testid="header-register-link" className="px-4 py-2 rounded-md bg-brand text-black font-semibold text-sm hover:bg-brand-hover transition-colors">{t("nav.getstarted")}</Link>
            </>
          )}
        </div>
      </header>

      <section className="relative grid-bg overflow-hidden">
        <div className="absolute -top-40 -right-40 w-[500px] h-[500px] bg-brand/10 rounded-full blur-[120px]" />
        <div className="relative max-w-5xl mx-auto px-6 py-28 text-center">
          <span className="text-xs uppercase tracking-[0.3em] font-semibold text-brand">{t("landing.eyebrow")}</span>
          <h1 className="mt-6 font-display font-black text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.05]">
            One embed link.<br />Every host. <span className="text-brand">Maximum revenue.</span>
          </h1>
          <p className="mt-6 max-w-2xl mx-auto text-base md:text-lg text-muted-foreground leading-relaxed">
            {settings.description || settings.tagline}
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link to={user ? "/dashboard" : "/register"} data-testid="hero-cta-button" className="inline-flex items-center gap-2 px-6 py-3 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
              {t("landing.cta")} <ArrowRight size={18} />
            </Link>
            <Link to="/login" data-testid="hero-signin-button" className="px-6 py-3 rounded-md border border-border text-foreground hover:border-brand transition-colors">{t("nav.signin")}</Link>
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-20 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {featureDefs.map((f) => (
          <div key={f.key} className="bg-card border border-border rounded-lg p-6 hover:-translate-y-1 hover:border-brand/30 transition-all duration-300">
            <div className="w-11 h-11 rounded-md bg-brand/10 flex items-center justify-center mb-4">
              <f.icon className="text-brand" size={22} />
            </div>
            <h3 className="font-display font-bold text-lg">{t(`${f.key}.title`)}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{t(`${f.key}.desc`)}</p>
          </div>
        ))}
      </section>

      <footer className="border-t border-border py-8 text-center text-sm text-muted-foreground">
        © {new Date().getFullYear()} {settings.site_name}. {settings.footer_text}
      </footer>
    </div>
  );
}
