import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import { useTheme } from "../context/ThemeContext";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { BarChart3, Eye, Globe2, TrendingUp, DollarSign, Server, Film, Info } from "lucide-react";

const flagEmoji = (cc) => {
  if (!cc || cc.length !== 2 || !/^[a-zA-Z]{2}$/.test(cc)) return null;
  const base = 0x1f1e6;
  return String.fromCodePoint(...[...cc.toUpperCase()].map((c) => base + c.charCodeAt(0) - 65));
};
const countryName = (cc, lang) => {
  try { return new Intl.DisplayNames([lang || "de"], { type: "region" }).of((cc || "").toUpperCase()) || cc; }
  catch { return cc; }
};

const PERIODS = ["today", "7d", "30d", "all"];

const RankBar = ({ label, sub, value, weight, max, flag, testid }) => {
  const w = weight != null ? weight : value;
  return (
    <div className="flex items-center gap-3" data-testid={testid}>
      {flag !== undefined && <span className="w-6 text-base leading-none text-center shrink-0" aria-hidden>{flag || "🌐"}</span>}
      <div className="w-40 min-w-0 shrink-0">
        <p className="text-sm truncate" title={typeof label === "string" ? label : undefined}>{label}</p>
        {sub && <p className="text-xs text-muted-foreground truncate">{sub}</p>}
      </div>
      <div className="flex-1 h-2.5 rounded-full bg-surface overflow-hidden">
        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.max(2, (w / max) * 100)}%` }} />
      </div>
      <span className="w-20 text-right text-sm font-mono tabular-nums shrink-0">{value}</span>
    </div>
  );
};

const Panel = ({ icon: Icon, title, note, children, testid }) => (
  <div className="bg-card border border-border rounded-lg p-6" data-testid={testid}>
    <h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2"><Icon size={18} className="text-brand" /> {title}</h3>
    {note && <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1.5"><Info size={12} /> {note}</p>}
    {!note && <div className="mb-3" />}
    {children}
  </div>
);

const StatCard = ({ icon: Icon, label, value }) => (
  <div className="bg-card border border-border rounded-lg p-5">
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">{label}</span>
      <Icon size={18} className="text-brand" />
    </div>
    <p className="mt-3 font-display font-black text-3xl">{value}</p>
  </div>
);

export default function Statistics() {
  const { t, lang } = useI18n();
  const { theme } = useTheme();
  const [period, setPeriod] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const dark = theme === "dark";
  const grid = dark ? "#222228" : "#E2E5EA";
  const axis = dark ? "#71717A" : "#94A3B8";
  const tooltipStyle = {
    backgroundColor: dark ? "#0F0F12" : "#FFFFFF",
    border: `1px solid ${grid}`, borderRadius: 8, color: dark ? "#fff" : "#0A0A0C",
  };

  const load = useCallback(async () => {
    setLoading(true);
    const { data } = await api.get(`/stats/overview?period=${period}`);
    setData(data);
    setLoading(false);
  }, [period]);

  useEffect(() => { load(); }, [load]);

  const countries = data?.top_countries || [];
  const earnCountries = data?.earnings_by_country || [];
  const mirrors = data?.top_mirrors || [];
  const earning = data?.top_earning || [];
  const hosts = data?.top_hosts || [];
  const timeline = data?.timeline || [];
  const cMax = Math.max(1, ...countries.map((c) => c.views));
  const ecMax = Math.max(1, ...earnCountries.map((c) => c.earnings));
  const mMax = Math.max(1, ...mirrors.map((m) => m.views));
  const eMax = Math.max(1, ...earning.map((m) => m.earnings));
  const hMax = Math.max(1, ...hosts.map((h) => h.views));

  return (
    <DashboardLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-8 flex-wrap">
          <div>
            <h1 className="font-display font-black text-3xl flex items-center gap-2"><BarChart3 className="text-brand" size={28} /> {t("statsov.title")}</h1>
            <p className="text-muted-foreground mt-1">{t("statsov.subtitle")}</p>
          </div>
          <div className="inline-flex rounded-md border border-border overflow-hidden" data-testid="stats-period-toggle">
            {PERIODS.map((p) => (
              <button key={p} onClick={() => setPeriod(p)} data-testid={`period-${p}`}
                className={`px-4 py-2 text-sm transition-colors ${period === p ? "bg-brand text-black font-semibold" : "text-muted-foreground hover:text-foreground hover:bg-secondary"}`}>
                {t(`statsov.period.${p}`)}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <p className="text-muted-foreground font-mono">{t("common.loading")}</p>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <StatCard icon={Eye} label={t("statsov.totalViews")} value={data.total_views} />
              <StatCard icon={DollarSign} label={t("statsov.totalEarnings")} value={`~$${data.total_earnings}`} />
            </div>

            <Panel icon={TrendingUp} title={t("statsov.overTime")} testid="panel-timeline">
              {timeline.length === 0 ? <p className="text-muted-foreground text-sm">{t("statsov.noViews")}</p> : (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={timeline}>
                    <CartesianGrid strokeDasharray="3 3" stroke={grid} />
                    <XAxis dataKey="date" stroke={axis} fontSize={12} />
                    <YAxis stroke={axis} fontSize={12} allowDecimals={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="views" stroke="#48C7F2" strokeWidth={2.5} dot={{ fill: "#48C7F2", r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </Panel>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Panel icon={Film} title={t("statsov.topMirrors")} testid="panel-top-mirrors">
                {mirrors.length === 0 ? <p className="text-muted-foreground text-sm">{t("statsov.empty")}</p> : (
                  <div className="space-y-2.5">
                    {mirrors.map((m) => (
                      <RankBar key={m.id} testid={`top-mirror-${m.id}`}
                        label={<Link to={`/dashboard/stats/${m.id}`} className="hover:text-brand">{m.title}</Link>}
                        value={m.views} max={mMax} />
                    ))}
                  </div>
                )}
              </Panel>

              <Panel icon={DollarSign} title={t("statsov.topEarning")} note={t("statsov.estimateNote")} testid="panel-top-earning">
                {earning.length === 0 || eMax <= 0 ? <p className="text-muted-foreground text-sm">{t("statsov.empty")}</p> : (
                  <div className="space-y-2.5">
                    {earning.map((m) => (
                      <RankBar key={m.id} testid={`top-earning-${m.id}`}
                        label={<Link to={`/dashboard/stats/${m.id}`} className="hover:text-brand">{m.title}</Link>}
                        sub={`${m.views} ${t("statsov.viewsSuffix")}`}
                        value={`~$${m.earnings}`} weight={m.earnings} max={eMax} />
                    ))}
                  </div>
                )}
              </Panel>

              <Panel icon={Globe2} title={t("dash.countries.title")} testid="panel-countries">
                {countries.length === 0 ? <p className="text-muted-foreground text-sm">{t("dash.countries.empty")}</p> : (
                  <div className="space-y-2.5">
                    {countries.map((c) => (
                      <RankBar key={c.country_code} testid={`country-row-${c.country_code}`}
                        flag={flagEmoji(c.country_code)}
                        label={c.country_code === "XX" ? t("dash.countries.unknown") : countryName(c.country_code, lang)}
                        value={c.views} max={cMax} />
                    ))}
                  </div>
                )}
              </Panel>

              <Panel icon={DollarSign} title={t("statsov.earnByCountry")} note={t("statsov.estimateNote")} testid="panel-earn-country">
                {earnCountries.length === 0 || ecMax <= 0 ? <p className="text-muted-foreground text-sm">{t("statsov.empty")}</p> : (
                  <div className="space-y-2.5">
                    {earnCountries.map((c) => (
                      <RankBar key={c.country_code} testid={`earn-country-${c.country_code}`}
                        flag={flagEmoji(c.country_code)}
                        label={c.country_code === "XX" ? t("dash.countries.unknown") : countryName(c.country_code, lang)}
                        value={`~$${c.earnings}`} weight={c.earnings} max={ecMax} />
                    ))}
                  </div>
                )}
              </Panel>

              <Panel icon={Server} title={t("statsov.topHosts")} note={t("statsov.hostsNote")} testid="panel-top-hosts">
                {hosts.length === 0 ? <p className="text-muted-foreground text-sm">{t("statsov.empty")}</p> : (
                  <div className="space-y-2.5">
                    {hosts.map((h, i) => (
                      <RankBar key={h.host_name + i} testid={`top-host-${i}`}
                        label={h.host_name} sub={h.domain} value={h.views} max={hMax} />
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
