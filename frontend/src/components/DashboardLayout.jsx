import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageToggle } from "./LanguageToggle";
import { LayoutDashboard, Shield, LogOut, Film, Plus } from "lucide-react";

export const DashboardLayout = ({ children }) => {
  const { user, logout } = useAuth();
  const { settings } = useSettings();
  const { t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();

  const nav = [
    { to: "/dashboard", key: "my-mirrors", label: t("nav.myMirrors"), icon: LayoutDashboard },
    ...(user?.role === "admin" ? [{ to: "/admin", key: "admin-panel", label: t("nav.adminPanel"), icon: Shield }] : []),
  ];

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-background">
      <aside className="w-64 shrink-0 border-r border-border bg-card/40 flex flex-col fixed h-screen">
        <div className="flex items-center justify-between px-6 h-16 border-b border-border">
          <Link to="/dashboard" className="flex items-center gap-2 min-w-0">
            <Film className="text-brand shrink-0" size={22} />
            <span className="font-display font-black text-lg tracking-tight truncate">{settings.site_name}</span>
          </Link>
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {nav.map((n) => {
            const active = location.pathname === n.to || (n.to === "/dashboard" && location.pathname.startsWith("/dashboard"));
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={`nav-${n.key}`}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-md text-sm transition-colors ${
                  active ? "bg-brand/10 text-brand" : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                }`}
              >
                <n.icon size={18} />
                {n.label}
              </Link>
            );
          })}
          <Link
            to="/dashboard/new"
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
      <main className="flex-1 ml-64 min-h-screen">{children}</main>
    </div>
  );
};
