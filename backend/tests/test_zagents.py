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
    assert not sourcing.keep("Country Manager, Japan", "Tokyo")[0]
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
        assert t1["new"] == 1 and t1["screened_out"] == 3
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
        assert [s["agent"] for s in run.steps] == ["sourcing", "web_sourcing", "reader", "index", "scoring", "checker", "analyst"]
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
