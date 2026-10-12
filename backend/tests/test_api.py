from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "seed" / "postings_2026-10-12.csv"

CV = """Alex Morgan — Commercial executive, ad tech and AI
2005-2026. Founded and led the regional business of a mobile advertising platform as General Manager,
with full P&L ownership of a $120 million revenue business and a team of 25 direct and indirect reports.
Built strategic partnerships with game developers and e-commerce platforms; negotiated revenue share deals
with C-level executives; launched programmatic and rewarded video products; forecasting and pipeline in Salesforce.
Co-founder and interim CRO of a generative AI start-up building LLM agents.
Bachelor of Science in Engineering. Executive MBA. MS in AI Engineering (in progress).
""" * 2


def signup(client, email):
    r = client.post("/api/auth/signup", json={"email": email, "password": "password123", "name": "T"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def test_full_flow(client):
    admin_h, admin = signup(client, "admin@example.com")
    assert admin["is_admin"]  # first user is admin
    user_h, user = signup(client, "user@example.com")
    assert not user["is_admin"]

    # Auth errors
    assert client.post("/api/auth/signup", json={"email": "user@example.com", "password": "password123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong"}).status_code == 401
    assert client.get("/api/dashboard").status_code == 401

    # Only admins import
    files = {"file": (SEED.name, SEED.read_bytes(), "text/csv")}
    assert client.post("/api/admin/import", files=files, headers=user_h).status_code == 403
    r = client.post("/api/admin/import", files=files, headers=admin_h, params={"source_date": "2026-10-12"})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 55 and r.json()["chunks"] > 55

    # Re-import updates rather than duplicating
    r = client.post("/api/admin/import", files={"file": (SEED.name, SEED.read_bytes(), "text/csv")}, headers=admin_h)
    assert r.json()["created"] == 0 and r.json()["updated"] == 55

    # Market stats exclude attribute tags
    m = client.get("/api/market", headers=user_h).json()
    all_tags = {t["tag"] for t in m["all"]["tags"]}
    assert not any(t.startswith(("scope_", "tenure_", "market_")) for t in all_tags)
    assert m["all"]["n"] == 42  # only LISTED postings count as open

    # CV upload extracts tags (keyword mode offline)
    r = client.post("/api/profile/cv", files={"file": ("cv.txt", CV.encode(), "text/plain")}, headers=user_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["extraction_mode"] == "keyword"
    tags = body["profile"]["tag_matches"]
    assert {"pnl_ownership", "domain_adtech", "func_partnerships"} <= set(tags)

    # Preferences + user override
    r = client.put("/api/profile", json={"excluded_title_terms": ["Country Manager"], "min_level": "Director"},
                   headers=user_h)
    assert r.status_code == 200
    r = client.put("/api/profile/tags/skill_si_gsi", json={"match": 0.5, "evidence": "Worked with SIs"}, headers=user_h)
    assert r.json()["tag_matches"]["skill_si_gsi"]["source"] == "user"

    # Dashboard ranks gate-passing postings only
    d = client.get("/api/dashboard", headers=user_h).json()
    assert d["profile_ready"]
    assert 0 < d["counts"]["gate_pass"] <= d["counts"]["open"]
    assert all(t["gate_pass"] for t in d["top"])
    ranks = [(t["has_zero_hard_gap"], -t["rank_score"]) for t in d["top"]]
    assert ranks == sorted(ranks)
    assert d["gaps"]

    rows = client.get("/api/postings", headers=user_h).json()
    assert len(rows) == 55
    assert any("posting status" in r for row in rows for r in row["gate_reasons"])
    detail = client.get(f"/api/postings/{rows[0]['posting']['id']}", headers=user_h).json()
    assert detail["posting"]["id"] == rows[0]["posting"]["id"]

    # RAG: private CV chunks are visible only to their owner
    a = client.post("/api/ask", json={"question": "Which partnerships roles at OpenAI fit me?"}, headers=user_h).json()
    assert a["mode"] == "extractive" and a["sources"]
    types = {s["type"] for s in a["sources"]}
    assert types <= {"posting", "market", "method", "cv", "scorecard"}
    a2 = client.post("/api/ask", json={"question": "Alex Morgan CV founded mobile advertising platform"},
                     headers=admin_h).json()
    assert all(s["type"] not in ("cv", "scorecard") for s in a2["sources"])
    a3 = client.post("/api/ask", json={"question": "Alex Morgan CV founded mobile advertising platform"},
                     headers=user_h).json()
    assert any(s["type"] == "cv" for s in a3["sources"])
    assert len(client.get("/api/ask/history", headers=user_h).json()) == 2

    s = client.get("/api/status", headers=admin_h).json()
    assert s["embedding_model"] == "local-hash-v1" and s["postings"] == 55 and not s["llm"]

    # Admin can close a posting; it then fails the gate
    pid = d["top"][0]["posting"]["id"]
    assert client.patch(f"/api/admin/postings/{pid}", params={"status": "closed"}, headers=admin_h).status_code == 200
    d2 = client.get("/api/dashboard", headers=user_h).json()
    assert pid not in [t["posting"]["id"] for t in d2["top"]]
