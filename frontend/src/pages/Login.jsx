import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { formatApiError } from "../lib/api";
import { Film } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
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
            <h2 className="font-display font-black text-3xl leading-tight">Route every view to the highest-paying host.</h2>
            <p className="mt-3 text-slate-300 max-w-md">Smart geo-based provider ordering for your video mirrors.</p>
          </div>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-background">
        <form onSubmit={submit} className="w-full max-w-sm animate-fade-up">
          <h1 className="font-display font-black text-3xl">Welcome back</h1>
          <p className="mt-2 text-sm text-muted-foreground">Sign in to your dashboard.</p>
          {error && <p data-testid="login-error" className="mt-4 text-sm text-offline bg-offline/10 border border-offline/30 rounded-md px-3 py-2">{error}</p>}
          <div className="mt-6 space-y-4">
            <div>
              <label className="text-sm text-muted-foreground">Email</label>
              <input data-testid="login-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full bg-[#0A0A0C] border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">Password</label>
              <input data-testid="login-password-input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full bg-[#0A0A0C] border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
          </div>
          <button data-testid="login-submit-button" disabled={loading} type="submit"
            className="mt-6 w-full py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <p className="mt-6 text-sm text-center text-muted-foreground">
            No account? <Link to="/register" className="text-brand hover:underline">Create one</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
