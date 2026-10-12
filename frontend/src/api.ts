export type User = { id: number; email: string; name: string; is_admin: boolean };

export type Gap = {
  tag: string; label: string; cls: string; pct: number; match: number;
  closable: boolean; close_hint: string; postings?: number; impact?: number; hard?: boolean;
};

export type Posting = {
  id: number; company: string; title: string; level_band: string; role_cluster: string;
  location: string; remote_flag: string; bay_area: boolean; pay_range: string; auth_text: string;
  no_sponsorship: boolean; scope: string; years_required: number | null; tags: string[]; url: string;
  posted: string; status: string; verification: string; last_seen: string;
};

export type Row = {
  posting: Posting; gate_pass: boolean; gate_reasons: string[]; cluster: string;
  weighted_score: number; rank_score: number; has_zero_hard_gap: boolean; hard_gaps: Gap[]; gaps: Gap[];
};

export type TagMatch = { match: number; evidence: string; source: string };

export type Profile = {
  headline: string; cv_text: string; years_experience: number | null;
  tag_matches: Record<string, TagMatch>; min_level: string; locations: string[];
  remote_ok: boolean; needs_sponsorship: boolean; excluded_title_terms: string[]; updated_at: string | null;
};

export type Source = { n: number; title: string; type: string; url: string; similarity: number; excerpt: string };
export type Answer = { id?: number; question?: string; answer: string; sources: Source[]; mode: string; created_at?: string };

const TOKEN_KEY = "ci_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = opts.body;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  const res = await fetch(path, { ...opts, headers, body });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : msg;
    } catch { /* not json */ }
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export function upload<T>(path: string, file: File, params: Record<string, string> = {}): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams(params).toString();
  return api<T>(qs ? `${path}?${qs}` : path, { method: "POST", body: fd });
}

export const pct = (x: number) => `${Math.round(x * 100)}`;
