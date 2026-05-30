from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_SAMPLE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc..def 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,7 @@ def validate_token(token):
+    logger.debug("validating token")
     return jwt.decode(token, SECRET)
diff --git a/src/models/user.py b/src/models/user.py
index 111..222 100644
--- a/src/models/user.py
+++ b/src/models/user.py
@@ -1,3 +1,4 @@
+from datetime import datetime
 class User:
     pass
"""


async def test_parse_from_raw_extracts_changed_files() -> None:
    from core.ingestor.diff_parser import parse_from_raw

    result = parse_from_raw(_SAMPLE_DIFF)

    assert "src/auth.py" in result.changed_files
    assert "src/models/user.py" in result.changed_files
    assert result.diff == _SAMPLE_DIFF
    assert result.test_contents == {}


async def test_parse_from_raw_empty_diff() -> None:
    from core.ingestor.diff_parser import parse_from_raw

    result = parse_from_raw("")

    assert result.changed_files == []
    assert result.diff == ""
    assert result.test_contents == {}


async def test_fetch_and_parse_calls_github_apis() -> None:
    from core.ingestor.diff_parser import PRDiff, fetch_and_parse

    with (
        patch("core.ingestor.diff_parser._fetch_diff", new_callable=AsyncMock, return_value=_SAMPLE_DIFF),
        patch("core.ingestor.diff_parser._fetch_pr_head_sha", new_callable=AsyncMock, return_value="abc123"),
        patch("core.ingestor.diff_parser._fetch_file_contents", new_callable=AsyncMock, return_value="def test_validate(): pass"),
    ):
        result = await fetch_and_parse("https://github.com/owner/repo/pull/42")

    assert isinstance(result, PRDiff)
    assert "src/auth.py" in result.changed_files
    assert result.diff == _SAMPLE_DIFF


async def test_fetch_and_parse_skips_missing_test_files() -> None:
    from core.ingestor.diff_parser import fetch_and_parse

    with (
        patch("core.ingestor.diff_parser._fetch_diff", new_callable=AsyncMock, return_value=_SAMPLE_DIFF),
        patch("core.ingestor.diff_parser._fetch_pr_head_sha", new_callable=AsyncMock, return_value="abc123"),
        patch("core.ingestor.diff_parser._fetch_file_contents", new_callable=AsyncMock, return_value=None),
    ):
        result = await fetch_and_parse("https://github.com/owner/repo/pull/42")

    assert result.test_contents == {}


async def test_parse_pr_url_invalid_raises() -> None:
    from core.ingestor.diff_parser import _parse_pr_url

    with pytest.raises(ValueError, match="Cannot parse PR URL"):
        _parse_pr_url("https://notgithub.com/foo")


async def test_evals_run_with_raw_diff() -> None:
    from unittest.mock import AsyncMock, patch
    from httpx import ASGITransport, AsyncClient
    from core.models.failure import JudgeResult
    from core.main import app

    _pass = JudgeResult(judge="behavior", score=0.9, verdict="pass", reasoning="ok", flags=[])

    with (
        patch("core.judge.behavior.BehaviorJudge.judge", new_callable=AsyncMock, return_value=_pass),
        patch("core.judge.security.SecurityJudge.judge", new_callable=AsyncMock,
              return_value=JudgeResult(judge="security", score=0.9, verdict="pass", reasoning="ok", flags=[])),
        patch("core.judge.regression.RegressionJudge.judge", new_callable=AsyncMock,
              return_value=JudgeResult(judge="regression", score=0.9, verdict="pass", reasoning="ok", flags=[])),
        patch("core.judge.regression.fetch_similar_signatures", new_callable=AsyncMock, return_value=[]),
        patch("core.db.neo4j.neo4j_session"),
        patch("core.judge.graph_writer.write_eval_result", new_callable=AsyncMock, return_value="eid"),
        patch("core.api.ws.broadcast_event", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/evals/run", json={"diff": _SAMPLE_DIFF})

    assert r.status_code == 200
    body = r.json()
    assert "trust_score" in body
    assert "verdict" in body


async def test_evals_run_missing_both_fields_returns_422() -> None:
    from httpx import ASGITransport, AsyncClient

    from core.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/evals/run", json={})

    assert r.status_code == 422
