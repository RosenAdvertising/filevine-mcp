"""Regression coverage for every ID-bearing client path call site.

The transport boundary is replaced, so rejected identifiers must fail before
any HTTP call, including a preliminary read in a merge/update operation.
"""

import inspect
from unittest.mock import Mock

import pytest
import requests

from filevine_mcp.client import FileVineClient

CASES = [
    ("get_user", "user_id"),
    ("get_user_tasks", "user_id"),
    ("get_user_appointments", "user_id"),
    ("get_user_recent_projects", "user_id"),
    ("get_user_project_access", "user_id"),
    ("get_project", "project_id"),
    ("update_project", "project_id"),
    ("archive_project", "project_id"),
    ("get_project_vitals", "project_id"),
    ("get_project_form", "project_id"),
    ("get_project_form", "selector"),
    ("update_project_form", "project_id"),
    ("update_project_form", "selector"),
    ("get_project_contacts", "project_id"),
    ("add_contact_to_project", "project_id"),
    ("update_project_contact", "project_contact_id"),
    ("update_project_contact", "project_id"),
    ("remove_contact_from_project", "project_contact_id"),
    ("remove_contact_from_project", "project_id"),
    ("list_collection_items", "project_id"),
    ("list_collection_items", "selector"),
    ("get_collection_item", "project_id"),
    ("get_collection_item", "selector"),
    ("get_collection_item", "unique_id"),
    ("create_collection_item", "project_id"),
    ("create_collection_item", "selector"),
    ("update_collection_item", "project_id"),
    ("update_collection_item", "selector"),
    ("update_collection_item", "unique_id"),
    ("delete_collection_item", "project_id"),
    ("delete_collection_item", "selector"),
    ("delete_collection_item", "unique_id"),
    ("get_project_team", "project_id"),
    ("get_project_team_member", "project_id"),
    ("get_project_team_member", "user_id"),
    ("update_project_team_member", "project_id"),
    ("update_project_team_member", "user_id"),
    ("remove_project_team_member", "project_id"),
    ("remove_project_team_member", "user_id"),
    ("add_team_member", "project_id"),
    ("list_project_appointments", "project_id"),
    ("create_project_appointment", "project_id"),
    ("list_project_notes", "project_id"),
    ("pin_note_to_project", "note_id"),
    ("pin_note_to_project", "project_id"),
    ("unpin_note_from_project", "note_id"),
    ("unpin_note_from_project", "project_id"),
    ("list_project_deadlines", "project_id"),
    ("get_project_deadline", "deadline_id"),
    ("get_project_deadline", "project_id"),
    ("create_project_deadline", "project_id"),
    ("update_project_deadline", "deadline_id"),
    ("update_project_deadline", "project_id"),
    ("delete_project_deadline", "deadline_id"),
    ("delete_project_deadline", "project_id"),
    ("list_project_emails", "project_id"),
    ("add_email_to_project", "project_id"),
    ("create_invoice", "project_id"),
    ("update_invoice", "invoice_id"),
    ("update_invoice", "project_id"),
    ("delete_invoice", "invoice_id"),
    ("delete_invoice", "project_id"),
    ("finalize_invoice", "invoice_id"),
    ("finalize_invoice", "project_id"),
    ("get_project_invoices", "project_id"),
    ("get_invoice_pdf", "invoice_id"),
    ("approve_invoice", "invoice_id"),
    ("mark_invoice_sent", "invoice_id"),
    ("get_contact", "contact_id"),
    ("update_contact", "contact_id"),
    ("get_contact_addresses", "contact_id"),
    ("get_contact_emails", "contact_id"),
    ("get_contact_phones", "contact_id"),
    ("get_contact_projects", "contact_id"),
    ("remove_tag_from_contacts", "tag_name"),
    ("list_project_tasks", "project_id"),
    ("get_task", "task_id"),
    ("update_task", "task_id"),
    ("delete_task", "task_id"),
    ("complete_task", "task_id"),
    ("incomplete_task", "task_id"),
    ("assign_task", "assignee_id"),
    ("assign_task", "task_id"),
    ("pin_task", "task_id"),
    ("unpin_task", "task_id"),
    ("snooze_task", "task_id"),
    ("get_note", "note_id"),
    ("update_note", "note_id"),
    ("pin_note", "note_id"),
    ("unpin_note", "note_id"),
    ("list_note_comments", "note_id"),
    ("get_note_comment", "comment_id"),
    ("get_note_comment", "note_id"),
    ("create_note_comment", "note_id"),
    ("update_note_comment", "comment_id"),
    ("update_note_comment", "note_id"),
    ("remove_tag_from_notes", "tag_name"),
    ("get_document", "document_id"),
    ("update_document", "document_id"),
    ("delete_document", "document_id"),
    ("get_document_download_locator", "document_id"),
    ("add_document_revision", "document_id"),
    ("lock_document", "document_id"),
    ("unlock_document", "document_id"),
    ("add_document_to_project", "document_id"),
    ("add_document_to_project", "project_id"),
    ("remove_tag_from_documents", "tag_name"),
    ("get_folder", "folder_id"),
    ("update_folder", "folder_id"),
    ("delete_folder", "folder_id"),
    ("get_project_billing_vitals", "project_id"),
    ("get_project_billing_settings", "project_id"),
    ("get_project_billing_codes", "project_id"),
    ("get_project_transactions", "project_id"),
    ("get_project_funds", "project_id"),
    ("get_project_fund_transactions", "project_id"),
    ("create_billing_item", "project_id"),
    ("update_billing_item", "billing_item_id"),
    ("update_billing_item", "project_id"),
    ("delete_billing_item", "billing_item_id"),
    ("get_billing_item", "billing_item_id"),
    ("get_billing_item", "project_id"),
    ("create_payment", "project_id"),
    ("create_payment_and_apply", "project_id"),
    ("get_payment_link", "project_id"),
    ("set_project_rate_schedule", "project_id"),
    ("set_project_rate_schedule", "rate_schedule_id"),
    ("get_webhook_subscription", "subscription_id"),
    ("update_webhook_subscription", "subscription_id"),
    ("delete_webhook_subscription", "subscription_id"),
    ("get_project_type", "project_type_id"),
    ("get_document_series", "series_id"),
    ("get_report", "report_id"),
    ("get_share_link", "link_id"),
    ("delete_share_link", "link_id"),
    ("get_team", "team_id"),
    ("delete_team", "team_id"),
    ("list_project_teams", "project_id"),
    ("create_hashtag", "hashtag"),
]


def client_and_arguments(method):
    client = object.__new__(FileVineClient)
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"id": "normal-id", "success": true}'
    request = Mock(return_value={"id": "normal-id", "success": True})
    send = Mock(return_value=response)
    client._request = request
    client._send = send
    kwargs = {}
    for key, param in inspect.signature(getattr(client, method)).parameters.items():
        if param.default is not inspect.Parameter.empty or param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        annotation = str(param.annotation)
        if "dict" in annotation or key in {"body", "fields", "overlay"}:
            kwargs[key] = {"name": "probe"}
        elif "int" in annotation:
            kwargs[key] = 1
        else:
            kwargs[key] = "normal-id"
    if "resource" in kwargs:
        kwargs["resource"] = "matters"
    if "path" in kwargs:
        kwargs["path"] = "/tasks"
    if method == "tag_call":
        kwargs["tag_ids"] = [1]
    if method == "update_contact" and FileVineClient.__name__ == "CloudTalkClient":
        kwargs["name"] = "probe"
    return client, kwargs, request, send


@pytest.mark.parametrize(("method", "parameter"), CASES)
@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "a/../b", "%2e%2e", "a?b", "a#b", "a\\b", " ", "a\n", None, True],
)
def test_invalid_path_id_never_reaches_transport(method, parameter, value):
    client, kwargs, request, send = client_and_arguments(method)
    kwargs[parameter] = value
    with pytest.raises(Exception) as caught:
        getattr(client, method)(**kwargs)
    error = caught.value
    assert parameter in str(error) or getattr(error, "field", None) == parameter
    assert "identifier" in str(error) or "identifier" in getattr(error, "expected", "")
    request.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize(("method", "parameter"), CASES)
@pytest.mark.parametrize(
    "value", ["normal-id", "550e8400-e29b-41d4-a716-446655440000", "123", 123]
)
def test_normal_path_id_reaches_transport(method, parameter, value):
    client, kwargs, request, send = client_and_arguments(method)
    kwargs[parameter] = value
    getattr(client, method)(**kwargs)
    calls = request.call_args_list + send.call_args_list
    assert calls
    assert any(str(value) in str(call) for call in calls)
