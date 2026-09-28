"""Regression coverage for Filevine list caps, pagination, and ordering."""

from __future__ import annotations

import asyncio

import pytest

from filevine_mcp import server
from filevine_mcp.client import FileVineClient, _cap_collection

PAGINATED_LIST_TOOLS = {
    "list_users",
    "list_projects",
    "list_collection_items",
    "list_project_appointments",
    "list_project_notes",
    "list_project_deadlines",
    "list_project_emails",
    "list_contacts",
    "list_tasks",
    "list_project_tasks",
    "list_notes",
    "list_note_comments",
    "list_documents",
    "list_recently_opened_documents",
    "list_folders",
    "list_project_types",
    "list_document_series",
    "list_reports",
    "list_share_links",
    "list_mailroom",
}
FINITE_LIST_TOOLS = {
    "list_webhook_events",
    "list_webhook_subscriptions",
    "list_teams",
    "list_project_teams",
    "list_classifications",
}
SEMANTIC_COLLECTION_TOOLS = {
    "get_user_tasks",
    "get_user_appointments",
    "get_user_project_access",
    "get_project_contacts",
    "get_project_team",
    "get_project_invoices",
    "get_contact_addresses",
    "get_contact_emails",
    "get_contact_phones",
    "get_contact_projects",
    "get_project_transactions",
    "get_project_fund_transactions",
}


def _tool_schemas() -> dict[str, dict]:
    tools = asyncio.run(server.mcp.list_tools())
    return {tool.name: tool.input_schema for tool in tools}


def test_every_named_list_tool_is_classified_and_paginated_ones_are_bounded() -> None:
    schemas = _tool_schemas()
    discovered = {name for name in schemas if name.startswith("list_")}
    assert discovered == PAGINATED_LIST_TOOLS | FINITE_LIST_TOOLS

    for name in PAGINATED_LIST_TOOLS | SEMANTIC_COLLECTION_TOOLS | {
        "search_documents"
    }:
        limit = schemas[name]["properties"]["limit"]
        assert limit["minimum"] == 1, name
        assert limit["maximum"] == 200, name


class RecordingClient:
    def __init__(self) -> None:
        self.call: tuple[str, dict | None, int | None] | None = None

    def get(self, path, params=None, *, result_limit=None):
        self.call = (path, params, result_limit)
        return {"Items": []}


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "expected_path", "expected_params"),
    [
        ("list_users", (), {}, "Users", {"limit": 7, "offset": 3}),
        (
            "list_projects",
            (),
            {},
            "Projects",
            {"limit": 7, "offset": 3, "sortBy": "projectId", "orderBy": "desc"},
        ),
        (
            "list_collection_items",
            ("project", "selector"),
            {},
            "Projects/project/Collections/selector",
            {"limit": 7, "offset": 3},
        ),
        (
            "list_project_appointments",
            ("project",),
            {},
            "Projects/project/Appointments",
            {"limit": 7, "offset": 3},
        ),
        (
            "list_project_notes",
            ("project",),
            {},
            "Projects/project/Notes",
            {"limit": 7, "offset": 3},
        ),
        (
            "list_project_deadlines",
            ("project",),
            {},
            "projects/project/deadlines",
            {"limit": 7, "offset": 3},
        ),
        (
            "list_project_emails",
            ("project",),
            {},
            "projects/project/emails",
            {"limit": 7, "offset": 3},
        ),
        ("list_contacts", (), {}, "Contacts", {"limit": 7, "offset": 3}),
        ("list_tasks", (), {}, "tasks", {"offset": 3}),
        (
            "list_project_tasks",
            ("project",),
            {},
            "projects/project/tasks",
            {"limit": 7, "offset": 3},
        ),
        ("list_notes", (), {}, "Notes", {"offset": 3}),
        (
            "list_note_comments",
            ("note",),
            {},
            "Notes/note/Comments",
            {"orderByDescending": True, "limit": 7, "offset": 3},
        ),
        ("list_documents", (), {}, "Documents", {"limit": 7, "offset": 3}),
        (
            "list_recently_opened_documents",
            (),
            {},
            "RecentlyOpenedDocuments",
            {"offset": 3},
        ),
        (
            "list_folders",
            (),
            {},
            "Folders",
            {
                "ascendingOrder": False,
                "sortByName": False,
                "limit": 7,
                "offset": 3,
            },
        ),
        ("list_project_types", (), {}, "ProjectTypes", {"limit": 7, "offset": 3}),
        (
            "list_document_series",
            (),
            {"last_id": 3},
            "DocumentSeries",
            {"limit": 7, "lastId": 3},
        ),
        ("list_reports", (), {}, "Reports", {"limit": 7, "offset": 3}),
        (
            "list_share_links",
            (),
            {"last_key": "cursor"},
            "ShareLinks",
            {"limit": 7, "lastKey": "cursor"},
        ),
        ("list_mailroom", (), {}, "Mailroom/Items", {"offset": 3}),
    ],
)
def test_named_list_clients_send_vendor_parameters_and_apply_total_cap(
    method: str,
    args: tuple,
    kwargs: dict,
    expected_path: str,
    expected_params: dict,
) -> None:
    recorder = RecordingClient()
    call_kwargs = {"limit": 7, **kwargs}
    if method not in {"list_document_series", "list_share_links"}:
        call_kwargs["offset"] = 3

    getattr(FileVineClient, method)(recorder, *args, **call_kwargs)

    assert recorder.call == (expected_path, expected_params, 7)
    assert "requestedPage" not in expected_params
    assert "pageSize" not in expected_params


def test_search_documents_uses_required_vendor_names_and_project_scope() -> None:
    recorder = RecordingClient()
    FileVineClient.search_documents(
        recorder,
        query="motion",
        project_id="project",
        limit=7,
        offset=3,
    )
    assert recorder.call == (
        "DocumentSearch",
        {
            "searchTerm": "motion",
            "projectId": "project",
            "limit": 7,
            "offset": 3,
        },
        7,
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (list(range(5)), [0, 1]),
        ({"Items": list(range(5)), "Count": 5}, {"Items": [0, 1], "Count": 5}),
        ({"ShareLinks": list(range(5))}, {"ShareLinks": [0, 1]}),
        ({"data": {"items": list(range(5))}}, {"data": {"items": [0, 1]}}),
    ],
)
def test_collection_envelopes_never_exceed_the_requested_limit(payload, expected) -> None:
    assert _cap_collection(payload, 2) == expected


def test_legacy_page_arguments_translate_to_vendor_offset_without_overfetch() -> None:
    assert server._legacy_pagination(50, 0, page=3, page_size=7) == (7, 14)


def test_ordering_defaults_avoid_oldest_first() -> None:
    recorder = RecordingClient()
    FileVineClient.list_projects(recorder, limit=7, offset=0)
    assert recorder.call is not None
    assert recorder.call[1] == {
        "limit": 7,
        "offset": 0,
        "sortBy": "projectId",
        "orderBy": "desc",
    }

    FileVineClient.list_note_comments(recorder, "note", limit=7, offset=0)
    assert recorder.call is not None
    assert recorder.call[1]["orderByDescending"] is True

    FileVineClient.list_folders(recorder, limit=7, offset=0)
    assert recorder.call is not None
    assert recorder.call[1]["ascendingOrder"] is False
