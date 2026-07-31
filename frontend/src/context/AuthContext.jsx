import { createContext, useContext, useEffect, useState } from "react";
import api from "../lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null = loading, false = not auth
  const [ready, setReady] = useState(false);

  const loadUser = async () => {
    const token = localStorage.getItem("token");
    if (!token) {
      setUser(false);
      setReady(true);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      localStorage.removeItem("token");
      setUser(false);
    }
    setReady(true);
  };

  useEffect(() => {
    loadUser();
  }, []);

  const login = async (email, password, turnstileToken) => {
    const { data } = await api.post("/auth/login", { email, password, turnstile_token: turnstileToken || null });
    localStorage.setItem("token", data.access_token);
    setUser(data.user);
    return data.user;
  };

  const register = async (name, email, password, turnstileToken) => {
    const { data } = await api.post("/auth/register", { name, email, password, turnstile_token: turnstileToken || null });
    localStorage.setItem("token", data.access_token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch {}
    localStorage.removeItem("token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, ready, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
