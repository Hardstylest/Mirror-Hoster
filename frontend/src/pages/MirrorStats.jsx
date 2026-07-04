import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../lib/api";
import { useTheme } from "../context/ThemeContext";
import { DashboardLayout } from "../components/DashboardLayout";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar,
} from "recharts";
import { ArrowLeft, Eye, Globe2 } from "lucide-react";

export default function MirrorStats() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { theme } = useTheme();
  const [data, setData] = useState(null);

  const dark = theme === "dark";
  const grid = dark ? "#222228" : "#E2E5EA";
  const axis = dark ? "#71717A" : "#94A3B8";
  const tooltipStyle = {
    backgroundColor: dark ? "#0F0F12" : "#FFFFFF",
    border: `1px solid ${grid}`,
    borderRadius: 8,
    color: dark ? "#fff" : "#0A0A0C",
  };

  useEffect(() => {
    api.get(`/stats/mirror/${id}`).then((r) => setData(r.data));
  }, [id]);

  return (
    <DashboardLayout>
      <div className="p-8 max-w-5xl mx-auto">
        <button onClick={() => navigate("/dashboard")} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors">
          <ArrowLeft size={16} /> Back
        </button>
        <h1 className="font-display font-black text-3xl mb-8">Mirror Statistics</h1>

        {!data ? <p className="text-muted-foreground font-mono">Loading…</p> : (
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              <div className="bg-card border border-border rounded-lg p-5">
                <div className="flex items-center justify-between"><span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Total Views</span><Eye size={18} className="text-brand" /></div>
                <p className="mt-3 font-display font-black text-3xl" data-testid="stats-total-views">{data.total_views}</p>
              </div>
              <div className="bg-card border border-border rounded-lg p-5">
                <div className="flex items-center justify-between"><span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Countries</span><Globe2 size={18} className="text-brand" /></div>
                <p className="mt-3 font-display font-black text-3xl">{data.countries.length}</p>
              </div>
              <div className="bg-card border border-border rounded-lg p-5">
                <div className="flex items-center justify-between"><span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">Sources</span></div>
                <p className="mt-3 font-display font-black text-3xl">{data.links.length}</p>
              </div>
            </div>

            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="font-display font-bold text-lg mb-4">Views over time</h3>
              {data.timeline.length === 0 ? <p className="text-muted-foreground text-sm">No views recorded yet.</p> : (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={data.timeline}>
                    <CartesianGrid strokeDasharray="3 3" stroke={grid} />
                    <XAxis dataKey="date" stroke={axis} fontSize={12} />
                    <YAxis stroke={axis} fontSize={12} allowDecimals={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="views" stroke="#48C7F2" strokeWidth={2.5} dot={{ fill: "#48C7F2", r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-card border border-border rounded-lg p-6">
                <h3 className="font-display font-bold text-lg mb-4">Top countries</h3>
                {data.countries.length === 0 ? <p className="text-muted-foreground text-sm">No data yet.</p> : (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={data.countries} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke={grid} horizontal={false} />
                      <XAxis type="number" stroke={axis} fontSize={12} allowDecimals={false} />
                      <YAxis type="category" dataKey="country" stroke={axis} fontSize={12} width={90} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(72,199,242,0.08)" }} />
                      <Bar dataKey="views" fill="#48C7F2" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="bg-card border border-border rounded-lg p-6">
                <h3 className="font-display font-bold text-lg mb-4">Views per host</h3>
                {data.per_host.every((h) => h.views === 0) ? <p className="text-muted-foreground text-sm">No host selections recorded yet.</p> : (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={data.per_host}>
                      <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                      <XAxis dataKey="host_name" stroke={axis} fontSize={12} />
                      <YAxis stroke={axis} fontSize={12} allowDecimals={false} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(72,199,242,0.08)" }} />
                      <Bar dataKey="views" fill="#48C7F2" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
