def test_parse_synthetic_payload():
    from core.ingestor.parser import parse_github_webhook

    payload = {
        "repo": "owner/repo",
        "run_id": "123456",
        "workflow": "CI",
        "job": "test",
        "step": "Run pytest",
        "exit_code": 1,
        "log_tail": "FAILED test_foo",
        "changed_files": ["src/main.py"],
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    event = parse_github_webhook(payload, "push")
    assert event is not None
    assert event.repo == "owner/repo"
    assert event.run_id == "123456"
    assert event.exit_code == 1
    assert event.changed_files == ["src/main.py"]


def test_parse_github_workflow_run_failure():
    from core.ingestor.parser import parse_github_webhook

    payload = {
        "workflow_run": {
            "id": 999,
            "name": "CI",
            "conclusion": "failure",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        "repository": {"full_name": "owner/repo"},
    }
    event = parse_github_webhook(payload, "workflow_run")
    assert event is not None
    assert event.repo == "owner/repo"
    assert event.run_id == "999"
    assert event.workflow == "CI"
    assert event.job == "unknown"
    assert event.step == "unknown"
    assert event.exit_code == 1


def test_parse_github_workflow_run_success_returns_none():
    from core.ingestor.parser import parse_github_webhook

    payload = {
        "workflow_run": {
            "id": 999,
            "name": "CI",
            "conclusion": "success",
        },
        "repository": {"full_name": "owner/repo"},
    }
    event = parse_github_webhook(payload, "workflow_run")
    assert event is None


def test_parse_unrecognised_payload_returns_none():
    from core.ingestor.parser import parse_github_webhook

    event = parse_github_webhook({"action": "opened"}, "pull_request")
    assert event is None
