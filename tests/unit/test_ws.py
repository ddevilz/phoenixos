# tests/unit/test_ws.py
import json
from unittest.mock import AsyncMock


async def test_broadcast_with_no_clients_does_not_raise() -> None:
    from core.api.ws import _ConnectionManager

    mgr = _ConnectionManager()
    await mgr.broadcast({"type": "test", "run_id": "r1", "timestamp": "t", "payload": {}})


async def test_broadcast_sends_to_connected_client() -> None:
    from core.api.ws import _ConnectionManager

    mgr = _ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mgr._connections.append(mock_ws)

    await mgr.broadcast(
        {"type": "signature_extracted", "run_id": "r1", "timestamp": "t", "payload": {}}
    )

    mock_ws.send_text.assert_called_once()
    msg = json.loads(mock_ws.send_text.call_args[0][0])
    assert msg["type"] == "signature_extracted"
    assert msg["run_id"] == "r1"


async def test_broadcast_removes_dead_connection() -> None:
    from core.api.ws import _ConnectionManager

    mgr = _ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock(side_effect=Exception("connection closed"))
    mgr._connections.append(mock_ws)

    await mgr.broadcast({"type": "test", "run_id": "r1", "timestamp": "t", "payload": {}})

    assert mock_ws not in mgr._connections


async def test_broadcast_event_function_no_clients() -> None:
    from core.api.ws import broadcast_event

    await broadcast_event("graph_updated", "run-1", {"node_id": "sig-1"})
