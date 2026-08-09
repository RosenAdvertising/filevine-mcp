"""PII-free logging and diagnostic-output regressions."""

from __future__ import annotations

import logging

import pytest

from filevine_mcp import client, server
from filevine_mcp.client import FileVineClient, TokenManager
from filevine_mcp.setup import oauth_flow, verify

PII_MARKER = "person.name+private@example.test"
SECRET_MARKER = "secret-response-body-marker"

CONFIRMATION_GATES = [
    ("archive_project", (PII_MARKER,)),
    ("remove_contact_from_project", (PII_MARKER, "contact")),
    ("delete_collection_item", (PII_MARKER, "selector", "item")),
    ("remove_project_team_member", (PII_MARKER, "user")),
    ("delete_invoice", (PII_MARKER, "invoice")),
    ("finalize_invoice", (PII_MARKER, "invoice")),
    ("approve_invoice", (PII_MARKER,)),
    ("remove_tag_from_contacts", (PII_MARKER,)),
    ("delete_task", (PII_MARKER,)),
    ("remove_tag_from_notes", (PII_MARKER,)),
    ("delete_document", (PII_MARKER,)),
    ("remove_tag_from_documents", (PII_MARKER,)),
    ("delete_folder", (PII_MARKER,)),
    ("create_billing_item", (PII_MARKER,)),
    ("update_billing_item", (PII_MARKER, "billing-item")),
    ("delete_billing_item", (PII_MARKER,)),
    ("create_payment", (PII_MARKER,)),
    ("create_payment_and_apply", (PII_MARKER,)),
    ("delete_webhook_subscription", (PII_MARKER,)),
    ("delete_share_link", (PII_MARKER,)),
    ("delete_team", (PII_MARKER,)),
]


@pytest.mark.parametrize(("tool_name", "args"), CONFIRMATION_GATES)
def test_every_confirmation_rejection_logs_a_pii_free_reason(
    caplog: pytest.LogCaptureFixture,
    tool_name: str,
    args: tuple[str, ...],
) -> None:
    caplog.set_level(logging.WARNING)
    result = getattr(server, tool_name)(*args)

    assert "confirm=True" in result
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.event == "tool_call_rejected"
    assert record.tool == tool_name
    assert record.reason == "confirmation_required"
    assert PII_MARKER not in caplog.text


def test_argument_validation_log_omits_raw_fields_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    result = server.create_project(fields_json=f'{{"name":"{PII_MARKER}"')

    assert "Invalid fields_json" in result
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.event == "tool_call_rejected"
    assert record.tool == "create_project"
    assert record.reason == "invalid_arguments"
    assert PII_MARKER not in caplog.text


class FakeResponse:
    status_code = 418
    text = SECRET_MARKER
    content = SECRET_MARKER.encode()
    ok = False
    headers: dict[str, str] = {}

    def json(self):
        return {"error": SECRET_MARKER}


class FreshToken:
    def is_expired(self) -> bool:
        return False


class FakeSession:
    def request(self, *args, **kwargs):
        return FakeResponse()


def test_api_error_never_includes_upstream_response_body() -> None:
    instance = object.__new__(FileVineClient)
    instance.tm = FreshToken()
    instance.session = FakeSession()

    with pytest.raises(RuntimeError) as exc_info:
        instance._request("GET", "Users/Me")

    assert "418" in str(exc_info.value)
    assert SECRET_MARKER not in str(exc_info.value)


def test_token_errors_never_include_identity_response_body(monkeypatch) -> None:
    monkeypatch.setattr(client, "CLIENT_ID", "configured")
    monkeypatch.setattr(client, "CLIENT_SECRET", "configured")
    monkeypatch.setattr(client, "FILEVINE_PAT", "configured")
    monkeypatch.setattr(client.requests, "post", lambda *args, **kwargs: FakeResponse())

    manager = object.__new__(TokenManager)
    with pytest.raises(RuntimeError) as exc_info:
        manager.fetch()

    assert "418" in str(exc_info.value)
    assert SECRET_MARKER not in str(exc_info.value)


def test_setup_token_errors_never_include_identity_response_body(monkeypatch) -> None:
    monkeypatch.setattr(
        oauth_flow.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        oauth_flow.fetch_token("client", "secret", "https://identity.test", "pat")

    assert "418" in str(exc_info.value)
    assert SECRET_MARKER not in str(exc_info.value)


def test_missing_org_guard_logs_only_a_reason_code(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(client, "ORG_ID", "")
    caplog.set_level(logging.WARNING)

    with pytest.raises(ValueError):
        FileVineClient()

    assert len(caplog.records) == 1
    assert caplog.records[0].reason == "missing_org_id"
    assert PII_MARKER not in caplog.text


def test_verify_cli_does_not_print_user_profile(monkeypatch, capsys) -> None:
    class SuccessfulClient:
        def get_me(self):
            return {
                "fullName": PII_MARKER,
                "email": PII_MARKER,
                "sub": PII_MARKER,
            }

    monkeypatch.setattr(verify, "FileVineClient", SuccessfulClient)
    verify.main()
    output = capsys.readouterr()

    assert "credentials verified" in output.out
    assert PII_MARKER not in output.out
    assert PII_MARKER not in output.err


def test_verify_cli_sanitizes_exceptions(monkeypatch, capsys) -> None:
    class FailingClient:
        def __init__(self):
            raise RuntimeError(SECRET_MARKER)

    monkeypatch.setattr(verify, "FileVineClient", FailingClient)
    with pytest.raises(SystemExit):
        verify.main()
    output = capsys.readouterr()

    assert "Verification failed" in output.out
    assert SECRET_MARKER not in output.out
    assert SECRET_MARKER not in output.err
