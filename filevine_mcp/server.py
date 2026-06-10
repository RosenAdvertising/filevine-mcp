#!/usr/bin/env python3
"""Filevine MCP server — FastMCP tools for the Filevine API."""

import json
from functools import wraps
from mcp.server.fastmcp import FastMCP
from filevine_mcp.client import FileVineClient

mcp = FastMCP(
    "filevine",
    instructions=(
        "Filevine legal practice management. "
        "Manage projects (matters), contacts, tasks, notes, documents, billing, and more. "
        "Projects are the core entity — most resources belong to a project."
    ),
)

_raw_tool = mcp.tool


def _safe_tool(*args, **kwargs):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*fn_args, **fn_kwargs):
            try:
                return fn(*fn_args, **fn_kwargs)
            except ValueError as e:
                return json.dumps({"error": str(e)})

        return _raw_tool(*args, **kwargs)(wrapped)

    return decorator


mcp.tool = _safe_tool


def _c():
    return FileVineClient()


def _fields(fields_json: str) -> dict:
    if not fields_json:
        return {}
    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid fields_json: {e}") from e
    if not isinstance(fields, dict):
        raise ValueError("fields_json must be a JSON object")
    return fields


# ── Users ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_current_user() -> str:
    """Get the currently authenticated user (me)."""
    return json.dumps(_c().get_me(), indent=2)


@mcp.tool()
def list_users() -> str:
    """List all users in the organisation."""
    return json.dumps(_c().list_users(), indent=2)


@mcp.tool()
def get_user(user_id: str) -> str:
    """Get a user by ID."""
    return json.dumps(_c().get_user(user_id), indent=2)


@mcp.tool()
def get_user_tasks(user_id: str, page: int = 1, page_size: int = 50) -> str:
    """Get tasks assigned to a user."""
    return json.dumps(_c().get_user_tasks(user_id, page, page_size), indent=2)


@mcp.tool()
def get_user_appointments(user_id: str) -> str:
    """Get appointments for a user."""
    return json.dumps(_c().get_user_appointments(user_id), indent=2)


@mcp.tool()
def get_user_recent_projects(user_id: str) -> str:
    """Get recently accessed projects for a user."""
    return json.dumps(_c().get_user_recent_projects(user_id), indent=2)


@mcp.tool()
def get_user_project_access(user_id: str) -> str:
    """Get the list of projects a user has access to."""
    return json.dumps(_c().get_user_project_access(user_id), indent=2)


# ── Projects (Matters) ─────────────────────────────────────────────────────────


@mcp.tool()
def list_projects(page: int = 1, page_size: int = 50) -> str:
    """List all projects (matters)."""
    return json.dumps(_c().list_projects(page, page_size), indent=2)


@mcp.tool()
def get_project(project_id: str) -> str:
    """Get a project by ID."""
    return json.dumps(_c().get_project(project_id), indent=2)


@mcp.tool()
def create_project(
    project_type_id: str = "",
    name: str = "",
    description: str = "",
    fields_json: str = "",
) -> str:
    """Create a new project. Use fields_json for additional fields as a JSON object."""
    data = _fields(fields_json)
    if project_type_id:
        data["projectTypeId"] = project_type_id
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    return json.dumps(_c().create_project(**data), indent=2)


@mcp.tool()
def update_project(
    project_id: str,
    name: str = "",
    description: str = "",
    status: str = "",
    fields_json: str = "",
) -> str:
    """Update a project. Use fields_json for additional fields as a JSON object."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if status:
        data["status"] = status
    return json.dumps(_c().update_project(project_id, **data), indent=2)


@mcp.tool()
def archive_project(project_id: str, confirm: bool = False) -> str:
    """Archive (soft-delete) a project.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "archive_project requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().archive_project(project_id), indent=2)


@mcp.tool()
def get_project_vitals(project_id: str) -> str:
    """Get the vitals (key fields) for a project."""
    return json.dumps(_c().get_project_vitals(project_id), indent=2)


@mcp.tool()
def get_project_form(project_id: str, selector: str) -> str:
    """Get a custom form section on a project by selector name."""
    return json.dumps(_c().get_project_form(project_id, selector), indent=2)


@mcp.tool()
def update_project_form(project_id: str, selector: str, fields_json: str) -> str:
    """Update a custom form section on a project. fields_json is a JSON object of field values."""
    data = _fields(fields_json)
    return json.dumps(_c().update_project_form(project_id, selector, **data), indent=2)


# ── Project Contacts ───────────────────────────────────────────────────────────


@mcp.tool()
def get_project_contacts(project_id: str) -> str:
    """Get all contacts associated with a project."""
    return json.dumps(_c().get_project_contacts(project_id), indent=2)


@mcp.tool()
def add_contact_to_project(
    project_id: str,
    contact_id: str,
    role: str = "",
    fields_json: str = "",
) -> str:
    """Add a contact to a project with an optional role."""
    data = _fields(fields_json)
    if role:
        data["role"] = role
    return json.dumps(
        _c().add_contact_to_project(project_id, contact_id, **data), indent=2
    )


@mcp.tool()
def update_project_contact(
    project_id: str,
    project_contact_id: str,
    role: str = "",
    fields_json: str = "",
) -> str:
    """Update a contact's role or attributes on a project."""
    data = _fields(fields_json)
    if role:
        data["role"] = role
    return json.dumps(
        _c().update_project_contact(project_id, project_contact_id, **data), indent=2
    )


@mcp.tool()
def remove_contact_from_project(
    project_id: str, project_contact_id: str, confirm: bool = False
) -> str:
    """Remove a contact from a project.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "remove_contact_from_project requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(
        _c().remove_contact_from_project(project_id, project_contact_id), indent=2
    )


# ── Project Collections (Custom Sections) ─────────────────────────────────────


@mcp.tool()
def list_collection_items(
    project_id: str,
    selector: str,
    page: int = 1,
    page_size: int = 50,
) -> str:
    """List items in a custom collection section of a project."""
    return json.dumps(
        _c().list_collection_items(project_id, selector, page, page_size), indent=2
    )


@mcp.tool()
def get_collection_item(project_id: str, selector: str, unique_id: str) -> str:
    """Get a single item from a custom collection section."""
    return json.dumps(
        _c().get_collection_item(project_id, selector, unique_id), indent=2
    )


@mcp.tool()
def create_collection_item(project_id: str, selector: str, fields_json: str) -> str:
    """Create an item in a custom collection section. fields_json is a JSON object."""
    data = _fields(fields_json)
    return json.dumps(
        _c().create_collection_item(project_id, selector, **data), indent=2
    )


@mcp.tool()
def update_collection_item(
    project_id: str,
    selector: str,
    unique_id: str,
    fields_json: str,
) -> str:
    """Update an item in a custom collection section. fields_json is a JSON object."""
    data = _fields(fields_json)
    return json.dumps(
        _c().update_collection_item(project_id, selector, unique_id, **data), indent=2
    )


@mcp.tool()
def delete_collection_item(
    project_id: str, selector: str, unique_id: str, confirm: bool = False
) -> str:
    """Delete an item from a custom collection section.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_collection_item requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(
        _c().delete_collection_item(project_id, selector, unique_id), indent=2
    )


# ── Project Teams ──────────────────────────────────────────────────────────────


@mcp.tool()
def get_project_team(project_id: str) -> str:
    """Get the team members assigned to a project."""
    return json.dumps(_c().get_project_team(project_id), indent=2)


@mcp.tool()
def get_project_team_member(project_id: str, user_id: str) -> str:
    """Get a specific team member on a project."""
    return json.dumps(_c().get_project_team_member(project_id, user_id), indent=2)


@mcp.tool()
def add_team_member_to_project(project_id: str, fields_json: str) -> str:
    """Add a team member to a project. fields_json is a JSON object with userId, role, etc."""
    data = _fields(fields_json)
    return json.dumps(_c().add_team_member(project_id, **data), indent=2)


@mcp.tool()
def update_project_team_member(
    project_id: str,
    user_id: str,
    fields_json: str = "",
) -> str:
    """Update a team member's role on a project."""
    data = _fields(fields_json)
    return json.dumps(
        _c().update_project_team_member(project_id, user_id, **data), indent=2
    )


@mcp.tool()
def remove_project_team_member(
    project_id: str, user_id: str, confirm: bool = False
) -> str:
    """Remove a team member from a project.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "remove_project_team_member requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().remove_project_team_member(project_id, user_id), indent=2)


# ── Project Appointments ───────────────────────────────────────────────────────


@mcp.tool()
def list_project_appointments(project_id: str) -> str:
    """List all appointments for a project."""
    return json.dumps(_c().list_project_appointments(project_id), indent=2)


@mcp.tool()
def create_project_appointment(
    project_id: str,
    title: str = "",
    start_date: str = "",
    end_date: str = "",
    fields_json: str = "",
) -> str:
    """Create an appointment on a project."""
    data = _fields(fields_json)
    if title:
        data["title"] = title
    if start_date:
        data["startDate"] = start_date
    if end_date:
        data["endDate"] = end_date
    return json.dumps(_c().create_project_appointment(project_id, **data), indent=2)


# ── Project Notes ──────────────────────────────────────────────────────────────


@mcp.tool()
def list_project_notes(project_id: str) -> str:
    """List all notes on a project."""
    return json.dumps(_c().list_project_notes(project_id), indent=2)


@mcp.tool()
def pin_note_to_project(project_id: str, note_id: str) -> str:
    """Pin a note to a project."""
    return json.dumps(_c().pin_note_to_project(project_id, note_id), indent=2)


@mcp.tool()
def unpin_note_from_project(project_id: str, note_id: str) -> str:
    """Unpin a note from a project."""
    return json.dumps(_c().unpin_note_from_project(project_id, note_id), indent=2)


# ── Project Deadlines ──────────────────────────────────────────────────────────


@mcp.tool()
def list_project_deadlines(project_id: str) -> str:
    """List all deadlines for a project."""
    return json.dumps(_c().list_project_deadlines(project_id), indent=2)


@mcp.tool()
def get_project_deadline(project_id: str, deadline_id: str) -> str:
    """Get a specific deadline on a project."""
    return json.dumps(_c().get_project_deadline(project_id, deadline_id), indent=2)


@mcp.tool()
def create_project_deadline(
    project_id: str,
    name: str = "",
    due_date: str = "",
    fields_json: str = "",
) -> str:
    """Create a deadline on a project."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    if due_date:
        data["dueDate"] = due_date
    return json.dumps(_c().create_project_deadline(project_id, **data), indent=2)


@mcp.tool()
def update_project_deadline(
    project_id: str,
    deadline_id: str,
    name: str = "",
    due_date: str = "",
    fields_json: str = "",
) -> str:
    """Update a deadline on a project."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    if due_date:
        data["dueDate"] = due_date
    return json.dumps(
        _c().update_project_deadline(project_id, deadline_id, **data), indent=2
    )


@mcp.tool()
def delete_project_deadline(project_id: str, deadline_id: str) -> str:
    """Delete a deadline from a project."""
    return json.dumps(_c().delete_project_deadline(project_id, deadline_id), indent=2)


# ── Project Emails ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_project_emails(project_id: str) -> str:
    """List emails associated with a project."""
    return json.dumps(_c().list_project_emails(project_id), indent=2)


@mcp.tool()
def add_email_to_project(
    project_id: str,
    subject: str = "",
    body: str = "",
    fields_json: str = "",
) -> str:
    """Add an email record to a project."""
    data = _fields(fields_json)
    if subject:
        data["subject"] = subject
    if body:
        data["body"] = body
    return json.dumps(_c().add_email_to_project(project_id, **data), indent=2)


# ── Project Invoices ───────────────────────────────────────────────────────────


@mcp.tool()
def get_project_invoices(project_id: str) -> str:
    """Get all invoices for a project."""
    return json.dumps(_c().get_project_invoices(project_id), indent=2)


@mcp.tool()
def create_invoice(project_id: str, fields_json: str = "") -> str:
    """Create an invoice for a project. fields_json is a JSON object."""
    data = _fields(fields_json)
    return json.dumps(_c().create_invoice(project_id, **data), indent=2)


@mcp.tool()
def update_invoice(project_id: str, invoice_id: str, fields_json: str = "") -> str:
    """Update an invoice on a project."""
    data = _fields(fields_json)
    return json.dumps(_c().update_invoice(project_id, invoice_id, **data), indent=2)


@mcp.tool()
def delete_invoice(project_id: str, invoice_id: str, confirm: bool = False) -> str:
    """Delete an invoice from a project.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_invoice requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_invoice(project_id, invoice_id), indent=2)


@mcp.tool()
def finalize_invoice(project_id: str, invoice_id: str, confirm: bool = False) -> str:
    """Finalize an invoice on a project.

    FINANCIAL WRITE. Finalizing an invoice is not easily reversible. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "finalize_invoice requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().finalize_invoice(project_id, invoice_id), indent=2)


@mcp.tool()
def get_invoice_pdf(invoice_id: str) -> str:
    """Get the PDF download URL for an invoice."""
    return json.dumps(_c().get_invoice_pdf(invoice_id), indent=2)


@mcp.tool()
def approve_invoice(invoice_id: str, confirm: bool = False) -> str:
    """Approve an invoice.

    FINANCIAL WRITE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "approve_invoice requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().approve_invoice(invoice_id), indent=2)


@mcp.tool()
def mark_invoice_sent(invoice_id: str) -> str:
    """Mark an invoice as sent."""
    return json.dumps(_c().mark_invoice_sent(invoice_id), indent=2)


# ── Contacts ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_contacts(page: int = 1, page_size: int = 50) -> str:
    """List all contacts."""
    return json.dumps(_c().list_contacts(page, page_size), indent=2)


@mcp.tool()
def get_contact(contact_id: str) -> str:
    """Get a contact by ID."""
    return json.dumps(_c().get_contact(contact_id), indent=2)


@mcp.tool()
def create_contact(
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    company: str = "",
    fields_json: str = "",
) -> str:
    """Create a new contact."""
    data = _fields(fields_json)
    if first_name:
        data["firstName"] = first_name
    if last_name:
        data["lastName"] = last_name
    if email:
        data["email"] = email
    if phone:
        data["phone"] = phone
    if company:
        data["company"] = company
    return json.dumps(_c().create_contact(**data), indent=2)


@mcp.tool()
def update_contact(
    contact_id: str,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    company: str = "",
    fields_json: str = "",
) -> str:
    """Update a contact."""
    data = _fields(fields_json)
    if first_name:
        data["firstName"] = first_name
    if last_name:
        data["lastName"] = last_name
    if email:
        data["email"] = email
    if phone:
        data["phone"] = phone
    if company:
        data["company"] = company
    return json.dumps(_c().update_contact(contact_id, **data), indent=2)


@mcp.tool()
def get_contact_addresses(contact_id: str) -> str:
    """Get all addresses for a contact."""
    return json.dumps(_c().get_contact_addresses(contact_id), indent=2)


@mcp.tool()
def get_contact_emails(contact_id: str) -> str:
    """Get all email addresses for a contact."""
    return json.dumps(_c().get_contact_emails(contact_id), indent=2)


@mcp.tool()
def get_contact_phones(contact_id: str) -> str:
    """Get all phone numbers for a contact."""
    return json.dumps(_c().get_contact_phones(contact_id), indent=2)


@mcp.tool()
def get_contact_projects(contact_id: str) -> str:
    """Get all projects associated with a contact."""
    return json.dumps(_c().get_contact_projects(contact_id), indent=2)


@mcp.tool()
def get_countries() -> str:
    """Get the list of available countries for contact addresses."""
    return json.dumps(_c().get_countries(), indent=2)


@mcp.tool()
def remove_tag_from_contacts(tag_name: str, confirm: bool = False) -> str:
    """Remove a tag from all contacts that have it.

    DESTRUCTIVE — removes the tag from every contact in the org that has it. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "remove_tag_from_contacts requires confirm=True. This removes the tag from ALL matching contacts. Confirm with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().remove_tag_from_contacts(tag_name), indent=2)


# ── Tasks ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_tasks(page: int = 1, page_size: int = 50) -> str:
    """List all tasks across all projects."""
    return json.dumps(_c().list_tasks(page, page_size), indent=2)


@mcp.tool()
def list_project_tasks(project_id: str) -> str:
    """List all tasks on a specific project."""
    return json.dumps(_c().list_project_tasks(project_id), indent=2)


@mcp.tool()
def get_task(task_id: str) -> str:
    """Get a task by ID."""
    return json.dumps(_c().get_task(task_id), indent=2)


@mcp.tool()
def create_task(
    body: str = "",
    due_date: str = "",
    project_id: str = "",
    assignee_id: str = "",
    fields_json: str = "",
) -> str:
    """Create a new task."""
    data = _fields(fields_json)
    if body:
        data["body"] = body
    if due_date:
        data["dueDate"] = due_date
    if project_id:
        data["projectId"] = project_id
    if assignee_id:
        data["assigneeId"] = assignee_id
    return json.dumps(_c().create_task(**data), indent=2)


@mcp.tool()
def update_task(
    task_id: str,
    body: str = "",
    due_date: str = "",
    fields_json: str = "",
) -> str:
    """Update a task."""
    data = _fields(fields_json)
    if body:
        data["body"] = body
    if due_date:
        data["dueDate"] = due_date
    return json.dumps(_c().update_task(task_id, **data), indent=2)


@mcp.tool()
def delete_task(task_id: str, confirm: bool = False) -> str:
    """Delete a task.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_task requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_task(task_id), indent=2)


@mcp.tool()
def complete_task(task_id: str) -> str:
    """Mark a task as complete."""
    return json.dumps(_c().complete_task(task_id), indent=2)


@mcp.tool()
def incomplete_task(task_id: str) -> str:
    """Mark a completed task as incomplete."""
    return json.dumps(_c().incomplete_task(task_id), indent=2)


@mcp.tool()
def assign_task(task_id: str, assignee_id: str) -> str:
    """Assign a task to a user."""
    return json.dumps(_c().assign_task(task_id, assignee_id), indent=2)


@mcp.tool()
def pin_task(task_id: str) -> str:
    """Pin a task."""
    return json.dumps(_c().pin_task(task_id), indent=2)


@mcp.tool()
def unpin_task(task_id: str) -> str:
    """Unpin a task."""
    return json.dumps(_c().unpin_task(task_id), indent=2)


@mcp.tool()
def snooze_task(task_id: str, due_date: str) -> str:
    """Snooze a task until a future date (ISO 8601 format)."""
    return json.dumps(_c().snooze_task(task_id, due_date), indent=2)


# ── Notes ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_notes(page: int = 1, page_size: int = 50) -> str:
    """List all notes across all projects."""
    return json.dumps(_c().list_notes(page, page_size), indent=2)


@mcp.tool()
def get_note(note_id: str) -> str:
    """Get a note by ID."""
    return json.dumps(_c().get_note(note_id), indent=2)


@mcp.tool()
def create_note(
    body: str = "",
    project_id: str = "",
    fields_json: str = "",
) -> str:
    """Create a new note."""
    data = _fields(fields_json)
    if body:
        data["body"] = body
    if project_id:
        data["projectId"] = project_id
    return json.dumps(_c().create_note(**data), indent=2)


@mcp.tool()
def update_note(note_id: str, body: str = "", fields_json: str = "") -> str:
    """Update a note."""
    data = _fields(fields_json)
    if body:
        data["body"] = body
    return json.dumps(_c().update_note(note_id, **data), indent=2)


@mcp.tool()
def pin_note(note_id: str) -> str:
    """Pin a note."""
    return json.dumps(_c().pin_note(note_id), indent=2)


@mcp.tool()
def unpin_note(note_id: str) -> str:
    """Unpin a note."""
    return json.dumps(_c().unpin_note(note_id), indent=2)


@mcp.tool()
def list_note_comments(note_id: str) -> str:
    """List all comments on a note."""
    return json.dumps(_c().list_note_comments(note_id), indent=2)


@mcp.tool()
def get_note_comment(note_id: str, comment_id: str) -> str:
    """Get a specific comment on a note."""
    return json.dumps(_c().get_note_comment(note_id, comment_id), indent=2)


@mcp.tool()
def create_note_comment(note_id: str, body: str = "", fields_json: str = "") -> str:
    """Add a comment to a note."""
    data = _fields(fields_json)
    if body:
        data["body"] = body
    return json.dumps(_c().create_note_comment(note_id, **data), indent=2)


@mcp.tool()
def update_note_comment(
    note_id: str,
    comment_id: str,
    body: str = "",
    fields_json: str = "",
) -> str:
    """Update a comment on a note."""
    data = _fields(fields_json)
    if body:
        data["body"] = body
    return json.dumps(_c().update_note_comment(note_id, comment_id, **data), indent=2)


@mcp.tool()
def remove_tag_from_notes(tag_name: str, confirm: bool = False) -> str:
    """Remove a tag from all notes that have it.

    DESTRUCTIVE — removes the tag from every note in the org that has it. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "remove_tag_from_notes requires confirm=True. This removes the tag from ALL matching notes. Confirm with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().remove_tag_from_notes(tag_name), indent=2)


# ── Documents ──────────────────────────────────────────────────────────────────


@mcp.tool()
def list_documents(page: int = 1, page_size: int = 50) -> str:
    """List all documents."""
    return json.dumps(_c().list_documents(page, page_size), indent=2)


@mcp.tool()
def get_document(document_id: str) -> str:
    """Get a document by ID."""
    return json.dumps(_c().get_document(document_id), indent=2)


@mcp.tool()
def create_document(
    name: str = "",
    folder_id: str = "",
    fields_json: str = "",
) -> str:
    """Create a new document record."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    if folder_id:
        data["folderId"] = folder_id
    return json.dumps(_c().create_document(**data), indent=2)


@mcp.tool()
def update_document(
    document_id: str,
    name: str = "",
    folder_id: str = "",
    fields_json: str = "",
) -> str:
    """Update a document's metadata."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    if folder_id:
        data["folderId"] = folder_id
    return json.dumps(_c().update_document(document_id, **data), indent=2)


@mcp.tool()
def delete_document(document_id: str, confirm: bool = False) -> str:
    """Delete a document.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_document requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_document(document_id), indent=2)


@mcp.tool()
def get_document_download_locator(document_id: str) -> str:
    """Get the download URL/locator for a document."""
    return json.dumps(_c().get_document_download_locator(document_id), indent=2)


@mcp.tool()
def add_document_revision(document_id: str, fields_json: str = "") -> str:
    """Add a new revision to a document."""
    data = _fields(fields_json)
    return json.dumps(_c().add_document_revision(document_id, **data), indent=2)


@mcp.tool()
def lock_document(document_id: str) -> str:
    """Lock a document to prevent editing."""
    return json.dumps(_c().lock_document(document_id), indent=2)


@mcp.tool()
def unlock_document(document_id: str) -> str:
    """Unlock a document to allow editing."""
    return json.dumps(_c().unlock_document(document_id), indent=2)


@mcp.tool()
def move_documents(document_ids_csv: str, folder_id: str) -> str:
    """Move documents to a folder. document_ids_csv is a comma-separated list of document IDs."""
    doc_ids = [d.strip() for d in document_ids_csv.split(",") if d.strip()]
    return json.dumps(_c().move_documents(doc_ids, folder_id), indent=2)


@mcp.tool()
def copy_documents(document_ids_csv: str, folder_id: str) -> str:
    """Copy documents to a folder. document_ids_csv is a comma-separated list of document IDs."""
    doc_ids = [d.strip() for d in document_ids_csv.split(",") if d.strip()]
    return json.dumps(_c().copy_documents(doc_ids, folder_id), indent=2)


@mcp.tool()
def batch_upload_documents(fields_json: str) -> str:
    """Initiate a batch document upload. fields_json is a JSON object with upload details."""
    data = _fields(fields_json)
    return json.dumps(_c().batch_upload_documents(**data), indent=2)


@mcp.tool()
def confirm_batch_upload(fields_json: str) -> str:
    """Confirm a batch document upload. fields_json is a JSON object."""
    data = _fields(fields_json)
    return json.dumps(_c().confirm_batch_upload(**data), indent=2)


@mcp.tool()
def batch_download_documents(document_ids_csv: str) -> str:
    """Request a batch download of documents. document_ids_csv is comma-separated document IDs."""
    doc_ids = [d.strip() for d in document_ids_csv.split(",") if d.strip()]
    return json.dumps(_c().batch_download_documents(doc_ids), indent=2)


@mcp.tool()
def search_documents(query: str, page: int = 1, page_size: int = 50) -> str:
    """Search documents by query string."""
    return json.dumps(_c().search_documents(query, page, page_size), indent=2)


@mcp.tool()
def add_document_to_project(project_id: str, document_id: str) -> str:
    """Associate a document with a project."""
    return json.dumps(_c().add_document_to_project(project_id, document_id), indent=2)


@mcp.tool()
def remove_tag_from_documents(tag_name: str, confirm: bool = False) -> str:
    """Remove a tag from all documents that have it.

    DESTRUCTIVE — removes the tag from every document in the org that has it. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "remove_tag_from_documents requires confirm=True. This removes the tag from ALL matching documents. Confirm with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().remove_tag_from_documents(tag_name), indent=2)


@mcp.tool()
def list_recently_opened_documents() -> str:
    """List recently opened documents for the current user."""
    return json.dumps(_c().list_recently_opened_documents(), indent=2)


# ── Folders ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_folders(page: int = 1, page_size: int = 50) -> str:
    """List all document folders."""
    return json.dumps(_c().list_folders(page, page_size), indent=2)


@mcp.tool()
def get_folder(folder_id: str) -> str:
    """Get a folder by ID."""
    return json.dumps(_c().get_folder(folder_id), indent=2)


@mcp.tool()
def create_folder(
    name: str = "",
    parent_folder_id: str = "",
    fields_json: str = "",
) -> str:
    """Create a new document folder."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    if parent_folder_id:
        data["parentFolderId"] = parent_folder_id
    return json.dumps(_c().create_folder(**data), indent=2)


@mcp.tool()
def update_folder(folder_id: str, name: str = "", fields_json: str = "") -> str:
    """Update a document folder."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    return json.dumps(_c().update_folder(folder_id, **data), indent=2)


@mcp.tool()
def delete_folder(folder_id: str, confirm: bool = False) -> str:
    """Delete a document folder.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_folder requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_folder(folder_id), indent=2)


# ── Billing ────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_org_billing_codes() -> str:
    """Get all available billing codes for the organisation."""
    return json.dumps(_c().get_org_billing_codes(), indent=2)


@mcp.tool()
def get_org_billing_settings() -> str:
    """Get the organisation's billing settings."""
    return json.dumps(_c().get_org_billing_settings(), indent=2)


@mcp.tool()
def get_project_billing_vitals(project_id: str) -> str:
    """Get billing vitals (summary) for a project."""
    return json.dumps(_c().get_project_billing_vitals(project_id), indent=2)


@mcp.tool()
def get_project_billing_settings(project_id: str) -> str:
    """Get billing settings for a project."""
    return json.dumps(_c().get_project_billing_settings(project_id), indent=2)


@mcp.tool()
def get_project_billing_codes(project_id: str) -> str:
    """Get available billing codes for a project."""
    return json.dumps(_c().get_project_billing_codes(project_id), indent=2)


@mcp.tool()
def get_project_transactions(project_id: str) -> str:
    """Get all billing transactions for a project."""
    return json.dumps(_c().get_project_transactions(project_id), indent=2)


@mcp.tool()
def get_project_funds(project_id: str) -> str:
    """Get trust/retainer fund balances for a project."""
    return json.dumps(_c().get_project_funds(project_id), indent=2)


@mcp.tool()
def get_project_fund_transactions(project_id: str) -> str:
    """Get trust/retainer fund transaction history for a project."""
    return json.dumps(_c().get_project_fund_transactions(project_id), indent=2)


@mcp.tool()
def get_billing_item(project_id: str, billing_item_id: str) -> str:
    """Get a specific billing item on a project."""
    return json.dumps(_c().get_billing_item(project_id, billing_item_id), indent=2)


@mcp.tool()
def create_billing_item(
    project_id: str,
    description: str = "",
    amount: str = "",
    rate: str = "",
    hours: str = "",
    fields_json: str = "",
    confirm: bool = False,
) -> str:
    """Create a billing item (time entry or expense) on a project.

    FINANCIAL WRITE. You MUST set confirm=True to proceed.
    Confirm billing details with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "create_billing_item requires confirm=True. Confirm billing details with the user before proceeding."
            },
            indent=2,
        )
    data = _fields(fields_json)
    if description:
        data["description"] = description
    if amount:
        data["amount"] = float(amount)
    if rate:
        data["rate"] = float(rate)
    if hours:
        data["hours"] = float(hours)
    return json.dumps(_c().create_billing_item(project_id, **data), indent=2)


@mcp.tool()
def update_billing_item(
    project_id: str,
    billing_item_id: str,
    description: str = "",
    amount: str = "",
    fields_json: str = "",
    confirm: bool = False,
) -> str:
    """Update a billing item on a project.

    FINANCIAL WRITE. You MUST set confirm=True to proceed.
    Confirm billing details with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "update_billing_item requires confirm=True. Confirm billing details with the user before proceeding."
            },
            indent=2,
        )
    data = _fields(fields_json)
    if description:
        data["description"] = description
    if amount:
        data["amount"] = float(amount)
    return json.dumps(
        _c().update_billing_item(project_id, billing_item_id, **data), indent=2
    )


@mcp.tool()
def delete_billing_item(billing_item_id: str, confirm: bool = False) -> str:
    """Delete a billing item.

    FINANCIAL WRITE / DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_billing_item requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_billing_item(billing_item_id), indent=2)


@mcp.tool()
def create_payment(
    project_id: str,
    amount: str = "",
    date: str = "",
    description: str = "",
    fields_json: str = "",
    confirm: bool = False,
) -> str:
    """Record a payment on a project.

    FINANCIAL WRITE. You MUST set confirm=True to proceed.
    Confirm the payment amount and project with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "create_payment requires confirm=True. Confirm payment details with the user before proceeding."
            },
            indent=2,
        )
    data = _fields(fields_json)
    if amount:
        data["amount"] = float(amount)
    if date:
        data["date"] = date
    if description:
        data["description"] = description
    return json.dumps(_c().create_payment(project_id, **data), indent=2)


@mcp.tool()
def create_payment_and_apply(
    project_id: str,
    amount: str = "",
    invoice_id: str = "",
    fields_json: str = "",
    confirm: bool = False,
) -> str:
    """Record a payment and apply it to an invoice.

    FINANCIAL WRITE. You MUST set confirm=True to proceed.
    Confirm the payment amount, project, and invoice with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "create_payment_and_apply requires confirm=True. Confirm payment details with the user before proceeding."
            },
            indent=2,
        )
    data = _fields(fields_json)
    if amount:
        data["amount"] = float(amount)
    if invoice_id:
        data["invoiceId"] = invoice_id
    return json.dumps(_c().create_payment_and_apply(project_id, **data), indent=2)


@mcp.tool()
def get_payment_link(project_id: str) -> str:
    """Get the online payment link for a project."""
    return json.dumps(_c().get_payment_link(project_id), indent=2)


@mcp.tool()
def get_org_rate_schedules() -> str:
    """Get all rate schedules for the organisation."""
    return json.dumps(_c().get_org_rate_schedules(), indent=2)


@mcp.tool()
def set_project_rate_schedule(project_id: str, rate_schedule_id: str) -> str:
    """Set the rate schedule for a project."""
    return json.dumps(
        _c().set_project_rate_schedule(project_id, rate_schedule_id), indent=2
    )


# ── Webhooks ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_webhook_events() -> str:
    """List all available webhook event types."""
    return json.dumps(_c().list_webhook_events(), indent=2)


@mcp.tool()
def list_webhook_subscriptions() -> str:
    """List all active webhook subscriptions."""
    return json.dumps(_c().list_webhook_subscriptions(), indent=2)


@mcp.tool()
def get_webhook_subscription(subscription_id: str) -> str:
    """Get a specific webhook subscription."""
    return json.dumps(_c().get_webhook_subscription(subscription_id), indent=2)


@mcp.tool()
def create_webhook_subscription(
    event_name: str,
    target_url: str,
    fields_json: str = "",
) -> str:
    """Create a webhook subscription for a Filevine event."""
    data = _fields(fields_json)
    return json.dumps(
        _c().create_webhook_subscription(event_name, target_url, **data), indent=2
    )


@mcp.tool()
def update_webhook_subscription(
    subscription_id: str,
    target_url: str = "",
    fields_json: str = "",
) -> str:
    """Update a webhook subscription."""
    data = _fields(fields_json)
    if target_url:
        data["targetUrl"] = target_url
    return json.dumps(
        _c().update_webhook_subscription(subscription_id, **data), indent=2
    )


@mcp.tool()
def delete_webhook_subscription(subscription_id: str, confirm: bool = False) -> str:
    """Delete a webhook subscription.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_webhook_subscription requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_webhook_subscription(subscription_id), indent=2)


# ── Project Types ──────────────────────────────────────────────────────────────


@mcp.tool()
def list_project_types() -> str:
    """List all project (matter) types configured in the organisation."""
    return json.dumps(_c().list_project_types(), indent=2)


@mcp.tool()
def get_project_type(project_type_id: str) -> str:
    """Get a specific project type by ID."""
    return json.dumps(_c().get_project_type(project_type_id), indent=2)


# ── Document Series ────────────────────────────────────────────────────────────


@mcp.tool()
def list_document_series() -> str:
    """List all document series templates."""
    return json.dumps(_c().list_document_series(), indent=2)


@mcp.tool()
def get_document_series(series_id: str) -> str:
    """Get a document series template by ID."""
    return json.dumps(_c().get_document_series(series_id), indent=2)


# ── Reports ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_reports() -> str:
    """List all available reports."""
    return json.dumps(_c().list_reports(), indent=2)


@mcp.tool()
def get_report(report_id: str) -> str:
    """Get a specific report by ID."""
    return json.dumps(_c().get_report(report_id), indent=2)


# ── Share Links ────────────────────────────────────────────────────────────────


@mcp.tool()
def list_share_links() -> str:
    """List all document share links."""
    return json.dumps(_c().list_share_links(), indent=2)


@mcp.tool()
def get_share_link(link_id: str) -> str:
    """Get a specific share link."""
    return json.dumps(_c().get_share_link(link_id), indent=2)


@mcp.tool()
def create_share_link(fields_json: str) -> str:
    """Create a document share link. fields_json is a JSON object."""
    data = _fields(fields_json)
    return json.dumps(_c().create_share_link(**data), indent=2)


@mcp.tool()
def delete_share_link(link_id: str, confirm: bool = False) -> str:
    """Delete a share link.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_share_link requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_share_link(link_id), indent=2)


# ── Mailroom ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_mailroom() -> str:
    """List all items in the mailroom."""
    return json.dumps(_c().list_mailroom(), indent=2)


@mcp.tool()
def create_mailroom_item(fields_json: str) -> str:
    """Add an item to the mailroom. fields_json is a JSON object."""
    data = _fields(fields_json)
    return json.dumps(_c().create_mailroom_item(**data), indent=2)


# ── Teams ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_teams() -> str:
    """List all teams in the organisation."""
    return json.dumps(_c().list_teams(), indent=2)


@mcp.tool()
def get_team(team_id: str) -> str:
    """Get a team by ID."""
    return json.dumps(_c().get_team(team_id), indent=2)


@mcp.tool()
def create_team(name: str = "", fields_json: str = "") -> str:
    """Create a new team."""
    data = _fields(fields_json)
    if name:
        data["name"] = name
    return json.dumps(_c().create_team(**data), indent=2)


@mcp.tool()
def delete_team(team_id: str, confirm: bool = False) -> str:
    """Delete a team.

    DESTRUCTIVE. You MUST set confirm=True to proceed.
    Confirm with the user before calling this tool with confirm=True.
    """
    if not confirm:
        return json.dumps(
            {
                "error": "delete_team requires confirm=True. Confirm this action with the user before proceeding."
            },
            indent=2,
        )
    return json.dumps(_c().delete_team(team_id), indent=2)


@mcp.tool()
def list_project_teams(project_id: str) -> str:
    """List all teams assigned to a project."""
    return json.dumps(_c().list_project_teams(project_id), indent=2)


# ── Reference Data ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_classifications() -> str:
    """List all document classification categories."""
    return json.dumps(_c().list_classifications(), indent=2)


@mcp.tool()
def create_hashtag(hashtag: str, fields_json: str = "") -> str:
    """Create a hashtag for use in notes and tasks. hashtag is the tag name (without #)."""
    data = _fields(fields_json)
    return json.dumps(_c().create_hashtag(hashtag, **data), indent=2)


# ── Resources ─────────────────────────────────────────────────────────────────


@mcp.resource("filevine://project_types", mime_type="application/json")
def project_types_resource() -> str:
    """All project (matter) types configured in this Filevine organisation — read-only reference data."""
    return json.dumps(_c().list_project_types(), indent=2)


@mcp.resource("filevine://classifications", mime_type="application/json")
def classifications_resource() -> str:
    """All document classification categories configured in this Filevine organisation — read-only reference data."""
    return json.dumps(_c().list_classifications(), indent=2)


@mcp.resource("filevine://security-notes", mime_type="text/markdown")
def security_notes_resource() -> str:
    """Security posture documentation for this Filevine MCP server."""
    return """\
# Filevine MCP — Security Notes

## Confirmation-Gated Operations (SEC-E)

The following tools require `confirm=True` to execute. **Never pass confirm=True
without first obtaining explicit user confirmation.** Return the tool's error
response to the user and ask for confirmation before re-calling with confirm=True.

### Destructive Operations (14 tools)
These permanently delete or remove data:

- `archive_project` — archive a project (matter)
- `remove_contact_from_project` — remove a contact from a project
- `delete_collection_item` — delete a collection section item
- `remove_project_team_member` — remove a team member from a project
- `delete_invoice` — permanently delete an invoice
- `remove_tag_from_contacts` — bulk-remove a tag from contacts
- `delete_task` — delete a task
- `remove_tag_from_notes` — bulk-remove a tag from notes
- `delete_document` — delete a document
- `remove_tag_from_documents` — bulk-remove a tag from documents
- `delete_folder` — delete a folder
- `delete_billing_item` — delete a billing line item
- `delete_webhook_subscription` — delete a webhook subscription
- `delete_share_link` — delete a share link
- `delete_team` — delete a team

### Financial Operations (6 tools)
These create or modify financial records:

- `finalize_invoice` — finalize (lock) an invoice
- `approve_invoice` — approve an invoice for payment
- `create_billing_item` — create a billing line item
- `update_billing_item` — update a billing line item
- `create_payment` — record a payment
- `create_payment_and_apply` — record and apply a payment to an invoice

**Agent guidance**: always present the operation details to the user and wait for
explicit confirmation before calling any of the above tools with confirm=True.
Auto-confirming is not permitted.
"""


# ── Prompts ───────────────────────────────────────────────────────────────────


@mcp.prompt()
def daily_briefing() -> str:
    """Morning briefing: open projects needing attention, overdue tasks, and pending billing."""
    return """You are a legal assistant. Run a morning briefing using the Filevine tools:

1. List all active projects (list_projects) — note any recently opened or updated
2. List all open tasks (list_tasks) — flag any overdue (due before today) with ⚠️
3. List project deadlines across active matters (list_project_deadlines) — highlight upcoming 7-day deadlines
4. List billing items needing attention (list_billing_items or get_org_billing_settings) — identify unbilled work
5. Summarize: what needs attention today, ranked by urgency

Be specific — include project names, task names, due dates, and amounts. Keep it concise."""


@mcp.prompt()
def intake_triage(project_id: str) -> str:
    """Triage a new or recently opened project: review contacts, tasks, documents, and billing setup."""
    return f"""Triage project {project_id} to ensure it is properly set up:

1. Get the project detail — confirm project type, status, and assigned team members
2. List contacts on the project (list_contacts with project_id={project_id}) — check a client contact is linked
3. List tasks on the project (list_project_tasks with project_id={project_id}) — note any missing intake tasks
4. List documents on the project (list_documents with project_id={project_id}) — check for required intake docs
5. List notes on the project (list_project_notes with project_id={project_id}) — surface any intake flags

Output a checklist: ✅ complete, ⚠️ needs attention, ❌ missing. One line per item.

IMPORTANT: if any remediation requires destructive or financial operations (see filevine://security-notes),
present the specific action and details to the user and obtain explicit confirmation before proceeding.
Do NOT auto-confirm any operation requiring confirm=True."""


@mcp.prompt()
def billing_workflow(project_id: str) -> str:
    """Guided billing workflow for a project: review items, finalize invoice, record payment.

    All financial write operations in this server require explicit user confirmation
    before calling with confirm=True — never auto-confirm.
    """
    return f"""Run the billing workflow for project {project_id}. Follow this sequence:

1. List billing items (list_billing_items with project_id={project_id}) — review all unbilled line items
2. Check billing settings (get_org_billing_settings) — confirm rate schedules and billing codes
3. List existing invoices (list_invoices with project_id={project_id}) — check for any draft invoices

For each write step below, you MUST:
  a. Present the full details of the operation to the user
  b. Wait for explicit user confirmation (yes/no)
  c. Only then call the tool with confirm=True

Write steps (confirmation required each time):
- `create_billing_item` — add a new line item (confirm=True required)
- `finalize_invoice` — lock the invoice for sending (confirm=True required)
- `approve_invoice` — approve for payment processing (confirm=True required)
- `create_payment` or `create_payment_and_apply` — record payment receipt (confirm=True required)

Never pass confirm=True without receiving explicit user confirmation for that specific step.
After each confirmed write, report what was done before proceeding to the next step."""


def main():
    mcp.run()


if __name__ == "__main__":
    main()
