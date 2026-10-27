import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import ScorecardPage from "./pages/Scorecard";
import Roles from "./pages/Roles";
import Postings from "./pages/Postings";
import Market from "./pages/Market";
import ProfilePage from "./pages/Profile";
import Ask from "./pages/Ask";
import Admin from "./pages/Admin";

const NAV = [
  { to: "/", label: "Scorecard" },
  { to: "/roles", label: "Role review" },
  { to: "/postings", label: "Postings" },
  { to: "/market", label: "Market" },
  { to: "/ask", label: "Ask" },
  { to: "/profile", label: "Profile" },
  { to: "/dashboard", label: "Gate & gaps" },
];

export default function App() {
  const { user, status, loading, logout } = useAuth();
  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Login />;

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">Career<span>Intel</span></div>
        <nav>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
              {n.label}
            </NavLink>
          ))}
          {user.is_admin && <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>Data</NavLink>}
        </nav>
        <div className="side-foot">
          {status && (
            <div className="sys">
              <span className={`dot ${status.llm ? "on" : "off"}`} />
              {status.llm ? "Claude answers on" : "Offline answers"}
              <br />
              <span className="muted small">{status.embedding_model} · {status.postings} postings</span>
            </div>
          )}
          <div className="who">{user.name || user.email}</div>
          <button className="link" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<ScorecardPage />} />
          <Route path="/scorecard" element={<ScorecardPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/roles" element={<Roles />} />
          <Route path="/postings" element={<Postings />} />
          <Route path="/market" element={<Market />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/ask" element={<Ask />} />
          {user.is_admin && <Route path="/admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
