import { createContext, useContext, useEffect, useState } from "react";
import api from "../lib/api";

const SettingsContext = createContext(null);

const FALLBACK = {
  site_name: "MirrorStream",
  tagline: "One embed link. Every host. Maximum revenue.",
  description: "",
  footer_text: "For legal content only.",
  ad_header: "",
  ad_footer: "",
  ad_player_top: "",
  ad_player_bottom: "",
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

  return (
    <SettingsContext.Provider value={{ settings, reloadSettings: load }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => useContext(SettingsContext);
