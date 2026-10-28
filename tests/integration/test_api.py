from __future__ import annotations

from tests.conftest import read_sse


async def test_healthz_and_readyz(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    response = await client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["db"] == "ok"


async def test_session_lifecycle(client, session_headers):
    session_id, headers = session_headers

    listed = await client.get("/api/v1/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == session_id for item in listed.json()["items"])

    messages = await client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert messages.json()["items"] == []

    deleted = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 204

    after = await client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=headers)
    assert after.status_code == 404


async def test_auth_matrix(client):
    # no credentials -> 401 on list
    assert (await client.get("/api/v1/chat/sessions")).status_code == 401

    created = await client.post("/api/v1/chat/sessions", json={"locale": "zh-CN"})
    body = created.json()
    sid, token = body["session"]["id"], body["session_token"]

    # unknown session -> 404 even with a valid token
    other = await client.post("/api/v1/chat/sessions", json={"locale": "en"})
    other_sid = other.json()["session"]["id"]
    response = await client.get(f"/api/v1/chat/sessions/{other_sid}/messages", headers={"X-Chat-Session-Token": token})
    assert response.status_code == 404

    # bind requires bearer
    response = await client.post(f"/api/v1/chat/sessions/{sid}:bind", headers={"X-Chat-Session-Token": token})
    assert response.status_code == 401

    # bind with bearer succeeds, second bind to another uid conflicts
    response = await client.post(
        f"/api/v1/chat/sessions/{sid}:bind",
        headers={"X-Chat-Session-Token": token, "Authorization": "Bearer mock:1"},
    )
    assert response.status_code == 200
    response = await client.post(
        f"/api/v1/chat/sessions/{sid}:bind",
        headers={"X-Chat-Session-Token": token, "Authorization": "Bearer mock:2"},
    )
    assert response.status_code == 409

    # bound session visible via uid only
    response = await client.get("/api/v1/chat/sessions", headers={"Authorization": "Bearer mock:1"})
    assert any(item["id"] == sid for item in response.json()["items"])


async def test_stream_career_flow(client, session_headers):
    session_id, headers = session_headers
    events = await read_sse(
        client,
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        {"message": "INFP 适合做什么职业？", "client_message_id": "c1"},
        headers,
    )
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    # sources/actions arrive before the first token (design §9.6)
    assert names.index("sources") < names.index("token")
    assert names.index("actions") < names.index("token")

    payload = dict(events)
    assert payload["sources"]["sources"], "career flow should cite sources"
    assert any(a["url"].startswith("/zh-CN/") for a in payload["actions"]["actions"])
    assert payload["done"]["finish_reason"] == "stop"
    answer = "".join(d["delta"] for n, d in events if n == "token")
    assert len(answer) > 20

    # persisted with intent
    messages = await client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=headers)
    items = messages.json()["items"]
    assert [m["role"] for m in items] == ["user", "assistant"]
    assert items[1]["status"] == "completed"
    assert items[1]["intent"] == "career_fit"
    assert items[1]["sources"] and items[1]["actions"]


async def test_stream_guardrail_skips_rag(client, session_headers):
    session_id, headers = session_headers
    events = await read_sse(
        client,
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        {"message": "我想自杀"},
        headers,
    )
    payload = dict(events)
    assert payload["sources"]["sources"] == []
    assert payload["actions"]["actions"] == []
    answer = "".join(d["delta"] for n, d in events if n == "token")
    assert "紧急服务" in answer


async def test_stream_personal_report_requires_login(client, session_headers):
    session_id, headers = session_headers

    anon = await read_sse(
        client,
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        {"message": "根据我的报告，我适合什么工作？"},
        headers,
    )
    anon_answer = "".join(d["delta"] for n, d in anon if n == "token")
    assert "登录后" in anon_answer
    assert dict(anon)["sources"]["sources"], "anonymous still gets generic sources"

    logged = await read_sse(
        client,
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        {"message": "根据我的报告，我适合什么工作？", "client_message_id": "r1"},
        {**headers, "Authorization": "Bearer mock:7"},
    )
    logged_answer = "".join(d["delta"] for n, d in logged if n == "token")
    assert "INFP" in logged_answer
    actions = dict(logged)["actions"]["actions"]
    assert actions[0]["url"] == "/zh-CN/account/reports"


async def test_duplicate_client_message_id_conflicts(client, session_headers):
    session_id, headers = session_headers
    await read_sse(
        client,
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        {"message": "你好", "client_message_id": "dup"},
        headers,
    )
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        json={"message": "你好", "client_message_id": "dup"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_overlong_message_rejected(client, session_headers):
    session_id, headers = session_headers
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        json={"message": "x" * 5000},
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_feedback_on_assistant_message(client, session_headers):
    session_id, headers = session_headers
    await read_sse(
        client,
        f"/api/v1/chat/sessions/{session_id}/messages:stream",
        {"message": "INTJ 是什么类型？"},
        headers,
    )
    messages = await client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=headers)
    assistant_id = [m for m in messages.json()["items"] if m["role"] == "assistant"][0]["id"]

    response = await client.post(
        f"/api/v1/chat/messages/{assistant_id}/feedback",
        json={"rating": "helpful", "reason": None},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["rating"] == "helpful"

    # feedback on user message is rejected
    user_id = [m for m in messages.json()["items"] if m["role"] == "user"][0]["id"]
    response = await client.post(
        f"/api/v1/chat/messages/{user_id}/feedback",
        json={"rating": "unhelpful", "reason": "other"},
        headers=headers,
    )
    assert response.status_code == 400


async def test_error_envelope_shape(client):
    response = await client.get("/api/v1/chat/sessions/nope/messages", headers={"X-Chat-Session-Token": "st_x"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]
