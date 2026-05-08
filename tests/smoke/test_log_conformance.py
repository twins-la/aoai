"""Log records emitted by the twin must satisfy LOGGING.md §3.2."""

from twins_local.logs import VALID_OUTCOMES, VALID_PLANES


def _conformant(record: dict) -> None:
    required = {
        "timestamp",
        "twin",
        "tenant_id",
        "correlation_id",
        "plane",
        "operation",
        "resource",
        "outcome",
        "reason",
        "details",
    }
    assert required.issubset(record.keys()), record
    assert record["twin"] == "aoai"
    assert record["plane"] in VALID_PLANES
    assert record["outcome"] in VALID_OUTCOMES
    if record["outcome"] == "failure":
        assert record["reason"] and isinstance(record["reason"], str)
    assert isinstance(record["details"], dict)


def test_resource_create_emits_normative_log(client, tenant, tenant_headers):
    client.post("/_twin/resources", json={}, headers=tenant_headers)
    logs = client.get("/_twin/logs", headers=tenant_headers).get_json()["logs"]
    assert logs
    for record in logs:
        _conformant(record)
    creates = [r for r in logs if r["operation"] == "twin.resource.create"]
    assert creates


def test_chat_completion_emits_data_plane_log(
    client, tenant_headers, resource, api_key, deployment
):
    client.post(
        f"/{resource['resource_id']}/openai/deployments/{deployment['deployment_id']}/chat/completions",
        json={"messages": [{"role": "user", "content": "log me"}]},
        headers=api_key["headers"],
    )
    logs = client.get("/_twin/logs", headers=tenant_headers).get_json()["logs"]
    chat_logs = [r for r in logs if r["operation"] == "data.chat.completion"]
    assert chat_logs
    for record in chat_logs:
        _conformant(record)
        assert record["plane"] == "data"
