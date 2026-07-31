import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageToggle } from "./LanguageToggle";
import { LayoutDashboard, Shield, LogOut, Film, Plus, Menu, X, WifiOff } from "lucide-react";

export const DashboardLayout = ({ children }) => {
  const { user, logout } = useAuth();
  const { settings } = useSettings();
  const { t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [offlineCount, setOfflineCount] = useState(0);

  useEffect(() => {
    const refresh = () => api.get("/stats/dashboard").then(({ data }) => setOfflineCount(data.offline_mirrors || 0)).catch(() => {});
    refresh();
    window.addEventListener("offline-updated", refresh);
    return () => window.removeEventListener("offline-updated", refresh);
  }, [location.pathname]);

  const nav = [
    { to: "/dashboard", key: "my-mirrors", label: t("nav.myMirrors"), icon: LayoutDashboard },
    { to: "/dashboard/offline", key: "offline-streams", label: t("nav.offline"), icon: WifiOff, badge: offlineCount },
    ...(user?.role === "admin" ? [{ to: "/admin", key: "admin-panel", label: t("nav.adminPanel"), icon: Shield }] : []),
  ];

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 h-14 z-40 flex items-center justify-between px-4 border-b border-border bg-card">
        <Link to="/dashboard" className="flex items-center gap-2 min-w-0">
          <Film className="text-brand shrink-0" size={20} />
          <span className="font-display font-black text-base tracking-tight truncate">{settings.site_name}</span>
        </Link>
        <button data-testid="mobile-menu-button" onClick={() => setMobileOpen(true)} className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary">
          <Menu size={22} />
        </button>
      </div>

      {/* Backdrop for mobile drawer */}
      {mobileOpen && <div className="md:hidden fixed inset-0 z-40 bg-black/60" onClick={() => setMobileOpen(false)} />}

      <aside className={`w-64 shrink-0 border-r border-border bg-card flex flex-col fixed h-screen z-50 transition-transform duration-200
        ${mobileOpen ? "translate-x-0" : "-translate-x-full"} md:translate-x-0 md:bg-card/40`}>
        <div className="flex items-center justify-between px-6 h-16 border-b border-border">
          <Link to="/dashboard" onClick={() => setMobileOpen(false)} className="flex items-center gap-2 min-w-0">
            <Film className="text-brand shrink-0" size={22} />
            <span className="font-display font-black text-lg tracking-tight truncate">{settings.site_name}</span>
          </Link>
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <ThemeToggle />
            <button onClick={() => setMobileOpen(false)} className="md:hidden p-1 text-muted-foreground hover:text-foreground"><X size={20} /></button>
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {nav.map((n) => {
            const active = location.pathname === n.to || (n.to === "/dashboard" && location.pathname.startsWith("/dashboard") && location.pathname !== "/dashboard/offline");
            return (
              <Link
                key={n.to}
                to={n.to}
                onClick={() => setMobileOpen(false)}
                data-testid={`nav-${n.key}`}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-md text-sm transition-colors ${
                  active ? "bg-brand/10 text-brand" : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                }`}
              >
                <n.icon size={18} />
                {n.label}
                {n.badge > 0 && (
                  <span data-testid="offline-nav-badge" className="ml-auto inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-xs font-bold bg-offline text-white">
                    {n.badge}
                  </span>
                )}
              </Link>
            );
          })}
          <Link
            to="/dashboard/new"
            onClick={() => setMobileOpen(false)}
            data-testid="nav-new-mirror"
            className="flex items-center gap-3 px-4 py-2.5 mt-4 rounded-md text-sm bg-brand text-black font-semibold hover:bg-brand-hover transition-colors"
          >
            <Plus size={18} /> {t("nav.newMirror")}
          </Link>
        </nav>
        <div className="p-4 border-t border-border">
          <div className="px-2 mb-3">
            <p className="text-sm font-medium truncate">{user?.name}</p>
            <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
          </div>
          <button
            onClick={handleLogout}
            data-testid="logout-button"
            className="flex items-center gap-3 w-full px-4 py-2.5 rounded-md text-sm text-muted-foreground hover:text-offline hover:bg-secondary transition-colors"
          >
            <LogOut size={18} /> {t("nav.signout")}
          </button>
        </div>
      </aside>
      <main className="flex-1 md:ml-64 min-h-screen pt-14 md:pt-0">{children}</main>
    </div>
  );
};
