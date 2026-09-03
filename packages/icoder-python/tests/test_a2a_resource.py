import json

import httpx
import pytest

from icoder_sdk import (
    A2AProtocolError,
    A2ATransportError,
    iCoDerClient,
    iCoDerConfig,
)


def _client(handler):
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_a2a_multi_turn_get_and_delete_contract():
    calls = []
    context_id = "11111111-1111-4111-8111-111111111111"

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request, body))
        if request.method == "POST":
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "kind": "message",
                    "role": "agent",
                    "messageId": f"agent-{len(calls)}",
                    "contextId": context_id,
                    "parts": [],
                    "metadata": {},
                },
            })
        if request.method == "GET":
            return httpx.Response(200, json={"id": context_id, "items": [{}, {}, {}, {}]})
        return httpx.Response(200, json={
            "jsonrpc": "2.0",
            "id": None,
            "result": {
                "kind": "context",
                "contextId": context_id,
                "deleted": True,
                "reason": "user_requested",
            },
        })

    client = _client(handler)
    try:
        first = client.a2a.message_send("note-completeness-agent", "first")
        second = client.a2a.message_send(
            "note-completeness-agent", "second", context_id=first["contextId"]
        )
        context = client.a2a.get_context("note-completeness-agent", context_id)
        deleted = client.a2a.delete_context(context_id)
    finally:
        client.close()

    assert second["contextId"] == context_id
    assert len(context["items"]) == 4
    assert deleted["deleted"] is True
    assert all(request.headers["A2A-Protocol-Version"] == "0.3" for request, _ in calls)
    assert calls[1][1]["params"]["message"]["contextId"] == context_id


def test_a2a_protocol_error_does_not_retain_details():
    def handler(_request):
        return httpx.Response(500, json={
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": {
                    "a2a_error_code": "PLANNING_FAILED",
                    "details": "patient-secret-value",
                },
            },
        })

    client = _client(handler)
    try:
        with pytest.raises(A2AProtocolError) as raised:
            client.a2a.message_send("note-completeness-agent", "synthetic")
    finally:
        client.close()

    assert raised.value.jsonrpc_code == -32603
    assert raised.value.a2a_error_code == "PLANNING_FAILED"
    assert "patient-secret-value" not in str(raised.value)


def test_a2a_transport_error_does_not_retain_request_or_body():
    def handler(_request):
        return httpx.Response(500, json={"detail": "patient-secret-value"})

    client = _client(handler)
    try:
        with pytest.raises(A2ATransportError) as raised:
            client.a2a.message_send("note-completeness-agent", "synthetic")
    finally:
        client.close()

    assert raised.value.http_status == 500
    assert "patient-secret-value" not in str(raised.value)
    assert not hasattr(raised.value, "request")
    assert not hasattr(raised.value, "response")


def test_a2a_v1_async_task_poll_list_cancel_and_subscription_resume():
    calls = []
    task_reads = 0

    def handler(request):
        nonlocal task_reads
        body = json.loads(request.content) if request.content else None
        calls.append((request, body))
        path = request.url.path
        if path.endswith("/message:send"):
            return httpx.Response(200, json={
                "task": {
                    "id": "task-1",
                    "contextId": "context-1",
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                    "history": [],
                    "metadata": {},
                }
            })
        if path.endswith("/message:stream"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=(
                    "id: 1\nevent: task\n"
                    'data: {"task":{"id":"task-stream"}}\n\n'
                    "id: 2\nevent: artifact-update\n"
                    'data: {"artifactUpdate":{"taskId":"task-stream",'
                    '"append":false,"lastChunk":false}}\n\n'
                    "id: 3\nevent: artifact-update\n"
                    'data: {"artifactUpdate":{"taskId":"task-stream",'
                    '"append":true,"lastChunk":true}}\n\n'
                ),
            )
        if path.endswith("/tasks/task-1:subscribe"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=(
                    "id: 2\nevent: status-update\n"
                    'data: {"statusUpdate":{"taskId":"task-1"}}\n\n'
                    "id: 3\nevent: artifact-update\n"
                    'data: {"artifactUpdate":{"taskId":"task-1"}}\n\n'
                ),
            )
        if path.endswith("/tasks/task-1:cancel"):
            return httpx.Response(200, json={
                "id": "task-1",
                "status": {"state": "TASK_STATE_CANCELED"},
            })
        if path.endswith("/tasks/task-1"):
            task_reads += 1
            state = "TASK_STATE_WORKING" if task_reads == 1 else "TASK_STATE_COMPLETED"
            return httpx.Response(200, json={
                "id": "task-1",
                "status": {"state": state},
                "artifacts": [],
            })
        if path.endswith("/tasks"):
            return httpx.Response(200, json={
                "tasks": [{"id": "task-1"}],
                "pageSize": 10,
                "totalSize": 1,
                "nextPageToken": "",
            })
        raise AssertionError(path)

    client = _client(handler)
    try:
        submitted = client.a2a.message_send_v1(
            "note-completeness-agent",
            "safe note",
            message_id="message-1",
            return_immediately=True,
        )["task"]
        completed = client.a2a.wait_task_v1(
            "note-completeness-agent",
            submitted["id"],
            timeout=1,
            poll_interval=0.001,
        )
        listed = client.a2a.list_tasks_v1(
            "note-completeness-agent",
            page_size=10,
            include_artifacts=True,
        )
        events = list(client.a2a.subscribe_task_v1(
            "note-completeness-agent",
            "task-1",
            after_sequence=1,
            last_event_id="1",
        ))
        direct_events = list(client.a2a.message_stream_v1(
            "note-completeness-agent",
            "safe streamed note",
            context_id="context-input",
            task_id="task-input",
            message_id="message-stream-1",
        ))
        canceled = client.a2a.cancel_task_v1(
            "note-completeness-agent",
            "task-1",
        )
    finally:
        client.close()

    assert completed["status"]["state"] == "TASK_STATE_COMPLETED"
    assert listed["totalSize"] == 1
    assert [event["eventType"] for event in events] == [
        "status-update",
        "artifact-update",
    ]
    assert "statusUpdate" in events[0]
    assert "artifactUpdate" in events[1]
    assert [event["eventType"] for event in direct_events] == [
        "task",
        "artifact-update",
        "artifact-update",
    ]
    assert direct_events[1]["artifactUpdate"]["append"] is False
    assert direct_events[1]["artifactUpdate"]["lastChunk"] is False
    assert direct_events[2]["artifactUpdate"]["append"] is True
    assert direct_events[2]["artifactUpdate"]["lastChunk"] is True
    assert canceled["status"]["state"] == "TASK_STATE_CANCELED"
    assert all(request.headers["A2A-Version"] == "1.0" for request, _ in calls)
    send_call = next(item for item in calls if item[0].url.path.endswith("message:send"))
    assert send_call[1]["configuration"]["returnImmediately"] is True
    stream_call = next(item for item in calls if item[0].url.path.endswith("message:stream"))
    assert stream_call[0].headers["A2A-Version"] == "1.0"
    assert stream_call[1]["message"]["messageId"] == "message-stream-1"
    assert stream_call[1]["message"]["contextId"] == "context-input"
    assert stream_call[1]["message"]["taskId"] == "task-input"
    subscribe_call = next(item for item in calls if item[0].url.path.endswith(":subscribe"))
    assert subscribe_call[0].headers["Last-Event-ID"] == "1"
    assert subscribe_call[0].url.params["afterSequence"] == "1"


def test_a2a_v1_wait_returns_on_resumable_interruption():
    def handler(request):
        assert request.url.path.endswith("/tasks/task-input")
        return httpx.Response(200, json={
            "id": "task-input",
            "contextId": "context-input",
            "status": {"state": "TASK_STATE_INPUT_REQUIRED"},
            "artifacts": [],
            "history": [],
            "metadata": {},
        })

    client = _client(handler)
    try:
        settled = client.a2a.wait_task_v1(
            "note-completeness-agent",
            "task-input",
            timeout=0.1,
            poll_interval=0.001,
        )
    finally:
        client.close()
    assert settled["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"


def test_a2a_v1_error_extracts_only_stable_reason():
    def handler(_request):
        return httpx.Response(404, json={
            "error": {
                "code": 404,
                "status": "NOT_FOUND",
                "message": "Task not found",
                "details": [{
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "TASK_NOT_FOUND",
                    "metadata": {"secret": "patient-secret-value"},
                }],
            }
        })

    client = _client(handler)
    try:
        with pytest.raises(A2AProtocolError) as raised:
            client.a2a.get_task_v1("note-completeness-agent", "missing")
    finally:
        client.close()

    assert raised.value.a2a_error_code == "TASK_NOT_FOUND"
    assert "patient-secret-value" not in str(raised.value)


def test_agentic_trace_export_and_feedback_contract():
    calls = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request, body))
        if request.url.path.endswith("/trace"):
            return httpx.Response(200, json={
                "traces": [], "nextPageToken": None, "totalSize": None,
            })
        if request.url.path.endswith("/training-authorization") and request.method != "DELETE":
            return httpx.Response(200, json={
                "id": "ftg-1", "feedbackId": "fb/one", "taskId": "task/one",
                "trainingAuthorized": True, "authorizationStatus": "active",
                "purposeOfUse": "quality_improvement",
                "dataScope": "feedback_metadata_only",
                "expiresAt": "2026-08-23T00:00:00Z",
                "createdAt": "2026-08-22T00:00:00Z",
                "updatedAt": "2026-08-22T00:00:00Z",
                "revokedAt": None, "version": 1,
            })
        if request.method == "POST":
            return httpx.Response(201, json={
                "id": "fb-1", "taskId": "task-1",
                "rating": body["rating"], "normalizedScore": 1.0,
                "labels": body["labels"], "reason": None,
                "createdAt": "2026-08-22T00:00:00Z",
                "target": body.get("target"),
            })
        if request.method == "GET":
            return httpx.Response(200, json={"feedbacks": []})
        return httpx.Response(204)

    client = _client(handler)
    try:
        trace = client.a2a.export_context_traces("context/one", page_size=20)
        feedback = client.a2a.submit_task_feedback("context/one", "task/one", {
            "rating": {"scale": "binary", "value": 1},
            "labels": ["helpful"],
            "target": {"messageId": "message-1"},
        })
        listed = client.a2a.list_task_feedback("context/one", "task/one")
        deleted = client.a2a.delete_task_feedback("context/one", "task/one")
        training = client.a2a.authorize_feedback_for_training(
            "context/one", "task/one", "fb/one", {
                "purposeOfUse": "quality_improvement",
                "dataScope": "feedback_metadata_only",
                "expiresAt": "2026-08-23T00:00:00Z",
                "approvalReference": "qi-review-001",
                "acknowledgement": True,
            },
        )
        client.a2a.get_feedback_training_authorization(
            "context/one", "task/one", "fb/one",
        )
        client.a2a.revoke_feedback_training_authorization(
            "context/one", "task/one", "fb/one",
        )
    finally:
        client.close()

    assert trace["traces"] == []
    assert feedback["id"] == "fb-1"
    assert listed == {"feedbacks": []}
    assert deleted is None
    assert calls[0][0].url.params["pageSize"] == "20"
    assert calls[1][1]["target"]["messageId"] == "message-1"
    assert training["trainingAuthorized"] is True
    assert calls[4][0].url.raw_path.decode().endswith(
        "/tasks/task%2Fone/feedback/fb%2Fone/training-authorization"
    )
    assert calls[4][0].method == "PUT"
    assert calls[4][1]["dataScope"] == "feedback_metadata_only"
    assert calls[-1][0].method == "DELETE"


def test_agentic_v2_context_task_and_artifact_resource_contract():
    calls = []

    def handler(request):
        calls.append(request)
        context = {
            "id": "context-1",
            "agentId": "agent-1",
            "taskCount": 1,
            "createdAt": "2026-08-22T00:00:00Z",
            "updatedAt": "2026-08-22T00:00:01Z",
            "expiresAt": "2026-08-23T00:00:00Z",
        }
        task = {
            "id": "task-1",
            "contextId": "context-1",
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [],
            "history": [],
            "metadata": {},
        }
        path = request.url.path
        if request.method == "DELETE":
            return httpx.Response(204)
        if path.endswith("/artifacts/artifact/1"):
            return httpx.Response(200, json={
                "artifactId": "artifact/1", "parts": [{"text": "result"}],
                "metadata": {},
            })
        if path.endswith("/tasks/task/1"):
            return httpx.Response(200, json=task)
        if path.endswith("/tasks"):
            return httpx.Response(200, json={
                "tasks": [task], "nextPageToken": None, "totalSize": 1,
            })
        if path.endswith("/contexts/context/1"):
            return httpx.Response(200, json={**context, "tasks": [task]})
        if path.endswith("/contexts"):
            return httpx.Response(200, json={
                "contexts": [context], "nextPageToken": "next", "totalSize": 1,
            })
        raise AssertionError(path)

    client = _client(handler)
    try:
        contexts = client.a2a.list_contexts_v2(
            agent_id="agent/1",
            from_time="2026-08-01T00:00:00Z",
            page_size=10,
        )
        context = client.a2a.get_context_v2("context/1", history_length=2)
        tasks = client.a2a.list_context_tasks_v2(
            "context/1", page_size=5, history_length=1
        )
        task = client.a2a.get_context_task_v2("context/1", "task/1")
        artifact = client.a2a.get_task_artifact_v2(
            "context/1", "task/1", "artifact/1"
        )
        deleted = client.a2a.delete_context_v2("context/1")
    finally:
        client.close()

    assert contexts["totalSize"] == 1
    assert context["taskCount"] == 1
    assert tasks["tasks"][0]["id"] == "task-1"
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert artifact["artifactId"] == "artifact/1"
    assert deleted is None
    assert calls[0].url.params["agentId"] == "agent/1"
    assert calls[1].url.params["historyLength"] == "2"
    assert calls[2].url.params["historyLength"] == "1"
    assert calls[4].url.raw_path.split(b"?", 1)[0].endswith(
        b"/contexts/context%2F1/tasks/task%2F1/artifacts/artifact%2F1"
    )
    assert all(request.headers["A2A-Version"] == "1.0" for request in calls)


def test_agentic_agent_usage_contract():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={
            "granularity": "day",
            "from": "2026-08-01T00:00:00Z",
            "to": "2026-08-03T00:00:00Z",
            "totals": {"invocations": 3, "uniqueContexts": 2},
            "buckets": [{
                "periodStart": "2026-08-01T00:00:00Z",
                "periodEnd": "2026-08-02T00:00:00Z",
                "invocations": 3,
                "uniqueContexts": 2,
            }],
        })

    client = _client(handler)
    try:
        usage = client.a2a.get_agent_usage(
            "agent/one",
            from_time="2026-08-01T00:00:00Z",
            to_time="2026-08-03T00:00:00Z",
            granularity="hour",
        )
        with pytest.raises(ValueError, match="granularity"):
            client.a2a.get_agent_usage("agent", granularity="month")
    finally:
        client.close()

    assert usage["granularity"] == "day"
    assert usage["totals"]["uniqueContexts"] == 2
    assert captured[0].url.raw_path.split(b"?", 1)[0].endswith(
        b"/agents/agent%2Fone/usage"
    )
    assert captured[0].url.params["from"] == "2026-08-01T00:00:00Z"
    assert captured[0].url.params["granularity"] == "hour"


def test_managed_artifact_object_contract_and_one_time_download():
    calls = []
    object_payload = {
        "objectId": "obj/1", "artifactId": "artifact/1",
        "filename": "result.json", "mediaType": "application/json",
        "sizeBytes": 2, "sha256": "a" * 64, "status": "available",
        "malwareScanStatus": "clean", "dlpScanStatus": "clear",
        "dataClassification": "deidentified", "rejectionCode": None,
        "scanEngine": "icoder-safe-file-v1",
        "createdAt": "2026-08-22T00:00:00Z",
        "scannedAt": "2026-08-22T00:00:01Z",
    }
    authorization = {
        "objectId": "obj/1", "expiresAt": "2026-08-22T00:01:00Z",
        "singleUse": True, "purposeOfUse": "treatment",
        "part": {
            "url": "https://api.cn.icoder.cloud/api/v2/agentic/artifact-objects/download/grant-123",
            "filename": "result.json", "mediaType": "application/json",
        },
    }

    def handler(request):
        calls.append(request)
        path = request.url.path
        if "/artifact-objects/download/grant-" in path:
            return httpx.Response(200, content=b"{}")
        if request.method == "POST" and path.endswith(":authorize-download"):
            return httpx.Response(200, json=authorization)
        if request.method == "POST":
            return httpx.Response(201, json=object_payload)
        if request.method == "GET":
            return httpx.Response(200, json={"objects": [object_payload], "totalSize": 1})
        return httpx.Response(204)

    client = _client(handler)
    try:
        uploaded = client.a2a.upload_task_artifact_object_v2(
            "context/1", "task/1", "artifact/1",
            raw="e30=", filename="result.json", media_type="application/json",
        )
        listed = client.a2a.list_task_artifact_objects_v2(
            "context/1", "task/1", "artifact/1"
        )
        authorized = client.a2a.authorize_task_artifact_object_download_v2(
            "context/1", "task/1", "artifact/1", "obj/1",
            purpose_of_use="treatment", expires_in_seconds=30,
        )
        downloaded = client.a2a.download_authorized_artifact_object_v2(authorized)
        deleted = client.a2a.delete_task_artifact_object_v2(
            "context/1", "task/1", "artifact/1", "obj/1"
        )
    finally:
        client.close()

    assert uploaded["status"] == "available"
    assert listed["totalSize"] == 1
    assert authorized["singleUse"] is True
    assert downloaded == b"{}"
    assert deleted is None
    assert calls[0].url.raw_path.endswith(
        b"/contexts/context%2F1/tasks/task%2F1/artifacts/artifact%2F1/objects"
    )
    assert calls[2].url.raw_path.endswith(b"/objects/obj%2F1:authorize-download")
    assert json.loads(calls[2].content)["purposeOfUse"] == "treatment"
    assert calls[3].url.query == b""
    assert calls[3].headers["Authorization"] == "Bearer token"
    assert calls[4].method == "DELETE"
    assert all(call.headers.get("A2A-Version") == "1.0" for call in calls[:3])

    with pytest.raises(ValueError, match="purpose_of_use"):
        client.a2a.authorize_task_artifact_object_download_v2(
            "context", "task", "artifact", "object", purpose_of_use="research"
        )
    with pytest.raises(ValueError, match="configured origin"):
        client.a2a.download_authorized_artifact_object_v2({
            "part": {
                "url": "https://evil.example/api/v2/agentic/artifact-objects/download/grant-123"
            }
        })


def test_a2a_v1_agent_card_discovery_contract():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={
            "name": "Tenant Agent",
            "description": "Scoped Agent",
            "version": "1.0.0",
            "supportedInterfaces": [{
                "url": "https://api.cn.icoder.cloud/a2a",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            }],
            "capabilities": {"streaming": True, "pushNotifications": False},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["application/json"],
            "skills": [{
                "id": "run", "name": "Run", "description": "Run Agent", "tags": ["a2a"],
            }],
        })

    client = _client(handler)
    try:
        card = client.a2a.get_agent_card("agent/one")
    finally:
        client.close()

    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert captured[0].url.raw_path.decode() == (
        "/api/v2/agentic/agents/agent%2Fone/.well-known/agent-card.json"
    )
    assert captured[0].headers["A2A-Version"] == "1.0"
