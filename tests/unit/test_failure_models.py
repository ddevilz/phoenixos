from datetime import datetime, timezone

import pytest
from core.models.failure import FailureEvent, FailureSignature, FailureSignatureExtract
from pydantic import ValidationError


def _now() -> datetime:
    return datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_failure_event_roundtrip() -> None:
    event = FailureEvent(
        id="evt-1",
        repo="owner/repo",
        run_id="99",
        workflow="CI",
        job="CI",
        step="unknown",
        exit_code=1,
        log_tail="ERROR: test failed",
        changed_files=["src/main.py"],
        timestamp=_now(),
    )
    assert event.repo == "owner/repo"
    assert event.exit_code == 1
    assert event.changed_files == ["src/main.py"]


def test_failure_signature_empty_embedding_allowed() -> None:
    sig = FailureSignature(
        id="sig-1",
        summary="Import error in auth module",
        category="build_error",
        affected_component="src/auth.py",
        embedding=[],
        first_seen=_now(),
        last_seen=_now(),
        occurrence_count=1,
    )
    assert sig.embedding == []
    assert sig.occurrence_count == 1


def test_failure_signature_extract_rejects_bad_category() -> None:
    with pytest.raises(ValidationError):
        FailureSignatureExtract(
            summary="something broke",
            category="unknown_category",  # type: ignore[arg-type]
            affected_component="src/main.py",
        )


def test_failure_signature_extract_valid_categories() -> None:
    for cat in ("test_failure", "build_error", "contract_violation", "flaky"):
        obj = FailureSignatureExtract(
            summary="desc",
            category=cat,  # type: ignore[arg-type]
            affected_component="src/foo.py",
        )
        assert obj.category == cat
