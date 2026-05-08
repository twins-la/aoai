"""Public info endpoints + explainer page."""


def test_health(client):
    resp = client.get("/_twin/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["twin"] == "aoai"
    assert body["version"]


def test_scenarios_lists_supported(client):
    resp = client.get("/_twin/scenarios")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.get_json()["scenarios"]}
    assert {"chat-completions", "embeddings", "dual-auth"}.issubset(names)


def test_references(client):
    resp = client.get("/_twin/references")
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.get_json()["references"]]
    assert any("Azure OpenAI" in t for t in titles)


def test_settings(client):
    resp = client.get("/_twin/settings")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["twin"] == "aoai"
    assert body["base_url"]


def test_agent_instructions_endpoint(client):
    resp = client.get("/_twin/agent-instructions")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    text = resp.get_data(as_text=True)
    assert "aoai.twins.la" in text
    assert "api-key" in text


def test_explainer_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "aoai" in text.lower()
