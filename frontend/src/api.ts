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

export type Opportunity = {
  score: number; position: number; delta_vs_base: number; weights: Record<string, number>;
  emphasised: string[]; thresholds: string[];
};

export type Row = {
  posting: Posting; gate_pass: boolean; gate_reasons: string[]; cluster: string;
  weighted_score: number; rank_score: number; has_zero_hard_gap: boolean; hard_gaps: Gap[]; gaps: Gap[];
  opportunity: Opportunity | null;
};

export type Factor = {
  factor: string; label: string; weight: number; you_value: number | null; you_pct: number | null;
  holder_median_value: number | null; holder_median_pct: number | null; share_above_you: number | null;
  delta: number | null; coverage: number;
};
export type GapV2 = Factor & { class: string; action: string; months_to_close: number | null; closable_by_target: boolean | null };
export type Card = {
  cluster: string; n_reference: number; weights: Record<string, number>; base_score: number; position: number;
  position_ci95: [number | null, number | null];
  holders: { scores: number[]; tier_share: Record<string, number>; median: number; p25: number; p75: number; hist: { edges: number[]; counts: number[] } };
  prevalence: Record<string, number>; tag_labels: Record<string, string>;
  factors: Factor[]; gaps: GapV2[]; differentiators: Factor[];
  focus_areas: { tag: string; label: string; holder_share: number; your_weight: number; status: string; note: string }[];
  rare_strengths: { tag: string; label: string; holder_share: number }[];
  benchmark: {
    max: number; p90: number; p75: number; median: number; p25: number; min: number; ceiling_note: string;
    n_above: number; above_tiers: Record<string, number>;
    drivers: { label: string; avg_points: number | null; holders_ahead: number }[];
    whatifs: { change: string; factor: string; score: number; delta: number; position: number; closable: boolean }[];
  };
  peers: { company: string; title: string; score: number; similarity: number; ahead_on: string[]; you_lead_on: string[];
    components: Record<string, number>; values: Record<string, number | null> }[];
};
export type RoleRead = {
  title: string; company: string; start: string; end: string; months: number; level: number | null; counted: boolean; tier: number;
  key: string; families: string[]; auto: Record<string, { source: string; phrase: string }>; final: Record<string, number>;
  team_size: number | null; reviewed: boolean; recency_weight: number;
};
export type Scorecard = {
  ready: boolean; reason?: string; card?: Card;
  gap_plan?: { against: string; gap: string; kind: string; you: string | number | null; them: string | number | null;
    evidence: string; action: string; months: number | null; by_target: boolean | null; score_effect: number | null; factor: string | null }[]; reference?: { source: string; as_of: string }; months_left?: number | null;
  reading?: {
    source: string; format: string; years: number; level_max: string | null; level_names: Record<string, string>;
    recent_role: { title: string; company: string; start: string; end: string; months: number; level: number; level_cue: string | null; tier: number } | null;
    roles: RoleRead[]; evidence: { tag: string; weight: number; role: string; phrase: string; source: string; url: string }[];
    team_size_max: { size: number; role: string; source: string } | null;
    achievements: { role: string; line: string; match: string }[]; tags: Record<string, number>;
  };
  notes?: string[];
};

export type TagMatch = { match: number; evidence: string; source: string };

export type Profile = {
  headline: string; cv_text: string; experience_text: string; target_date: string; years_experience: number | null;
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
