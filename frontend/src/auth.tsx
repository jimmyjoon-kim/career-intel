import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, type User } from "./api";

type Status = { llm: boolean; llm_model: string | null; embedding_model: string; postings: number; chunks: number; is_admin: boolean };

type Ctx = {
  user: User | null;
  status: Status | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  refreshStatus: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshStatus = useCallback(async () => {
    try { setStatus(await api<Status>("/api/status")); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    api<User>("/api/auth/me")
      .then((u) => { setUser(u); return refreshStatus(); })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, [refreshStatus]);

  const finish = async (r: { token: string; user: User }) => {
    setToken(r.token);
    setUser(r.user);
    await refreshStatus();
  };

  const value: Ctx = {
    user, status, loading, refreshStatus,
    login: async (email, password) => finish(await api("/api/auth/login", { method: "POST", json: { email, password } })),
    signup: async (email, password, name) => finish(await api("/api/auth/signup", { method: "POST", json: { email, password, name } })),
    logout: () => { setToken(null); setUser(null); setStatus(null); },
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): Ctx {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth outside provider");
  return c;
}
