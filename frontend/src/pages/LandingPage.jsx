import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Film, Globe2, LayoutGrid, WifiOff, BarChart3, ArrowRight } from "lucide-react";

const features = [
  { icon: LayoutGrid, title: "Browser-Tab Player", desc: "Switch between Doodstream, VOE & more via native-style tabs with favicons." },
  { icon: Globe2, title: "Geo Revenue Routing", desc: "Viewers see the highest-paying host for their country first — automatically." },
  { icon: WifiOff, title: "Offline Detection", desc: "Broken mirrors are detected on a schedule and flagged in your dashboard." },
  { icon: BarChart3, title: "Per-Movie Analytics", desc: "Track views, countries and host performance for every mirror." },
];

export default function LandingPage() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-background text-white">
      <header className="flex items-center justify-between px-6 md:px-12 h-16 border-b border-border">
        <div className="flex items-center gap-2">
          <Film className="text-brand" size={22} />
          <span className="font-display font-black text-lg tracking-tight">MirrorStream</span>
        </div>
        <div className="flex items-center gap-3">
          {user ? (
            <Link to="/dashboard" data-testid="header-dashboard-link" className="px-4 py-2 rounded-md bg-brand text-black font-semibold text-sm hover:bg-brand-hover transition-colors">Dashboard</Link>
          ) : (
            <>
              <Link to="/login" data-testid="header-login-link" className="px-4 py-2 text-sm text-muted-foreground hover:text-white transition-colors">Sign in</Link>
              <Link to="/register" data-testid="header-register-link" className="px-4 py-2 rounded-md bg-brand text-black font-semibold text-sm hover:bg-brand-hover transition-colors">Get started</Link>
            </>
          )}
        </div>
      </header>

      <section className="relative grid-bg overflow-hidden">
        <div className="absolute -top-40 -right-40 w-[500px] h-[500px] bg-brand/10 rounded-full blur-[120px]" />
        <div className="relative max-w-5xl mx-auto px-6 py-28 text-center">
          <span className="text-xs uppercase tracking-[0.3em] font-semibold text-brand">Multi-host video mirroring</span>
          <h1 className="mt-6 font-display font-black text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.05]">
            One embed link.<br />Every host. <span className="text-brand">Maximum revenue.</span>
          </h1>
          <p className="mt-6 max-w-2xl mx-auto text-base md:text-lg text-slate-300 leading-relaxed">
            Paste your embed links from Doodstream, VOE and other hosters. We generate a single player that always shows your viewers the best-paying source for their country.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link to={user ? "/dashboard" : "/register"} data-testid="hero-cta-button" className="inline-flex items-center gap-2 px-6 py-3 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
              Start mirroring <ArrowRight size={18} />
            </Link>
            <Link to="/login" data-testid="hero-signin-button" className="px-6 py-3 rounded-md border border-border text-white hover:border-brand transition-colors">Sign in</Link>
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-20 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {features.map((f) => (
          <div key={f.title} className="bg-card border border-border rounded-lg p-6 hover:-translate-y-1 hover:border-brand/30 transition-all duration-300">
            <div className="w-11 h-11 rounded-md bg-brand/10 flex items-center justify-center mb-4">
              <f.icon className="text-brand" size={22} />
            </div>
            <h3 className="font-display font-bold text-lg">{f.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </section>

      <footer className="border-t border-border py-8 text-center text-sm text-muted-foreground">
        © {new Date().getFullYear()} MirrorStream. For legal content only.
      </footer>
    </div>
  );
}
