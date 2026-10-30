import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signupOpen, setSignupOpen] = useState(false);
  useEffect(() => { api<{ signup_open: boolean }>("/api/auth/config").then((c) => setSignupOpen(c.signup_open)).catch(() => setSignupOpen(false)); }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      mode === "login" ? await login(email, password) : await signup(email, password, name);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <section className="auth-intro">
        <div className="brand big">Career<span>Intel</span></div>
        <h1>Know exactly where you stand for the roles you want.</h1>
        <p>
          Upload your CV. Career Intel maps it against live postings, separates the requirements every hire has from the
          ones that set candidates apart, and shows which gaps you can close.
        </p>
        <ul className="ticks">
          <li>Gate first: level, location, authorization, live status</li>
          <li>Weights from the market, not from job-ad wording</li>
          <li>Ask questions answered only from cited sources</li>
        </ul>
      </section>
      <form className="card auth-card" onSubmit={submit}>
        <h2>{mode === "login" ? "Sign in" : "Create your account"}</h2>
        {mode === "signup" && (
          <label>Name<input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
        )}
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>
          Password
          <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"} />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
        {(signupOpen || mode === "signup") && <p className="muted small">
          {mode === "login" ? "New here? " : "Already have an account? "}
          <button type="button" className="link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>}
      </form>
    </div>
  );
}
