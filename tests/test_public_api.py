from flask import Flask
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ping_reports_bot_stopped(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["bot_running"] is False


def test_teams_reads_from_json(client, app):
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    teams_path = json_dir / "teams.json"
    teams_path.write_text(json.dumps([{"name": "Alpha"}]), encoding="utf-8")

    resp = client.get("/api/teams")
    assert resp.status_code == 200
    assert resp.get_json() == [{"name": "Alpha"}]


def _seed_standings_data(app, matches=None):
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    groups = {
        group: [f"{group} Team {number}" for number in range(1, 5)]
        for group in "ABCDEFGHIJKL"
    }
    groups["A"] = ["South Korea", "Czech Republic", "Turkey", "Cape Verde"]
    (json_dir / "team_meta.json").write_text(json.dumps({"groups": groups}), encoding="utf-8")
    (json_dir / "matches.json").write_text(json.dumps(matches or []), encoding="utf-8")
    return groups


def test_public_standings_returns_all_groups_without_authentication(client, app):
    groups = _seed_standings_data(app)
    response = client.get("/api/standings")
    assert response.status_code == 200
    payload = response.get_json()
    assert [group["group"] for group in payload["groups"]] == list("ABCDEFGHIJKL")
    assert all(len(group["teams"]) == 4 for group in payload["groups"])
    assert payload["completed_matches"] == 0
    assert payload["groups"][0]["teams"][0]["team"] in groups["A"]
    assert all(
        all(team[key] == 0 for key in ("mp", "w", "d", "l", "gf", "ga", "gd", "pts"))
        for group in payload["groups"] for team in group["teams"]
    )


def test_public_standings_calculates_results_and_sort_order(client, app):
    _seed_standings_data(app, [
        {"group": "A", "home": "Korea Republic", "away": "Czechia", "home_score": 3, "away_score": 1},
        {"group": "A", "home": "Turkey", "away": "Cabo Verde", "home_score": 2, "away_score": 2},
        {"group": "B", "home": "B Team 1", "away": "B Team 2", "home_score": 2, "away_score": 0},
        {"group": "B", "home": "B Team 3", "away": "B Team 4", "home_score": 3, "away_score": 1},
        {"group": "B", "home": "B Team 1", "away": "B Team 3", "home_score": 1, "away_score": 0},
        {"group": "C", "home": "C Team 1", "away": "C Team 2", "home_score": 3, "away_score": 1},
        {"group": "C", "home": "C Team 3", "away": "C Team 4", "home_score": 2, "away_score": 0},
    ])
    payload = client.get("/api/standings").get_json()
    group_a = payload["groups"][0]["teams"]
    assert [team["team"] for team in group_a] == ["South Korea", "Cape Verde", "Turkey", "Czech Republic"]
    assert group_a[0] == {
        "team": "South Korea", "mp": 1, "w": 1, "d": 0, "l": 0,
        "gf": 3, "ga": 1, "gd": 2, "pts": 3,
    }
    assert group_a[1]["d"] == 1 and group_a[1]["pts"] == 1 and group_a[1]["gd"] == 0
    group_b = payload["groups"][1]["teams"]
    assert [team["team"] for team in group_b[:2]] == ["B Team 1", "B Team 3"]
    assert group_b[0]["pts"] == 6
    assert group_b[1]["pts"] == 3
    group_c = payload["groups"][2]["teams"]
    assert [team["team"] for team in group_c[:2]] == ["C Team 1", "C Team 3"]
    assert group_c[0]["pts"] == group_c[1]["pts"] == 3
    assert group_c[0]["gd"] == group_c[1]["gd"] == 2
    assert group_c[0]["gf"] > group_c[1]["gf"]


def test_public_standings_ignores_non_final_and_malformed_fixtures(client, app):
    _seed_standings_data(app, [
        {"group": "A", "home": "South Korea", "away": "Turkey", "home_score": 4, "away_score": 0, "status": "postponed"},
        {"group": "A", "home": "South Korea", "away": "Turkey", "home_score": "", "away_score": ""},
        {"group": "A", "home": "South Korea", "away": "Turkey", "home_score": -1, "away_score": 0},
        {"group": "A", "home": "South Korea", "away": "Turkey", "home_score": 1, "away_score": 0, "stage": "Round of 32"},
    ])
    payload = client.get("/api/standings").get_json()
    assert payload["completed_matches"] == 0
    assert all(team["mp"] == 0 for team in payload["groups"][0]["teams"])


def test_public_standings_handles_missing_or_malformed_sources(client, app):
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    (json_dir / "team_meta.json").write_text("{bad json", encoding="utf-8")
    (json_dir / "matches.json").write_text('{"not": "a list"}', encoding="utf-8")
    response = client.get("/api/standings")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["groups"] == []
    assert payload["errors"]


def test_tables_page_is_wired_into_existing_navigation_and_loader():
    index_html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-page="tables">Tables</a>' in index_html
    assert '<section id="tables" class="page-section">' in index_html
    assert 'class="table-wrap tables-card"' in index_html
    assert 'class="table-title tables-title">Group Tables</h1>' in index_html
    assert [f'data-tables-group="{group}"' for group in ("ALL", *"ABCDEFGHIJKL")] == [
        token for token in (
            f'data-tables-group="{group}"' for group in ("ALL", *"ABCDEFGHIJKL")
        ) if token in index_html
    ]
    assert "case 'tables': await loadTables(); break;" in app_js
    assert "const TABLE_GROUPS = [...'ABCDEFGHIJKL'];" in app_js
    assert "Standings response does not contain 12 complete groups" in app_js
    assert "12 complete group tables" in app_js
    assert "wc:lastPage" in app_js
    assert "filtersWired" in app_js


def test_index_uses_document_relative_static_asset_paths(client):
    """
    Index assets should stay document-relative so reverse proxies that mount the
    app under a prefix (e.g. /panel/) do not break static URL resolution.
    """
    html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")

    # Positive checks: the intended mount-aware paths.
    assert 'href="style.css"' in html
    assert 'src="app.js"' in html
    assert 'src="user.js"' in html

    # Negative checks: guard against root-absolute regressions that 404 behind prefixes.
    assert 'href="/style.css"' not in html
    assert 'src="/app.js"' not in html
    assert 'src="/user.js"' not in html


def test_terms_uses_document_relative_static_asset_paths():
    """
    Terms assets should stay document-relative for prefix-based deployments
    (e.g. /panel/terms -> /panel/terms.css) to avoid 404s.
    """
    html = (ROOT / "WorldCupBot" / "static" / "terms.html").read_text(encoding="utf-8")

    # Positive checks: expected mount-aware asset references.
    assert 'href="terms.css"' in html
    assert 'src="terms.js"' in html

    # Negative checks: disallow root-absolute references that bypass mount prefixes.
    assert 'href="/terms.css"' not in html
    assert 'src="/terms.js"' not in html

def test_app_bootstraps_stage_constants_without_stage_js():
    """
    app.js now defines window.WorldCupStages when the standalone stage.js asset
    is unavailable so user-facing stage UI still works.
    """
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "if (!window.WorldCupStages) {" in app_js
    assert "const STAGE_ORDER = [" in app_js
    assert "const STAGE_PROGRESS = {" in app_js


def test_me_respects_masquerade_without_app_base_dir_config(tmp_path):
    """
    Ensure masquerade still works when app.config["BASE_DIR"] is unset.
    The route should fall back to the app static folder parent for config.json.
    """
    base_dir = tmp_path
    static_dir = base_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "config.json").write_text(json.dumps({"ADMIN_IDS": ["123"]}), encoding="utf-8")

    ctx = {
        "BASE_DIR": str(base_dir),
        "is_bot_running": lambda: False,
        "start_bot": lambda: True,
        "stop_bot": lambda: True,
        "restart_bot": lambda: True,
        "get_bot_resource_usage": lambda: {},
        "bot_last_start_ref": {"value": None},
        "bot_last_stop_ref": {"value": None},
    }

    from routes_public import create_public_routes

    app = Flask(__name__, static_folder=str(static_dir))
    app.secret_key = "test-secret"
    # Intentionally do not set app.config["BASE_DIR"].

    root_bp, api_bp, auth_bp = create_public_routes(ctx)
    app.register_blueprint(root_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "123", "username": "admin"}
        sess["wc_masquerade_id"] = "999"

    resp = client.get("/api/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["is_admin"] is True
    assert data["masquerading_as"] == "999"


def test_app_js_has_no_known_truncated_syntax_tokens():
    """
    Guard against previously observed truncated JS tokens that produced
    `SyntaxError: Invalid or unexpected token` at runtime.
    """
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")

    # Broken patterns seen in production errors / prior diffs.
    assert "createElementNS('http:\\n" not in app_js
    assert "src=\"https:\\n" not in app_js
    assert '/\\/embed\\/avatars\\\\\n' not in app_js

    # Ensure repaired snippets are present.
    assert "createElementNS('http://www.w3.org/2000/svg', 'g')" in app_js
    assert "https://flagcdn.com/w20/${safeIso}.png" in app_js
    assert r"/\/embed\/avatars\//.test(String(v.avatar_url))" in app_js


def test_split_requests_respond_accept_updates_players_and_history(client, app):
    """Main owner should be able to accept a pending split request from the public web endpoint."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    # Seed minimal ownership data where user 200 is the main owner of Brazil.
    players_path = json_dir / "players.json"
    players_path.write_text(json.dumps({
        "200": {"display_name": "Owner", "teams": [{"team": "Brazil", "ownership": {"main_owner": 200, "split_with": []}}]},
        "100": {"display_name": "Requester", "teams": []},
    }), encoding="utf-8")

    split_requests_path = json_dir / "split_requests.json"
    split_requests_path.write_text(json.dumps({
        "req1": {
            "requester_id": 100,
            "main_owner_id": 200,
            "team": "Brazil",
            "expires_at": 4102444800,
            "requested_percentage": 25
        }
    }), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "200", "username": "owner"}

    resp = client.post('/api/split_requests/respond', json={"id": "req1", "action": "accept"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["event"]["action"] == "accepted"

    # Pending request should be removed.
    pending_after = json.loads(split_requests_path.read_text(encoding="utf-8"))
    assert "req1" not in pending_after

    # Owner entry should include requester in split_with.
    players_after = json.loads(players_path.read_text(encoding="utf-8"))
    owner_teams = players_after["200"]["teams"]
    brazil_owner_row = next(t for t in owner_teams if t["team"] == "Brazil")
    assert 100 in brazil_owner_row["ownership"]["split_with"]

    # Requester should have team entry pointing to same main owner.
    requester_teams = players_after["100"]["teams"]
    brazil_requester_row = next(t for t in requester_teams if t["team"] == "Brazil")
    assert brazil_requester_row["ownership"]["main_owner"] == 200

    # Accepted web splits should persist and log the exact percentage map shown by the website.
    assert brazil_owner_row["ownership"]["percentages"] == {"200": 75.0, "100": 25.0}
    log_after = json.loads((json_dir / "split_requests_log.json").read_text(encoding="utf-8"))
    assert log_after[-1]["requested_percentage"] == 25.0
    assert log_after[-1]["percentages"] == {"200": 75.0, "100": 25.0}


def test_split_requests_respond_forbidden_for_non_owner(client, app):
    """Only the receiving main owner can resolve a split request via web API."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    (json_dir / "split_requests.json").write_text(json.dumps({
        "req2": {
            "requester_id": 100,
            "main_owner_id": 200,
            "team": "Argentina",
            "expires_at": 4102444800,
            "requested_percentage": 20
        }
    }), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "300", "username": "not-owner"}

    resp = client.post('/api/split_requests/respond', json={"id": "req2", "action": "decline"})
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "forbidden"


def test_split_requests_get_normalizes_history_owner_from_resolved_by(client, app):
    """Resolved split rows should expose the main owner name even for legacy Discord-cog log entries."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    (json_dir / "players.json").write_text(json.dumps({
        "100": {"display_name": "Siren", "teams": []},
        "200": {"display_name": "Owner", "teams": []},
    }), encoding="utf-8")
    (json_dir / "split_requests_log.json").write_text(json.dumps([
        {
            "request_id": "legacy-req",
            "status": "accepted",
            "team": "Brazil",
            "requester_id": 100,
            "resolved_by": 200,
            "timestamp": "2026-06-01T13:59:58+00:00",
        }
    ]), encoding="utf-8")

    resp = client.get("/api/split_requests")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pending"] == []

    resolved = data["resolved"]
    assert len(resolved) == 1
    row = resolved[0]
    assert row["action"] == "accepted"
    assert row["from_id"] == "100"
    assert row["from_username"] == "Siren"
    assert row["from"] == "Siren"
    assert row["to_id"] == "200"
    assert row["main_owner_id"] == "200"
    assert row["to_username"] == "Owner"
    assert row["to"] == "Owner"


def test_split_history_renderer_uses_resolved_by_as_owner_fallback():
    """The browser renderer should understand legacy history rows before API normalization is available."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "ev.receiver_id ?? ev.resolved_by ?? ev.main_owner ?? ev.to" in app_js


def test_bot_watcher_handles_maintenance_announcement_commands():
    """Regression guard: runtime command watcher should process maintenance announcements."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert 'if kind in ("maintenance_mode_enabled", "maintenance_mode_disabled"):' in bot_py
    assert 'await self._handle_maintenance_announcement(data)' in bot_py
    assert 'async def _handle_maintenance_announcement(self, data: dict):' in bot_py


def test_maintenance_announcement_channel_selection_requires_send_permission():
    """Guard against choosing a named channel where the bot cannot send messages."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert 'if ch.name.lower() == target and self._can_send_in_channel(guild, ch):' in bot_py


def test_maintenance_announcements_publish_in_news_channels():
    """Guard that maintenance announcements attempt crossposting in news channels."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert "if isinstance(channel, discord.TextChannel) and channel.is_news():" in bot_py
    assert "await sent.publish()" in bot_py


def test_maintenance_announcement_retries_fallback_channels_when_send_fails():
    """Guard that posting logic iterates fallback channels when initial send fails."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert "for ch in channels:" in bot_py
    assert "if await self._post_maintenance_message(guild, ch, message):" in bot_py


def test_maintenance_channel_selection_does_not_skip_when_member_cache_missing():
    """Guard that missing guild member cache does not block announcement attempts."""
    bot_py = (ROOT / "WorldCupBot" / "bot.py").read_text(encoding="utf-8")
    assert "if not member:" in bot_py
    assert "return True" in bot_py


def test_bets_create_requires_login(client):
    """Creating a bet from the web should require an authenticated Discord session."""
    resp = client.post("/api/bets/create", json={
        "bet_title": "Will Team A win?",
        "wager": "100 coins",
        "option1": "Team A",
        "option2": "Team B",
    })
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "login_required"


def test_bets_create_persists_bet_and_enqueues_command(client, app):
    """Creating from Bets page should store the bet and queue a Discord post command."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "1234", "username": "creator"}

    resp = client.post("/api/bets/create", json={
        "bet_title": "Will Team A win?",
        "wager": "100 coins",
        "option1": "Team A",
        "option2": "Team B",
    })
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    bet = payload["bet"]
    assert bet["option1_user_id"] == "1234"
    assert bet["option2_user_id"] is None

    bets_path = json_dir / "bets.json"
    bets = json.loads(bets_path.read_text(encoding="utf-8"))
    assert isinstance(bets, list) and len(bets) == 1
    assert bets[0]["bet_title"] == "Will Team A win?"

    commands_path = json_dir / "bot_commands.jsonl"
    lines = [ln for ln in commands_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "Expected a queued runtime command for Discord posting."
    cmd = json.loads(lines[-1])
    assert cmd["kind"] == "bet_created"
    assert cmd["data"]["bet_id"] == bet["bet_id"]


def test_bets_claim_updates_record_and_enqueues_command(client, app):
    """Claiming from the Bets page should fill option2 and queue a Discord edit command."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "bets.json").write_text(json.dumps([{
        "bet_id": "00001",
        "bet_title": "Who wins?",
        "wager": "50",
        "option1": "A",
        "option2": "B",
        "option1_user_id": "111",
        "option1_user_name": "creator",
        "option2_user_id": None,
        "option2_user_name": None,
        "channel_id": None,
        "message_id": None,
        "winner": None,
    }]), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "222", "username": "claimer"}

    resp = client.post("/api/bets/00001/claim", json={})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["bet"]["option2_user_id"] == "222"

    bets = json.loads((json_dir / "bets.json").read_text(encoding="utf-8"))
    assert bets[0]["option2_user_id"] == "222"
    assert bets[0]["option2_user_name"] == "claimer"

    commands_path = json_dir / "bot_commands.jsonl"
    lines = [ln for ln in commands_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cmd = json.loads(lines[-1])
    assert cmd["kind"] == "bet_claimed"
    assert cmd["data"]["bet_id"] == "00001"


def test_bet_page_announcer_handles_runtime_bet_commands():
    """Guard that the bot-side announcer processes queue commands for create + claim."""
    cog_py = (ROOT / "WorldCupBot" / "COGS" / "BetPageAnnouncer.py").read_text(encoding="utf-8")
    assert 'if kind == "bet_created":' in cog_py
    assert 'elif kind == "bet_claimed":' in cog_py
    assert "await self._handle_bet_created(bet_id)" in cog_py
    assert "await self._handle_bet_claimed(bet_id)" in cog_py
    assert 'discord.ui.Button(label="Claim Bet"' in cog_py
    assert '"bets"' in cog_py
    assert '"announcements"' not in cog_py


def test_bet_page_announcer_uses_single_sidecar_tmp_file():
    """State writes should use one deterministic .tmp sidecar file."""
    cog_py = (ROOT / "WorldCupBot" / "COGS" / "BetPageAnnouncer.py").read_text(encoding="utf-8")
    assert 'tmp_path = f"{path}.tmp"' in cog_py
    assert "tempfile.mkstemp" not in cog_py


def test_bet_page_announcer_skips_redundant_state_writes():
    """Polling loop should avoid rewriting offset state when unchanged."""
    cog_py = (ROOT / "WorldCupBot" / "COGS" / "BetPageAnnouncer.py").read_text(encoding="utf-8")
    assert "if self._saved_offset == int(self._offset):" in cog_py
    assert "self._saved_offset = int(self._offset)" in cog_py


def test_bets_create_modal_markup_exists_in_index():
    """Bets page should expose a first-class create modal instead of prompt dialogs."""
    html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="bets-create-backdrop"' in html
    assert 'id="bets-create-modal"' in html
    assert 'id="bets-create-submit"' in html
    assert 'id="bets-create-title-input"' in html


def test_bets_create_uses_modal_workflow_instead_of_window_prompts():
    """Regression guard: creating bets should use the custom modal flow."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "async function openBetsCreateModal(onCreated)" in app_js
    assert "createBtn.onclick = () => openBetsCreateModal(loadAndRenderBets);" in app_js


def test_fanzone_vote_blocks_repeat_votes_from_same_discord_user(client, app):
    """A logged-in Discord user should be counted once per fixture across sessions."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "298121351871594497", "username": "alpha"}

    payload = {"fixture_id": "2026-06-17-L-ENG-CRO", "choice": "away"}
    first = client.post("/api/fanzone/vote", json=payload)
    assert first.status_code == 200
    assert first.get_json()["ok"] is True

    second = client.post("/api/fanzone/vote", json=payload)
    assert second.status_code == 200
    assert second.get_json()["ok"] is True

    votes = json.loads((json_dir / "fan_votes.json").read_text(encoding="utf-8"))
    fx = votes["fixtures"]["2026-06-17-L-ENG-CRO"]
    # Strictly one counted vote for this Discord account.
    assert fx["away"] == 1
    assert fx["home"] == 0
    assert fx["draw"] == 0
    assert len(fx.get("voters", {})) == 1
    assert fx["voters"]["298121351871594497"] == "away"


def test_fanzone_vote_preexisting_browser_vote_does_not_double_count_new_discord_id(client, app):
    """Legacy browser voter records should not allow duplicate tally increments."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    votes_path = json_dir / "fan_votes.json"
    votes_path.write_text(json.dumps({
        "fixtures": {
            "fixture-1": {
                "home": 0,
                "away": 1,
                "draw": 0,
                "voters": {"1120014084679663616": "away"},
            }
        }
    }), encoding="utf-8")
    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "1120014084679663616", "username": "bravo"}

    resp = client.post("/api/fanzone/vote", json={"fixture_id": "fixture-1", "choice": "away"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    votes = json.loads(votes_path.read_text(encoding="utf-8"))
    fx = votes["fixtures"]["fixture-1"]
    # Count remains unchanged when the same Discord account retries.
    assert fx["away"] == 1
    assert fx["voters"]["1120014084679663616"] == "away"


def test_fanzone_fixture_state_uses_logged_in_discord_vote_after_refresh(client, app):
    """Fixture state should report last_choice from the authenticated Discord voter map."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "fan_votes.json").write_text(json.dumps({
        "fixtures": {
            "fixture-refresh": {
                "home": 0,
                "away": 1,
                "draw": 0,
                "voters": {"298121351871594497": "away"},
            }
        }
    }), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "298121351871594497", "username": "alpha"}

    resp = client.get("/api/fanzone/fixture-refresh")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["last_choice"] == "away"


def test_world_map_stage_label_uses_stage_not_ownership():
    """World map country card should label the tournament progression as Stage."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "stageEl.textContent  = 'Stage: ' + (stage || '-');" in app_js
    assert "stageEl.textContent  = 'Ownership: ' + (stage || '-');" not in app_js


def test_world_map_prize_share_uses_ownership_percentages():
    """World map prize share should mirror the Ownership page percentage data."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function formatMapSharePercent(value)" in app_js
    assert "function formatMapPrizeShare(ownerIds, percentages, ownersCount)" in app_js
    assert "ownership ? ownership.percentages : {}" in app_js
    assert "percentages: row.percentages || {}" in app_js
    assert "formatMapSharePercent(shareMap[id])" in app_js
    assert "formatOwnershipPercent(shareMap[id])" not in app_js
    assert "Older ownership records may not have a percentages map" in app_js


def test_world_map_tooltip_avoids_edge_clipping():
    """World map hover tooltip should be viewport-positioned and not inherit panel card styles."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    style_css = (ROOT / "WorldCupBot" / "static" / "style.css").read_text(encoding="utf-8")

    # The tooltip content must not use .map-info because that class is an
    # absolutely-positioned side panel, which causes wrong measurements/clipping.
    assert '<div class="map-tip-card">' in app_js
    assert '<div class="map-info">' not in app_js
    assert "position: fixed;" in style_css
    assert "window.innerWidth" in app_js
    assert "window.innerHeight" in app_js


def test_reassign_modal_uses_typeahead_player_picker():
    """Ownership reassignment should let admins type to narrow known players."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")
    style_css = (ROOT / "WorldCupBot" / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="reassign-picker"' in index_html
    assert 'role="combobox"' in index_html
    assert 'placeholder="Type a player name..."' in index_html
    assert "picker.addEventListener('input'" in app_js
    assert 'label.includes(needle)' in app_js
    assert "li.textContent = 'No matching players';" in app_js
    assert '#reassign-picker::placeholder' in style_css


def test_dashboard_quick_options_use_country_action_flow_and_single_game_list():
    """Dashboard match controls should use structured options without duplicate cards."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")
    style_css = (ROOT / "WorldCupBot" / "static" / "style.css").read_text(encoding="utf-8")

    assert index_html.count('id="dashboard-live-games"') == 1
    assert index_html.count('id="dashboard-live-refresh"') == 1
    assert 'id="quick-announce-message"' not in index_html
    assert 'id="quick-country-options"' in index_html
    assert 'placeholder="e.g. 23 or 90+1"' in index_html
    assert 'id="quick-full-time-confirm"' in index_html
    assert 'id="quick-final-score"' in index_html
    assert 'id="quick-yellow-cards"' in index_html
    assert 'id="quick-red-cards"' in index_html
    assert 'id="quick-announce-cancel"' in index_html
    assert 'id="quick-full-time-open"' in index_html
    assert 'grid-template-columns: repeat(4, minmax(0, 1fr));' in style_css
    assert '.quick-announce-options {' in style_css
    assert 'display: grid;' in style_css
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in style_css
    assert '#quick-announce-modal .modal-foot' in style_css
    assert 'width: min(92vw, 520px);' in style_css
    assert "eventType !== 'half_time'" in app_js
    assert "async function openQuickAnnouncementModal(button)" in app_js
    assert "await ensureTeamIsoLoaded();" in app_js
    assert "const goalCount = (country)" not in app_js
    assert "deriving a score from them could silently submit an incorrect result" in app_js
    assert "elapsed <= QUICK_MATCH_WINDOW_MS || !fixture.completed" in app_js


def test_bets_page_exposes_claim_button_flow():
    """Bets page should keep an explicit claim action in the web table UI."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "claimBtn.textContent = 'Claim Bet';" in app_js
    assert "await postJSON(`/api/bets/${encodeURIComponent(bet.bet_id)}/claim`, {});" in app_js


def test_fixtures_only_include_matches_within_next_48_hours_for_public(client, app):
    """Public fixture feed should only expose matches starting within the next 48 hours."""
    import datetime

    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    within = (now + datetime.timedelta(hours=12)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    outside = (now + datetime.timedelta(hours=72)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    (json_dir / "matches.json").write_text(json.dumps([
        {"id": "in-window", "home": "USA", "away": "Canada", "utc": within},
        {"id": "out-window", "home": "Spain", "away": "France", "utc": outside},
    ]), encoding="utf-8")

    resp = client.get("/api/fixtures")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["ok"] is True
    assert data["visibility_hours"] == 48
    assert data["admin_override"] is False
    assert [f["id"] for f in data["fixtures"]] == ["in-window"]




def test_fixtures_include_results_query_keeps_scored_past_and_undated_matches(client, app):
    """Results view should receive saved scores after fixtures leave the upcoming window."""
    import datetime

    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    past = (now - datetime.timedelta(hours=12)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    outside = (now + datetime.timedelta(hours=72)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    (json_dir / "matches.json").write_text(json.dumps([
        {"id": "past-result", "home": "USA", "away": "Canada", "utc": past, "home_score": 2, "away_score": 1},
        {"id": "undated-result", "home": "France", "away": "Germany", "home_score": 0, "away_score": 0},
        {"id": "hidden-future", "home": "Spain", "away": "Brazil", "utc": outside},
    ]), encoding="utf-8")

    resp = client.get("/api/fixtures?include_results=1")
    assert resp.status_code == 200
    fixtures = resp.get_json()["fixtures"]

    assert [fixture["id"] for fixture in fixtures] == ["past-result", "undated-result"]
    assert fixtures[0]["home_score"] == 2
    assert fixtures[0]["away_score"] == 1
    assert fixtures[1]["home_score"] == 0
    assert fixtures[1]["away_score"] == 0


def test_results_panel_requests_completed_fixture_scores():
    """The Results panel must opt into completed scores from the fixture API."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    assert "fetchJSON('/api/fixtures?include_results=1')" in app_js


def test_fixtures_api_exposes_penalty_winner_for_tied_result(client, app):
    """The frontend needs the shootout winner to progress a tied knockout match."""
    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "matches.json").write_text(
        json.dumps([{
            "id": "M97",
            "home": "USA",
            "away": "Canada",
            "home_score": 1,
            "away_score": 1,
            "winner_side": "away",
        }]),
        encoding="utf-8",
    )

    resp = client.get("/api/fixtures?include_results=1")

    assert resp.status_code == 200
    fixture = resp.get_json()["fixtures"][0]
    assert fixture["home_score"] == 1
    assert fixture["away_score"] == 1
    assert fixture["winner_side"] == "away"


def test_fixtures_include_all_query_returns_future_matches_beyond_48_hours(client, app):
    """include_all=1 should expose all future fixtures for world-map next-match rendering."""
    import datetime

    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    within = (now + datetime.timedelta(hours=12)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    outside = (now + datetime.timedelta(hours=72)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    (json_dir / "matches.json").write_text(json.dumps([
        {"id": "in-window", "home": "USA", "away": "Canada", "utc": within},
        {"id": "out-window", "home": "Spain", "away": "France", "utc": outside},
    ]), encoding="utf-8")

    resp = client.get("/api/fixtures?include_all=1")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["ok"] is True
    assert data["admin_override"] is False
    assert [f["id"] for f in data["fixtures"]] == ["in-window", "out-window"]


def test_fixtures_admin_view_overrides_48_hour_window(client, app):
    """Configured admins can request admin_view=1 to bypass the 48-hour visibility filter."""
    import datetime

    base_dir = Path(app.config["BASE_DIR"])
    json_dir = base_dir / "JSON"
    json_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    outside = (now + datetime.timedelta(hours=72)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    (json_dir / "matches.json").write_text(json.dumps([
        {"id": "out-window", "home": "Spain", "away": "France", "utc": outside},
    ]), encoding="utf-8")

    with client.session_transaction() as sess:
        sess["wc_user"] = {"discord_id": "123", "username": "admin"}

    resp = client.get("/api/fixtures?admin_view=1")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["ok"] is True
    assert data["admin_override"] is True
    assert [f["id"] for f in data["fixtures"]] == ["out-window"]


def test_fixture_form_uses_saved_score_before_legacy_declaration():
    """Last-5 form and progression should derive outcomes from the saved score."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")

    compute_records = app_js[
        app_js.index("  function computeRecords(fixtures, winnersMap){"):
        app_js.index("  function recordBar(rec){")
    ]
    assert "const winnerSide = winnerSideForFixture(f, winnersMap);" in compute_records
    assert "winnersMap?.[f.id]" not in compute_records
    assert "if (homeScore > awayScore) return 'home';" in app_js
    assert "if (awayScore > homeScore) return 'away';" in app_js
    assert "const tiedWinner = String(fixture?.winner_side || '').toLowerCase();" in app_js
    assert "if (tiedWinner === 'home' || tiedWinner === 'away') return tiedWinner;" in app_js

    # Legacy declarations remain a fallback for old fixtures without scores.
    assert "candidateKeys.push(String(matchNo), `Match ${matchNo}`);" in app_js


def test_fixtures_page_removes_manual_declare_country_controls():
    """Adding a score should replace the separate Declare COUNTRY controls."""
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")
    card_html = app_js[
        app_js.index("  function cardHTML(f, stats) {"):
        app_js.index("    function applyStatsToCard(card, stats) {")
    ]
    assert "Declare ${f.home}" not in card_html
    assert "Declare Draw" not in card_html
    assert "Declare ${f.away}" not in card_html


def test_result_form_submits_separate_penalty_winner_side():
    """The sole result UI should submit an advancing side for tied shootouts."""
    index_html = (ROOT / "WorldCupBot" / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "WorldCupBot" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="fixtures-result-winner-side"' in index_html
    assert '<option value="home">Home team advances</option>' in index_html
    assert '<option value="away">Away team advances</option>' in index_html
    assert "winner_side: winnerSide" in app_js
    assert "A penalty shootout winner can only be selected when the score is tied." in app_js
