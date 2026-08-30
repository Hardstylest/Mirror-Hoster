import { createContext, useContext, useEffect, useState } from "react";
import api from "../lib/api";

const SettingsContext = createContext(null);

// Inject admin-defined raw HTML (meta/scripts/etc.) into <head> or end of <body>.
// Re-creates <script> nodes so they actually execute, and removes prior injections
// (tagged via data-gp-inject) before re-applying so updates don't duplicate.
const injectCustomHTML = (html, target, marker) => {
  if (!target) return;
  target.querySelectorAll(`[data-gp-inject="${marker}"]`).forEach((n) => n.remove());
  if (!html || !html.trim()) return;
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  Array.from(tmp.childNodes).forEach((node) => {
    let el = node;
    if (node.tagName === "SCRIPT") {
      el = document.createElement("script");
      Array.from(node.attributes).forEach((a) => el.setAttribute(a.name, a.value));
      el.textContent = node.textContent;
    }
    if (el.setAttribute) el.setAttribute("data-gp-inject", marker);
    target.appendChild(el);
  });
};

const FALLBACK = {
  site_name: "MirrorStream",
  tagline: "One embed link. Every host. Maximum revenue.",
  description: "",
  footer_text: "For legal content only.",
  ad_header: "",
  ad_footer: "",
  ad_player_top: "",
  ad_player_bottom: "",
  ad_preroll: "",
  ad_preroll_enabled: false,
  ad_preroll_seconds: 8,
  ad_preroll_repeat_enabled: false,
  ad_preroll_repeat_minutes: 10,
  ad_preroll_repeat_max: 0,
  ad_postroll_enabled: false,
  ad_postroll: "",
  ad_postroll_minutes: 30,
  custom_head: "",
  custom_footer: "",
  verify_google: "",
  verify_bing: "",
  verify_juicyads: "",
  turnstile_enabled: false,
  turnstile_site_key: "",
  turnstile_login: true,
  turnstile_register: true,
  turnstile_gate: true,
  antiadblock_enabled: false,
  antiadblock_mode: "off",
  registration_open: true,
  proxycheck_enabled: false,
  has_proxycheck_key: false,
  has_turnstile_secret: false,
};

export const SettingsProvider = ({ children }) => {
  const [settings, setSettings] = useState(FALLBACK);

  const load = async () => {
    try {
      const { data } = await api.get("/settings");
      setSettings({ ...FALLBACK, ...data });
    } catch {
      setSettings(FALLBACK);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (settings?.site_name) document.title = settings.site_name;
  }, [settings?.site_name]);

  useEffect(() => { injectCustomHTML(settings.custom_head || "", document.head, "head"); }, [settings.custom_head]);
  useEffect(() => { injectCustomHTML(settings.custom_footer || "", document.body, "footer"); }, [settings.custom_footer]);

  useEffect(() => {
    const esc = (s) => String(s).replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const token = (v) => {
      // accept either a bare token or a full <meta ... content="TOKEN"> paste
      const m = String(v || "").match(/content=["']([^"']+)["']/i);
      return (m ? m[1] : v || "").trim();
    };
    const metas = [];
    if (settings.verify_google) metas.push(`<meta name="google-site-verification" content="${esc(token(settings.verify_google))}">`);
    if (settings.verify_bing) metas.push(`<meta name="msvalidate.01" content="${esc(token(settings.verify_bing))}">`);
    if (settings.verify_juicyads) metas.push(`<meta name="juicyads-site-verification" content="${esc(token(settings.verify_juicyads))}">`);
    injectCustomHTML(metas.join("\n"), document.head, "verify");
  }, [settings.verify_google, settings.verify_bing, settings.verify_juicyads]);

  return (
    <SettingsContext.Provider value={{ settings, reloadSettings: load }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => useContext(SettingsContext);
