from datetime import datetime, timezone


def test_failure_event_fields():
    from core.models.failure import FailureEvent

    event = FailureEvent(
        id="abc-123",
        repo="owner/repo",
        run_id="999",
        workflow="CI",
        job="test",
        step="Run pytest",
        exit_code=1,
        log_tail="FAILED test_foo",
        changed_files=["src/main.py"],
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert event.repo == "owner/repo"
    assert event.exit_code == 1
    assert event.changed_files == ["src/main.py"]


def test_failure_event_rejects_missing_required():
    import pytest
    from core.models.failure import FailureEvent
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FailureEvent()  # type: ignore
