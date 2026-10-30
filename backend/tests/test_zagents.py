"""Agent team (runs after test_api, which loads postings, reference holders and profiles). Offline: no model calls."""

import json

import httpx
import pytest

from app.agents import requirements, sourcing
from app.agents.checker import check_brief, golden, numbers_in

GH = {"jobs": [
    {"title": "Director, Strategic Partnerships", "absolute_url": "https://job-boards.greenhouse.io/testco/jobs/1",
     "location": {"name": "San Francisco, CA"}, "content": "&lt;p&gt;Lead partnerships with app publishers. $250,000 - $300,000&lt;/p&gt;",
     "updated_at": "2026-10-20T00:00:00Z"},
    {"title": "Country Manager, Partnerships Korea", "absolute_url": "https://job-boards.greenhouse.io/testco/jobs/2",
     "location": {"name": "Seoul"}, "content": "x", "updated_at": "2026-10-20"},
    {"title": "Software Engineer", "absolute_url": "https://job-boards.greenhouse.io/testco/jobs/3",
     "location": {"name": "Remote"}, "content": "x", "updated_at": "2026-10-20"},
    {"title": "Head of Partnerships, EMEA", "absolute_url": "https://job-boards.greenhouse.io/testco/jobs/4",
     "location": {"name": "London, UK"}, "content": "x", "updated_at": "2026-10-20"},
]}


def mock_client(payload):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload)))


def test_title_and_location_screen():
    assert sourcing.keep("VP, Business Development", "Remote - US")[0]
    assert not sourcing.keep("Country Manager, Japan", "Tokyo")[0]  # outside locations
    assert sourcing.keep("Regional Manager, Ads Solutions (APAC)", "Singapore", sourcing._loc_pattern(["Singapore"]))[0]
    assert not sourcing.keep("Senior Software Engineer", "Remote")[0]
    assert not sourcing.keep("Director of Partnerships", "London, United Kingdom")[0]
    assert sourcing.keep("Director of Partnerships", "")[0]  # unstated location is kept for the reader


def test_fetch_parsers():
    jobs = sourcing.fetch_board(mock_client(GH), "greenhouse", "testco")
    assert jobs[0]["pay"].startswith("$250,000") and "<p>" not in jobs[0]["description"]
    lever = [{"text": "Head of Growth Partnerships", "hostedUrl": "https://jobs.lever.co/x/1", "categories": {"location": "New York, NY"},
              "descriptionPlain": "Own growth.", "lists": [{"text": "Requirements", "content": "<li>10 years</li>"}],
              "workplaceType": "hybrid", "createdAt": 1761000000000, "salaryRange": {"min": 200000, "max": 260000}}]
    lj = sourcing.fetch_board(mock_client(lever), "lever", "x")[0]
    assert lj["remote"] == "hybrid" and lj["pay"] == "$200,000–$260,000" and "10 years" in lj["description"]
    ashby = {"jobs": [{"title": "VP Partnerships", "jobUrl": "https://jobs.ashbyhq.com/y/1", "location": "Remote", "isRemote": True,
                       "descriptionPlain": "AI partnerships.", "compensation": {"compensationTierSummary": "$300K – $350K"},
                       "publishedAt": "2026-10-01"}]}
    aj = sourcing.fetch_board(mock_client(ashby), "ashby", "y")[0]
    assert aj["remote"] == "yes" and aj["pay"] == "$300K – $350K"


def test_board_run_fingerprint_and_close(client):
    from app.db import SessionLocal
    from app.models import Board, Posting

    with SessionLocal() as db:
        sourcing.seed_boards(db)
        assert db.query(Board).filter(Board.slug == "anthropic").count() == 1  # found in posting URLs / seed list
        db.query(Board).update({"active": False})
        db.add(Board(ats="greenhouse", slug="testco", company="TestCo"))
        db.commit()
        t1 = sourcing.run_boards(db, mock_client(GH))
        assert t1["new"] == 1 and t1["screened_out"] == 3  # Seoul and London are outside the test profile's locations
        p = db.query(Posting).filter(Posting.url.like("%testco/jobs/1")).one()
        assert p.bay_area and p.source == "greenhouse" and p.content_hash
        p.read_check = {"hash": p.content_hash}
        db.commit()
        assert sourcing.run_boards(db, mock_client(GH))["same"] == 1
        changed = json.loads(json.dumps(GH))
        changed["jobs"][0]["content"] = "Lead partnerships with AI companies."
        assert sourcing.run_boards(db, mock_client(changed))["changed"] == 1
        db.refresh(p)
        assert p.read_check == {}  # re-read after a change
        t4 = sourcing.run_boards(db, mock_client({"jobs": []}))
        assert t4["closed"] == 1
        db.refresh(p)
        assert p.status == "closed"
        db.query(Board).update({"active": True})
        db.query(Board).filter(Board.slug == "testco").delete()
        db.commit()


def test_majority_vote():
    r = [{"tags": ["a", "b"], "level_band": "VP", "role_cluster": "Partnerships", "years_required": 10},
         {"tags": ["a", "b", "c"], "level_band": "VP", "role_cluster": "Partnerships", "years_required": 12},
         {"tags": ["a"], "level_band": "Director", "role_cluster": "Partnerships", "years_required": 10}]
    m = requirements.majority(r)
    assert m["tags"] == ["a", "b"] and m["disputed"] == ["c"] and m["level_band"] == "VP" and m["years_required"] == 10
    assert not m["unanimous"]


def test_cost_and_cap(client, monkeypatch):
    from types import SimpleNamespace

    from app import llm
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import UsageLog

    u = SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    assert llm.cost_usd("claude-fable-5-1", u) == 15.0
    assert llm.cost_usd("claude-haiku-5-5", u) == 0.15
    s = get_settings()
    assert s.monthly_cap_usd == round(s.api_monthly_allowance_usd * s.budget_share, 2)
    with SessionLocal() as db:
        row = UsageLog(agent="test", model="claude-opus-5-5", cost_usd=s.monthly_cap_usd + 1)
        db.add(row)
        db.commit()
        with pytest.raises(llm.BudgetExceeded):
            llm.check_budget()
        db.delete(row)
        db.commit()
    llm.check_budget()


def test_golden_and_brief_number_check():
    assert golden()["failed"] == []
    data = {"score": {"now": 80.1, "before": 77.5}, "top": [{"match_score": 64}]}
    assert "80.1" in numbers_in(data)
    ok = check_brief("- Score 80.1, up from 77.5\n- Top match 64", data, None)
    assert ok["passed"], ok
    bad = check_brief("- Score 80.1; 92 percent chance of an interview", data, None)
    assert not bad["passed"] and any("92" in i for i in bad["issues"])


def test_weekly_pipeline_and_api(client):
    from app.agents.coordinator import enqueue, execute
    from app.db import SessionLocal
    from app.models import AgentRun

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"}).json()
    ah = {"Authorization": f"Bearer {login['token']}"}
    r = client.post("/api/agents/run", json={"kind": "weekly"}, headers=ah)
    assert r.status_code == 200
    with SessionLocal() as db:
        run = db.get(AgentRun, r.json()["run"]["id"])
        from app.agents import sourcing as src

        src_run = src.run_boards
        src.run_boards = lambda db, client=None: {"boards_ok": 0, "note": "offline test"}
        try:
            execute(db, run)
        finally:
            src.run_boards = src_run
        assert [s["agent"] for s in run.steps] == ["sourcing", "web_sourcing", "reader", "level", "index", "scoring", "evidence", "checker", "analyst"]
        assert run.status == "done", run.steps
        chk = next(s for s in run.steps if s["agent"] == "checker")["result"]
        assert chk["golden"]["failed"] == [] and all(not u["rule_violations"] for u in chk["users"])
        assert enqueue(db, "rescore").status == "queued"
    st = client.get("/api/agents/status", headers=ah).json()
    assert st["budget"]["cap_usd"] > 0 and st["runs"][0]["kind"] in ("rescore", "weekly")
    b = client.get("/api/agents/brief", headers=ah).json()
    hist = client.get("/api/agents/history", headers=ah).json()
    assert isinstance(hist["points"], list)
    assert b["brief"] is None or b["brief"]["body"]


def test_inbox_proposal_and_approval(client, tmp_path, monkeypatch):
    from app.agents import inbox
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import Proposal, ReferenceProfile

    monkeypatch.setattr(get_settings(), "inbox_dir", str(tmp_path))
    (tmp_path / "bad.json").write_text(json.dumps({"kind": "holders", "holders": [{"name": "X", "company": "A", "title": "B", "experience_text": "y"}]}))
    good = {"kind": "holders", "cluster": "Partnerships", "as_of": "2026-11", "source": "test", "holders": [
        {"company": "NewCo", "title": "Director of Partnerships", "education_text": "BS Computer Science, Stanford, 2010",
         "experience_text": "Experience\nDirector of Partnerships\nNewCo · Full-time\nJan 2020 - Present · 6 yrs 11 mos\n- Led partnerships."}]}
    (tmp_path / "hires_2026-11-02.json").write_text(json.dumps(good))
    with SessionLocal() as db:
        out = inbox.run(db, None)
        assert out["files"] == 2 and any("personal fields" in r.get("rejected", "") for r in out["results"])
        assert not list(tmp_path.glob("*.json"))  # raw files removed
        n0 = db.query(ReferenceProfile).count()
        prop = db.query(Proposal).filter(Proposal.kind == "holders", Proposal.status == "pending").order_by(Proposal.id.desc()).first()
        assert prop and "experience_text" not in json.dumps(prop.payload)
    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"}).json()
    ah = {"Authorization": f"Bearer {login['token']}"}
    assert client.post(f"/api/agents/proposals/{prop.id}", json={"decision": "approve"}, headers=ah).status_code == 200
    with SessionLocal() as db:
        assert db.query(ReferenceProfile).count() == n0 + 1
        db.query(ReferenceProfile).filter(ReferenceProfile.company == "NewCo").delete()
        db.commit()


def test_signup_closed_and_login_lock(client, monkeypatch):
    from app.config import get_settings
    from app.routers import auth

    s = get_settings()
    monkeypatch.setattr(s, "allow_signup", False)
    monkeypatch.setattr(s, "login_max_failures", 3)
    assert client.get("/api/auth/config").json() == {"signup_open": False}
    r = client.post("/api/auth/signup", json={"email": "new@example.com", "password": "password123", "name": "N"})
    assert r.status_code == 403
    auth._fails.clear()
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong-one"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"}).status_code == 429
    auth._fails.clear()
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"}).status_code == 200
    assert client.get("/docs").status_code == 404


def test_ask_agent_tools_and_loop(client, monkeypatch):
    from types import SimpleNamespace as NS

    from app.agents import ask_agent
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "v2@example.com").one()  # has experience text from test_api
        ctx = ask_agent.Ctx(db, u)
        sc = ask_agent.run_tool(ctx, "get_scorecard", {})
        assert sc["score"] is not None and len(sc["factors"]) == 10 and sc["level_read_from"]["band"]
        wi = ask_agent.run_tool(ctx, "what_if", {"changes": {"LV": 3}})
        assert wi["changes"] == {"LV": 3.0} and wi["delta"] <= 0
        assert "error" in ask_agent.run_tool(ctx, "what_if", {"changes": {"XX": 1}})
        ps = ask_agent.run_tool(ctx, "search_postings", {"limit": 3})
        assert ps["returned"] <= 3
        mk = ask_agent.run_tool(ctx, "get_market_requirements", {})
        assert mk["clusters"]
        assert "api_cap_usd" in ask_agent.run_tool(ctx, "get_agent_status", {})

        # Simulated model: one tool call, then an answer with one number that is not in tool data.
        score = sc["score"]
        block = lambda **k: NS(model_dump=lambda exclude_none=True: k, **k)  # noqa: E731
        script = [
            [block(type="tool_use", id="t1", name="what_if", input={"changes": {"LV": 3}})],
            [block(type="text", text=f"- Score {score}; at VP it would be {wi['score']}.\n- 97 percent of roles fit.")],
            [block(type="text", text=f"- Score {score}; at VP it would be {wi['score']}.")],
        ]
        calls = []

        def fake_create(**kw):
            calls.append(kw)
            return NS(content=script[len(calls) - 1]), "test-model"

        monkeypatch.setattr(ask_agent, "create", fake_create)
        monkeypatch.setattr(ask_agent, "run_tool", lambda c, n, a: {**wi, "score_now": score})
        out = ask_agent.answer(db, u, "What if I were VP?")
        assert out["mode"] == "agent" and "97" not in out["answer"]
        assert [s["tool"] for s in out["steps"]] == ["what_if", "number_check"]
        assert calls[-1]["tool_choice"] == {"type": "none"}


def test_posting_sections_and_incremental_index(client):
    from app.db import SessionLocal
    from app.models import Chunk, Posting
    from app.rag.index import posting_sections, update_postings

    secs = posting_sections("About the role\nLead partners.\nWhat you'll do\nOwn deals.\nQualifications:\n10+ years\nBenefits\nGood")
    assert [n for n, _ in secs] == ["About the role", "What you'll do", "Qualifications", "Benefits"]
    with SessionLocal() as db:
        first = update_postings(db)
        assert first["postings_indexed"] > 0
        again = update_postings(db)
        assert again["postings_reindexed"] == 0  # nothing changed
        p = db.query(Posting).filter(Posting.status == "open").first()
        p.description = (p.description or "") + "\nRequirements\nNew requirement line."
        db.commit()
        assert update_postings(db)["postings_reindexed"] == 1
        assert db.query(Chunk).filter(Chunk.source_ref == str(p.id), Chunk.title.like("%Requirements%")).count() == 1


def test_evidence_finder_guardrail_and_confirm(client, monkeypatch):
    from app.agents import evidence
    from app.db import SessionLocal
    from app.models import EvidenceSuggestion, User
    from app.rag.index import rebuild_user

    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "v2@example.com").one()
        rebuild_user(db, u)
        db.refresh(u)
        tags = evidence.missing_tags(evidence.evaluate(db, u), u.profile)
        assert tags, "expected at least one requirement the profile does not show"
        from app.rag.index import search

        own = search(db, u.id, "partnerships", k=1, types=("experience", "cv"), own_only=True)
        assert own and own[0][0].owner_id == u.id
        real = " ".join(own[0][0].text.split("\n")[1].split()[:8])
        answers = iter([{"match": 1, "quote": real, "excerpt": 1}, {"match": 1, "quote": "Invented line that is not in the text", "excerpt": 1}]
                       + [{"match": 0, "quote": "", "excerpt": 1}] * 20)
        monkeypatch.setattr(evidence, "llm_available", lambda: True)
        monkeypatch.setattr(evidence, "complete_json", lambda *a, **k: next(answers))
        db.query(EvidenceSuggestion).delete()
        db.commit()
        out = evidence.run_for_user(db, u)
        assert out["suggested"] == 1  # the invented quote was dropped
        s = db.query(EvidenceSuggestion).one()
        evidence.decide(db, u, s.id, True)
        db.refresh(u.profile)
        assert u.profile.tag_matches[s.tag]["source"] == "user"


def test_tag_labels_examples_and_reader_test(client):
    from app.agents import requirements
    from app.db import SessionLocal
    from app.models import Posting

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"}).json()
    ah = {"Authorization": f"Bearer {login['token']}"}
    with SessionLocal() as db:
        ps = db.query(Posting).filter(Posting.status == "open").order_by(Posting.id).limit(10).all()
        test_p = next(p for p in ps if requirements.is_test(p))
        train_p = next(p for p in ps if not requirements.is_test(p))
        for p in (test_p, train_p):
            p.read_check = {"hash": p.content_hash, "model_tags": ["func_partnerships", "domain_ai"], "disputed": ["domain_ai"]}
        db.commit()
        tid, trid = test_p.id, train_p.id
    r = client.get("/api/agents/tag-review", headers=ah).json()
    assert any(x["id"] == tid for x in r["postings"])
    for pid in (tid, trid):
        assert client.post(f"/api/agents/tag-review/{pid}", headers=ah,
                           json={"labels": {"func_partnerships": True, "domain_ai": False}}).json()["tags"].count("domain_ai") == 0
    with SessionLocal() as db:
        ev = requirements.evaluate_reader(db)
        assert ev["test_postings"] >= 1 and ev["precision"] == 0.5 and ev["recall"] == 1.0
        assert any(t == "domain_ai" for t, _ in ev["most_missed_tags"])
        other = db.query(Posting).filter(Posting.id != trid, Posting.status == "open").first()
        ex = requirements.examples_for(db, other, requirements.labeled(db))
        assert db.get(Posting, trid).company in ex and db.get(Posting, tid).title not in ex.split(":")[0]


def test_location_driven_sourcing(client, monkeypatch):
    from app.agents import sourcing
    from app.agents.coordinator import PIPELINES
    from app.db import SessionLocal
    from app.models import AgentRun

    assert "locations" in PIPELINES
    pat = sourcing._loc_pattern(["Seoul, South Korea", "Singapore"])
    assert sourcing.keep("Head of Partnerships, APAC", "Singapore", pat)[0]
    assert sourcing.keep("Director, Business Development", "Seoul, Korea", pat)[0]
    assert not sourcing.keep("Director, Business Development", "London, UK", pat)[0]
    assert sourcing.keep("Country Manager, Korea", "Seoul", pat)[0]  # kept; scored as outside your preferences
    login = client.post("/api/auth/login", json={"email": "v2@example.com", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {login['token']}"}
    r = client.put("/api/profile", json={"locations": ["SF Bay Area", "Seoul, South Korea"]}, headers=h).json()
    assert "search" in r.get("note", "")
    with SessionLocal() as db:
        assert "Seoul, South Korea" in sourcing.profile_locations(db)
        assert db.query(AgentRun).filter(AgentRun.kind == "locations").count() >= 1
    from app.scoring import _location_ok
    from types import SimpleNamespace as NS

    assert _location_ok(NS(remote_flag="no", location="Seoul", bay_area=False),
                        NS(remote_ok=True, locations=["Seoul, South Korea"]))


def test_level_assessor_and_soft_screen(client, monkeypatch):
    from types import SimpleNamespace as NS

    from app.agents import level
    from app.scoring import gate_split

    desc = ("We are seeking a Regional Manager to lead and scale our advertising business across Asia-Pacific. "
            "You will oversee a distributed team of Client Partners and Customer Success Managers. "
            "Own regional revenue goals and business performance across multiple markets. " * 4)
    p = NS(title="Regional Manager, Ads Solutions (APAC)", company="OpenAI", location="Singapore", pay_range="",
           description=desc, content_hash="h1", read_check={}, level_band="Manager", scope="")
    monkeypatch.setattr(level, "complete_json", lambda *a, **k: {
        "band": "Director", "scope": "regional", "confidence": "high", "summary": "Runs APAC ads with a team",
        "evidence": ["lead and scale our advertising business across Asia-Pacific", "an invented quote that is not there"]})
    a = level.assess(p)
    assert a["band"] == "Director" and a["title_band"] == "Manager" and len(a["evidence"]) == 1
    level.apply(p, a)
    assert p.level_band == "Director" and p.scope == "regional"
    monkeypatch.setattr(level, "complete_json", lambda *a, **k: {"band": "VP", "confidence": "high", "evidence": ["made up"]})
    b = level.assess(p)
    assert b["confidence"] == "low"  # no verifiable quote: the title band stands

    prof = NS(min_level="Director", locations=["SF Bay Area"], remote_ok=True, needs_sponsorship=False, excluded_title_terms=[])
    pv = NS(title="Country Manager, Korea", status="open", no_sponsorship=False, level_band="Director", scope="country",
            location="Seoul", remote_flag="no", bay_area=False)
    hard, soft = gate_split(pv, prof)
    assert not hard and any("single-country" in s for s in soft) and any("location" in s for s in soft)
    pv.status = "closed"
    assert gate_split(pv, prof)[0]


def test_matches_worth_a_look(client):
    login = client.post("/api/auth/login", json={"email": "v2@example.com", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {login['token']}"}
    m = client.get("/api/matches", headers=h).json()
    assert "worth_a_look" in m and all(w["outside"] for w in m["worth_a_look"])


def test_focus_plan(client):
    login = client.post("/api/auth/login", json={"email": "v2@example.com", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {login['token']}"}
    f = client.get("/api/scorecard/focus", headers=h).json()
    assert f["ready"] and f["standing"]["rank"] >= 1 and len(f["standing"]["lines"]) >= 3
    assert {x["state"] for x in f["versus_peers"]} <= {"lead", "gap", "level"}
    assert all({"kind", "title", "effect", "where"} <= set(a) for a in f["actions"])
    assert f["postings_considered"] >= f["strong_matches_now"] >= 0
