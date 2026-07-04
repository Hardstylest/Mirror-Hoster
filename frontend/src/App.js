import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { SettingsProvider } from "./context/SettingsContext";
import LandingPage from "./pages/LandingPage";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import MirrorForm from "./pages/MirrorForm";
import MirrorStats from "./pages/MirrorStats";
import AdminDashboard from "./pages/AdminDashboard";
import EmbedPlayer from "./pages/EmbedPlayer";

const Protected = ({ children, adminOnly }) => {
  const { user, ready } = useAuth();
  if (!ready) return <div className="min-h-screen flex items-center justify-center text-brand font-mono">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
};

function App() {
  return (
    <div className="App">
      <Toaster theme="dark" position="top-right" richColors />
      <ThemeProvider>
        <SettingsProvider>
          <BrowserRouter>
            <AuthProvider>
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route path="/e/:slug" element={<EmbedPlayer />} />
                <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
                <Route path="/dashboard/new" element={<Protected><MirrorForm /></Protected>} />
                <Route path="/dashboard/edit/:id" element={<Protected><MirrorForm /></Protected>} />
                <Route path="/dashboard/stats/:id" element={<Protected><MirrorStats /></Protected>} />
                <Route path="/admin" element={<Protected adminOnly><AdminDashboard /></Protected>} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </AuthProvider>
          </BrowserRouter>
        </SettingsProvider>
      </ThemeProvider>
    </div>
  );
}

export default App;
