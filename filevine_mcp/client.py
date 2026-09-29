#!/usr/bin/env python3
"""Filevine API client. OAuth 2.0 client credentials, region-specific host, Bearer auth."""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from mcp.server.mcpserver.exceptions import ToolError

from filevine_mcp import credentials

logger = logging.getLogger(__name__)

REGIONS = {
    "us": {
        "api": "https://api.filevineapp.com",
        "identity": "https://identity.filevine.com",
    },
    "ca": {
        "api": "https://api.filevineapp.ca",
        "identity": "https://identity.filevine.ca",
    },
    "cjis": {
        "api": "https://api.filevinegov.com",
        "identity": "https://identity.filevinegov.com",
    },
}

CONFIG_DIR = Path.home() / ".filevine-mcp"
API_PREFIX = "/fv-app/v2"

# Resolve credentials through the pluggable store (OS keyring -> .env file).
credentials.load_into_environ(
    [
        "FILEVINE_CLIENT_ID",
        "FILEVINE_CLIENT_SECRET",
        "FILEVINE_ORG_ID",
        "FILEVINE_REGION",
        "FILEVINE_PAT",
    ]
)

CLIENT_ID = os.environ.get("FILEVINE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("FILEVINE_CLIENT_SECRET", "")
ORG_ID = os.environ.get("FILEVINE_ORG_ID", "")
REGION = os.environ.get("FILEVINE_REGION", "us").lower()
FILEVINE_PAT = os.environ.get("FILEVINE_PAT", "")

_region_cfg = REGIONS.get(REGION, REGIONS["us"])
BASE_URL = _region_cfg["api"]
IDENTITY_URL = _region_cfg["identity"]
TOKEN_URL = f"{IDENTITY_URL}/connect/token"
REQUEST_TIMEOUT = 30
MAX_RETRY_SLEEP = 60


class FilevineClientError(ToolError, RuntimeError):
    """A safe, actionable failure suitable for returning to an MCP client."""


def _retry_after_seconds(resp, default=10):
    try:
        return int(resp.headers.get("Retry-After", default))
    except (TypeError, ValueError):
        return default


def _json_response(resp):
    try:
        return resp.json()
    except ValueError:
        raise FilevineClientError("Filevine returned an unreadable response.") from None


def _cap_collection(payload, limit):
    """Cap known Filevine list envelopes without mutating the caller's object."""
    if isinstance(payload, list):
        return payload[:limit]
    if not isinstance(payload, dict):
        return payload

    for key in ("Items", "items", "ShareLinks", "shareLinks", "data", "Data"):
        value = payload.get(key)
        if isinstance(value, list):
            capped = dict(payload)
            capped[key] = value[:limit]
            return capped
        if isinstance(value, dict):
            nested = _cap_collection(value, limit)
            if nested is not value:
                capped = dict(payload)
                capped[key] = nested
                return capped
    return payload


class TokenManager:
    def __init__(self):
        self.token_file = CONFIG_DIR / "tokens.json"
        self.tokens = self._load()

    def _load(self):
        if self.token_file.exists():
            try:
                with open(self.token_file) as f:
                    tokens = json.load(f)
                if not isinstance(tokens, dict):
                    raise ValueError
                return tokens
            except (OSError, ValueError):
                raise FilevineClientError(
                    "Filevine stored tokens could not be read. Re-run filevine-mcp-setup."
                ) from None
        return {}

    def save(self, tokens):
        self.tokens = tokens
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        def secure_open(path, flags):
            fd = os.open(path, flags, 0o600)
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            return fd

        with open(self.token_file, "w", opener=secure_open) as f:
            json.dump(tokens, f, indent=2)
        os.chmod(self.token_file, 0o600)

    @property
    def access_token(self):
        return self.tokens.get("access_token", "")

    def is_expired(self):
        expires_at = self.tokens.get("expires_at", 0)
        return time.time() >= expires_at - 60

    def fetch(self):
        if not CLIENT_ID or not CLIENT_SECRET:
            logger.warning(
                "Filevine request rejected",
                extra={
                    "event": "request_rejected",
                    "reason": "missing_client_credentials",
                },
            )
            raise FilevineClientError(
                "FILEVINE_CLIENT_ID and FILEVINE_CLIENT_SECRET are required. Run: filevine-mcp-setup"
            )
        if not FILEVINE_PAT:
            logger.warning(
                "Filevine request rejected",
                extra={"event": "request_rejected", "reason": "missing_pat"},
            )
            raise FilevineClientError(
                "FILEVINE_PAT is required. Run: filevine-mcp-setup"
            )
        try:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "personal_access_token",
                    "token": FILEVINE_PAT,
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "scope": (
                        "fv.api.gateway.access tenant filevine.v2.api.* "
                        "openid email fv.auth.tenant.read filevine.v2.webhooks"
                    ),
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            raise FilevineClientError(
                "Filevine authorization request lost its connection; the outcome is unknown. Check whether authorization completed before retrying setup."
            ) from None
        if resp.status_code == 200:
            tokens = _json_response(resp)
            expires_in = tokens.get("expires_in", 3600)
            tokens["expires_at"] = time.time() + expires_in
            tokens["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self.save(tokens)
            return tokens
        if resp.status_code == 401:
            raise FilevineClientError(
                "Filevine authorization failed (401). Re-run filevine-mcp-setup to reauthorize."
            )
        if resp.status_code == 403:
            raise FilevineClientError(
                "Filevine access denied: the connected account lacks permission for this action (or the authorization expired; re-run filevine-mcp-setup if so)."
            )
        raise FilevineClientError(
            f"Filevine token request failed (HTTP {resp.status_code}). Check credentials and region."
        )

    def get_valid_token(self):
        if not self.access_token or self.is_expired():
            self.fetch()
        return self.access_token


class FileVineClient:
    def __init__(self):
        if not ORG_ID:
            logger.warning(
                "Filevine request rejected",
                extra={"event": "request_rejected", "reason": "missing_org_id"},
            )
            raise ValueError("FILEVINE_ORG_ID is required. Run filevine-mcp-setup.")
        self.tm = TokenManager()
        self.session = requests.Session()
        self._refresh_headers()

    def _refresh_headers(self):
        token = self.tm.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-fv-orgId": ORG_ID,
        }
        self.session.headers.update(headers)

    def _request(
        self,
        method,
        path,
        params=None,
        json_body=None,
        _rate_retries=0,
        _retry_sleep=0,
        result_limit=None,
    ):
        if self.tm.is_expired():
            self._refresh_headers()

        url = f"{BASE_URL}{API_PREFIX}/{path.lstrip('/')}"
        try:
            resp = self.session.request(
                method, url, params=params, json=json_body, timeout=REQUEST_TIMEOUT
            )
        except (requests.Timeout, requests.ConnectionError):
            if method.upper() in {"GET", "HEAD", "OPTIONS"}:
                raise FilevineClientError(
                    "Filevine request timed out or lost its connection. Check connectivity and retry."
                ) from None
            raise FilevineClientError(
                "Filevine request timed out or lost its connection; the outcome is unknown. Check whether it completed before retrying."
            ) from None

        if resp.status_code == 401:
            self.tm.fetch()
            self._refresh_headers()
            try:
                resp = self.session.request(
                    method, url, params=params, json=json_body, timeout=REQUEST_TIMEOUT
                )
            except (requests.Timeout, requests.ConnectionError):
                if method.upper() in {"GET", "HEAD", "OPTIONS"}:
                    raise FilevineClientError(
                        "Filevine request timed out or lost its connection. Check connectivity and retry."
                    ) from None
                raise FilevineClientError(
                    "Filevine request timed out or lost its connection; the outcome is unknown. Check whether it completed before retrying."
                ) from None

        if resp.status_code == 429 and _rate_retries < 3:
            retry_after = max(0, _retry_after_seconds(resp))
            remaining = MAX_RETRY_SLEEP - _retry_sleep
            if retry_after > remaining:
                raise FilevineClientError(
                    f"Filevine rate limit reached. Retry after {retry_after} seconds."
                )
            print(f"Rate limited. Waiting {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            return self._request(
                method,
                path,
                params=params,
                json_body=json_body,
                _rate_retries=_rate_retries + 1,
                _retry_sleep=_retry_sleep + retry_after,
                result_limit=result_limit,
            )

        if resp.status_code == 401:
            raise FilevineClientError(
                "Filevine authorization failed (401). Re-run filevine-mcp-setup to reauthorize."
            )
        if resp.status_code == 403:
            raise FilevineClientError(
                "Filevine access denied: the connected account lacks permission for this action (or the authorization expired; re-run filevine-mcp-setup if so)."
            )
        if not resp.ok and resp.status_code != 204:
            if resp.status_code == 429:
                retry_hint = _retry_after_seconds(resp)
                raise FilevineClientError(
                    f"Filevine rate limit reached. Retry after {max(0, retry_hint)} seconds."
                )
            raise FilevineClientError(
                f"Filevine request failed with HTTP {resp.status_code}. Check account permissions and request details."
            )

        if resp.status_code == 204 or not resp.content:
            return {"success": True}

        payload = _json_response(resp)
        return (
            _cap_collection(payload, result_limit)
            if result_limit is not None
            else payload
        )

    def get(self, path, params=None, *, result_limit=None):
        return self._request("GET", path, params=params, result_limit=result_limit)

    def post(self, path, body=None):
        return self._request("POST", path, json_body=body)

    def patch(self, path, body=None):
        return self._request("PATCH", path, json_body=body)

    def put(self, path, body=None):
        return self._request("PUT", path, json_body=body)

    def delete(self, path):
        return self._request("DELETE", path)

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_me(self):
        return self.get("Users/Me")

    def list_users(self, limit=50, offset=0):
        return self.get(
            "Users",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_user(self, user_id):
        return self.get(f"users/{quote(str(user_id), safe='')}")

    def get_user_tasks(self, user_id, limit=50, offset=0):
        return self.get(
            f"users/{quote(str(user_id), safe='')}/tasks",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_user_appointments(self, user_id, limit=50, offset=0):
        return self.get(
            f"users/{quote(str(user_id), safe='')}/appointments",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_user_recent_projects(self, user_id):
        return self.get(f"users/{quote(str(user_id), safe='')}/recentprojects")

    def get_user_project_access(self, user_id, limit=50, offset=0):
        return self.get(
            f"users/{quote(str(user_id), safe='')}/projects/access",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    # ── Projects (Matters) ────────────────────────────────────────────────────

    def list_projects(
        self,
        limit=50,
        offset=0,
        sort_by="projectId",
        order_by="desc",
    ):
        return self.get(
            "Projects",
            {
                "limit": limit,
                "offset": offset,
                "sortBy": sort_by,
                "orderBy": order_by,
            },
            result_limit=limit,
        )

    def get_project(self, project_id):
        return self.get(f"Projects/{quote(str(project_id), safe='')}")

    def create_project(self, **fields):
        return self.post("Projects", fields)

    def update_project(self, project_id, **fields):
        return self.patch(f"Projects/{quote(str(project_id), safe='')}", fields)

    def archive_project(self, project_id):
        return self.delete(f"projects/{quote(str(project_id), safe='')}")

    def get_project_vitals(self, project_id):
        return self.get(f"Projects/{quote(str(project_id), safe='')}/Vitals")

    def get_project_form(self, project_id, selector):
        return self.get(
            f"Projects/{quote(str(project_id), safe='')}/Forms/{quote(str(selector), safe='')}"
        )

    def update_project_form(self, project_id, selector, **fields):
        return self.patch(
            f"Projects/{quote(str(project_id), safe='')}/Forms/{quote(str(selector), safe='')}",
            fields,
        )

    # ── Project Contacts ──────────────────────────────────────────────────────

    def get_project_contacts(
        self,
        project_id,
        limit=50,
        offset=0,
        sort_by="",
        order_by="desc",
    ):
        params = {"limit": limit, "offset": offset, "orderBy": order_by}
        if sort_by:
            params["sortBy"] = sort_by
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/contacts",
            params,
            result_limit=limit,
        )

    def add_contact_to_project(self, project_id, contact_id, **fields):
        body = {"contactId": contact_id, **fields}
        return self.post(f"projects/{quote(str(project_id), safe='')}/contacts", body)

    def update_project_contact(self, project_id, project_contact_id, **fields):
        return self.patch(
            f"Projects/{quote(str(project_id), safe='')}/contacts/{quote(str(project_contact_id), safe='')}",
            fields,
        )

    def remove_contact_from_project(self, project_id, project_contact_id):
        return self.delete(
            f"Projects/{quote(str(project_id), safe='')}/contacts/{quote(str(project_contact_id), safe='')}"
        )

    # ── Project Collections (Custom Sections) ─────────────────────────────────

    def list_collection_items(self, project_id, selector, limit=50, offset=0):
        return self.get(
            f"Projects/{quote(str(project_id), safe='')}/Collections/{quote(str(selector), safe='')}",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_collection_item(self, project_id, selector, unique_id):
        return self.get(
            f"Projects/{quote(str(project_id), safe='')}/Collections/{quote(str(selector), safe='')}/{quote(str(unique_id), safe='')}"
        )

    def create_collection_item(self, project_id, selector, **fields):
        return self.post(
            f"Projects/{quote(str(project_id), safe='')}/Collections/{quote(str(selector), safe='')}",
            fields,
        )

    def update_collection_item(self, project_id, selector, unique_id, **fields):
        return self.patch(
            f"Projects/{quote(str(project_id), safe='')}/Collections/{quote(str(selector), safe='')}/{quote(str(unique_id), safe='')}",
            fields,
        )

    def delete_collection_item(self, project_id, selector, unique_id):
        return self.delete(
            f"Projects/{quote(str(project_id), safe='')}/Collections/{quote(str(selector), safe='')}/{quote(str(unique_id), safe='')}"
        )

    # ── Project Teams ─────────────────────────────────────────────────────────

    def get_project_team(
        self,
        project_id,
        limit=50,
        offset=0,
        sort_by="",
        order_by="desc",
    ):
        params = {"limit": limit, "offset": offset, "orderBy": order_by}
        if sort_by:
            params["sortBy"] = sort_by
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/team",
            params,
            result_limit=limit,
        )

    def get_project_team_member(self, project_id, user_id):
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/team/{quote(str(user_id), safe='')}"
        )

    def update_project_team_member(self, project_id, user_id, **fields):
        return self.patch(
            f"projects/{quote(str(project_id), safe='')}/team/{quote(str(user_id), safe='')}",
            fields,
        )

    def remove_project_team_member(self, project_id, user_id):
        return self.delete(
            f"projects/{quote(str(project_id), safe='')}/team/{quote(str(user_id), safe='')}"
        )

    def add_team_member(self, project_id, **fields):
        return self.post(f"projects/{quote(str(project_id), safe='')}/team", fields)

    # ── Project Appointments ──────────────────────────────────────────────────

    def list_project_appointments(self, project_id, limit=50, offset=0):
        return self.get(
            f"Projects/{quote(str(project_id), safe='')}/Appointments",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def create_project_appointment(self, project_id, **fields):
        return self.post(
            f"Projects/{quote(str(project_id), safe='')}/Appointments", fields
        )

    # ── Project Notes ─────────────────────────────────────────────────────────

    def list_project_notes(self, project_id, limit=50, offset=0):
        return self.get(
            f"Projects/{quote(str(project_id), safe='')}/Notes",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def pin_note_to_project(self, project_id, note_id):
        return self.post(
            f"projects/{quote(str(project_id), safe='')}/notes/{quote(str(note_id), safe='')}/pin"
        )

    def unpin_note_from_project(self, project_id, note_id):
        return self.post(
            f"projects/{quote(str(project_id), safe='')}/notes/{quote(str(note_id), safe='')}/unpin"
        )

    # ── Project Deadlines ─────────────────────────────────────────────────────

    def list_project_deadlines(self, project_id, limit=50, offset=0):
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/deadlines",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_project_deadline(self, project_id, deadline_id):
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/deadlines/{quote(str(deadline_id), safe='')}"
        )

    def create_project_deadline(self, project_id, **fields):
        return self.post(
            f"projects/{quote(str(project_id), safe='')}/deadlines", fields
        )

    def update_project_deadline(self, project_id, deadline_id, **fields):
        return self.patch(
            f"projects/{quote(str(project_id), safe='')}/deadlines/{quote(str(deadline_id), safe='')}",
            fields,
        )

    def delete_project_deadline(self, project_id, deadline_id):
        return self.delete(
            f"projects/{quote(str(project_id), safe='')}/deadlines/{quote(str(deadline_id), safe='')}"
        )

    # ── Project Emails ────────────────────────────────────────────────────────

    def list_project_emails(self, project_id, limit=50, offset=0):
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/emails",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def add_email_to_project(self, project_id, **fields):
        return self.post(f"projects/{quote(str(project_id), safe='')}/emails", fields)

    # ── Project Invoices ──────────────────────────────────────────────────────

    def create_invoice(self, project_id, **fields):
        return self.post(f"projects/{quote(str(project_id), safe='')}/invoices", fields)

    def update_invoice(self, project_id, invoice_id, **fields):
        return self.put(
            f"projects/{quote(str(project_id), safe='')}/invoices/{quote(str(invoice_id), safe='')}",
            fields,
        )

    def delete_invoice(self, project_id, invoice_id):
        return self.delete(
            f"projects/{quote(str(project_id), safe='')}/invoices/{quote(str(invoice_id), safe='')}"
        )

    def finalize_invoice(self, project_id, invoice_id):
        return self.post(
            f"projects/{quote(str(project_id), safe='')}/invoices/{quote(str(invoice_id), safe='')}/finalize"
        )

    def get_project_invoices(self, project_id, limit=50, offset=0):
        return self.get(
            f"billing/projects/{quote(str(project_id), safe='')}/invoices",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_invoice_pdf(self, invoice_id):
        return self.get(f"billing/invoices/{quote(str(invoice_id), safe='')}/pdf")

    def approve_invoice(self, invoice_id):
        return self.post(f"billing/invoices/{quote(str(invoice_id), safe='')}/approve")

    def mark_invoice_sent(self, invoice_id):
        return self.post(
            f"billing/invoices/{quote(str(invoice_id), safe='')}/mark-as-sent"
        )

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, limit=50, offset=0):
        return self.get(
            "Contacts",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact(self, contact_id):
        return self.get(f"Contacts/{quote(str(contact_id), safe='')}")

    def create_contact(self, **fields):
        return self.post("Contacts", fields)

    def update_contact(self, contact_id, **fields):
        return self.patch(f"Contacts/{quote(str(contact_id), safe='')}", fields)

    def get_contact_addresses(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{quote(str(contact_id), safe='')}/addresses",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact_emails(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{quote(str(contact_id), safe='')}/emailaddresses",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact_phones(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{quote(str(contact_id), safe='')}/phones",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact_projects(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{quote(str(contact_id), safe='')}/projects",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_countries(self):
        return self.get("Contacts/Countries")

    def remove_tag_from_contacts(self, tag_name):
        return self.delete(f"Contacts/tags/{quote(str(tag_name), safe='')}")

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def list_tasks(self, limit=50, offset=0):
        return self.get("tasks", {"offset": offset}, result_limit=limit)

    def list_project_tasks(self, project_id, limit=50, offset=0):
        return self.get(
            f"projects/{quote(str(project_id), safe='')}/tasks",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_task(self, task_id):
        return self.get(f"tasks/{quote(str(task_id), safe='')}")

    def create_task(self, **fields):
        return self.post("tasks", fields)

    def update_task(self, task_id, **fields):
        return self.patch(f"tasks/{quote(str(task_id), safe='')}", fields)

    def delete_task(self, task_id):
        return self.delete(f"tasks/{quote(str(task_id), safe='')}")

    def complete_task(self, task_id):
        return self.post(f"tasks/{quote(str(task_id), safe='')}/complete")

    def incomplete_task(self, task_id):
        return self.post(f"tasks/{quote(str(task_id), safe='')}/incomplete")

    def assign_task(self, task_id, assignee_id):
        return self.patch(
            f"tasks/{quote(str(task_id), safe='')}/assign/{quote(str(assignee_id), safe='')}"
        )

    def pin_task(self, task_id):
        return self.post(f"tasks/{quote(str(task_id), safe='')}/pin")

    def unpin_task(self, task_id):
        return self.post(f"tasks/{quote(str(task_id), safe='')}/unpin")

    def snooze_task(self, task_id, due_date):
        return self.put(
            f"tasks/{quote(str(task_id), safe='')}/snooze", {"dueDate": due_date}
        )

    # ── Notes ─────────────────────────────────────────────────────────────────

    def list_notes(self, limit=50, offset=0):
        return self.get("Notes", {"offset": offset}, result_limit=limit)

    def get_note(self, note_id):
        return self.get(f"Notes/{quote(str(note_id), safe='')}")

    def create_note(self, **fields):
        return self.post("Notes", fields)

    def update_note(self, note_id, **fields):
        return self.patch(f"Notes/{quote(str(note_id), safe='')}", fields)

    def pin_note(self, note_id):
        return self.post(f"Notes/{quote(str(note_id), safe='')}/pin")

    def unpin_note(self, note_id):
        return self.post(f"Notes/{quote(str(note_id), safe='')}/unpin")

    def list_note_comments(
        self,
        note_id,
        limit=50,
        offset=0,
        order_by_descending=True,
    ):
        return self.get(
            f"Notes/{quote(str(note_id), safe='')}/Comments",
            {
                "orderByDescending": order_by_descending,
                "limit": limit,
                "offset": offset,
            },
            result_limit=limit,
        )

    def get_note_comment(self, note_id, comment_id):
        return self.get(
            f"Notes/{quote(str(note_id), safe='')}/Comments/{quote(str(comment_id), safe='')}"
        )

    def create_note_comment(self, note_id, **fields):
        return self.post(f"Notes/{quote(str(note_id), safe='')}/Comments", fields)

    def update_note_comment(self, note_id, comment_id, **fields):
        return self.patch(
            f"Notes/{quote(str(note_id), safe='')}/Comments/{quote(str(comment_id), safe='')}",
            fields,
        )

    def remove_tag_from_notes(self, tag_name):
        return self.delete(f"Notes/tags/{quote(str(tag_name), safe='')}")

    # ── Documents ─────────────────────────────────────────────────────────────

    def list_documents(self, limit=50, offset=0):
        return self.get(
            "Documents",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_document(self, document_id):
        return self.get(f"Documents/{quote(str(document_id), safe='')}")

    def create_document(self, **fields):
        return self.post("Documents", fields)

    def update_document(self, document_id, **fields):
        return self.patch(f"Documents/{quote(str(document_id), safe='')}", fields)

    def delete_document(self, document_id):
        return self.delete(f"Documents/{quote(str(document_id), safe='')}")

    def get_document_download_locator(self, document_id):
        return self.get(f"Documents/{quote(str(document_id), safe='')}/locator")

    def add_document_revision(self, document_id, **fields):
        return self.post(
            f"Documents/{quote(str(document_id), safe='')}/Revisions", fields
        )

    def lock_document(self, document_id):
        return self.post(f"Documents/{quote(str(document_id), safe='')}/lock")

    def unlock_document(self, document_id):
        return self.post(f"Documents/{quote(str(document_id), safe='')}/unlock")

    def move_documents(self, document_ids: list, folder_id):
        return self.post(
            "Documents/move", {"documentIds": document_ids, "folderId": folder_id}
        )

    def copy_documents(self, document_ids: list, folder_id):
        return self.post(
            "Documents/copy", {"documentIds": document_ids, "folderId": folder_id}
        )

    def batch_upload_documents(self, **fields):
        return self.post("Documents/batch/upload", fields)

    def confirm_batch_upload(self, **fields):
        return self.post("Documents/batch/upload/confirm", fields)

    def batch_download_documents(self, document_ids: list):
        return self.post("Documents/batch/download", {"documentIds": document_ids})

    def search_documents(self, query, project_id, limit=50, offset=0):
        return self.get(
            "DocumentSearch",
            {
                "searchTerm": query,
                "projectId": project_id,
                "limit": limit,
                "offset": offset,
            },
            result_limit=limit,
        )

    def add_document_to_project(self, project_id, document_id):
        return self.post(
            f"Projects/{quote(str(project_id), safe='')}/Documents/{quote(str(document_id), safe='')}"
        )

    def remove_tag_from_documents(self, tag_name):
        return self.delete(f"Documents/tags/{quote(str(tag_name), safe='')}")

    # ── Folders ───────────────────────────────────────────────────────────────

    def list_folders(
        self,
        limit=50,
        offset=0,
        ascending_order=False,
        sort_by_name=False,
    ):
        return self.get(
            "Folders",
            {
                "ascendingOrder": ascending_order,
                "sortByName": sort_by_name,
                "limit": limit,
                "offset": offset,
            },
            result_limit=limit,
        )

    def get_folder(self, folder_id):
        return self.get(f"Folders/{quote(str(folder_id), safe='')}")

    def create_folder(self, **fields):
        return self.post("Folders", fields)

    def update_folder(self, folder_id, **fields):
        return self.patch(f"Folders/{quote(str(folder_id), safe='')}", fields)

    def delete_folder(self, folder_id):
        return self.delete(f"Folders/{quote(str(folder_id), safe='')}")

    # ── Billing ───────────────────────────────────────────────────────────────

    def get_org_billing_codes(self):
        return self.get("Billing/AvailableBillingCodes")

    def get_org_billing_settings(self):
        return self.get("Billing/org/Settings")

    def get_project_billing_vitals(self, project_id):
        return self.get(
            f"Billing/projects/{quote(str(project_id), safe='')}/billingVitals"
        )

    def get_project_billing_settings(self, project_id):
        return self.get(
            f"Billing/projects/{quote(str(project_id), safe='')}/billingsettings"
        )

    def get_project_billing_codes(self, project_id):
        return self.get(
            f"Billing/{quote(str(project_id), safe='')}/AvailableBillingCodes"
        )

    def get_project_transactions(self, project_id, limit=50, offset=0):
        return self.get(
            f"Billing/projects/{quote(str(project_id), safe='')}/transactions",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_project_funds(self, project_id):
        return self.get(f"Billing/projects/{quote(str(project_id), safe='')}/funds")

    def get_project_fund_transactions(self, project_id, limit=50, offset=0):
        return self.get(
            f"Billing/projects/{quote(str(project_id), safe='')}/fundslist",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def create_billing_item(self, project_id, **fields):
        return self.post(
            f"projects/{quote(str(project_id), safe='')}/BillingItem", fields
        )

    def update_billing_item(self, project_id, billing_item_id, **fields):
        return self.put(
            f"projects/{quote(str(project_id), safe='')}/BillingItem/{quote(str(billing_item_id), safe='')}",
            fields,
        )

    def delete_billing_item(self, billing_item_id):
        return self.delete(
            f"Billing/Delete/BillingItem/{quote(str(billing_item_id), safe='')}"
        )

    def get_billing_item(self, project_id, billing_item_id):
        return self.get(
            f"billing/projects/{quote(str(project_id), safe='')}/billing-items/{quote(str(billing_item_id), safe='')}"
        )

    def create_payment(self, project_id, **fields):
        return self.post(
            f"billing/projects/{quote(str(project_id), safe='')}/payment", fields
        )

    def create_payment_and_apply(self, project_id, **fields):
        return self.post(
            f"billing/projects/{quote(str(project_id), safe='')}/payment/apply", fields
        )

    def get_payment_link(self, project_id):
        return self.get(
            f"billing/projects/{quote(str(project_id), safe='')}/payment-link"
        )

    def get_org_rate_schedules(self):
        return self.get("Billing/org/rateschedules")

    def set_project_rate_schedule(self, project_id, rate_schedule_id):
        return self.put(
            f"Billing/projects/{quote(str(project_id), safe='')}/rateschedule/{quote(str(rate_schedule_id), safe='')}"
        )

    # ── Webhooks ──────────────────────────────────────────────────────────────

    def list_webhook_events(self):
        return self.get("webhooks/Events")

    def list_webhook_subscriptions(self):
        return self.get("webhooks/subscriptions")

    def get_webhook_subscription(self, subscription_id):
        return self.get(f"webhooks/subscription/{quote(str(subscription_id), safe='')}")

    def create_webhook_subscription(self, event_name, target_url, **fields):
        body = {"eventName": event_name, "targetUrl": target_url, **fields}
        return self.post("webhooks/subscription", body)

    def update_webhook_subscription(self, subscription_id, **fields):
        return self.put(
            f"webhooks/subscription/{quote(str(subscription_id), safe='')}", fields
        )

    def delete_webhook_subscription(self, subscription_id):
        return self.delete(
            f"webhooks/subscription/{quote(str(subscription_id), safe='')}"
        )

    # ── Project Types ─────────────────────────────────────────────────────────

    def list_project_types(self, limit=50, offset=0):
        return self.get(
            "ProjectTypes",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_project_type(self, project_type_id):
        return self.get(f"ProjectTypes/{quote(str(project_type_id), safe='')}")

    # ── Document Series ───────────────────────────────────────────────────────

    def list_document_series(self, limit=50, last_id=0):
        return self.get(
            "DocumentSeries",
            {"limit": limit, "lastId": last_id},
            result_limit=limit,
        )

    def get_document_series(self, series_id):
        return self.get(f"DocumentSeries/{quote(str(series_id), safe='')}")

    # ── Reports ───────────────────────────────────────────────────────────────

    def list_reports(self, limit=50, offset=0):
        return self.get(
            "Reports",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_report(self, report_id):
        return self.get(f"Reports/{quote(str(report_id), safe='')}")

    # ── Share Links ───────────────────────────────────────────────────────────

    def list_share_links(self, limit=50, last_key=""):
        params: dict[str, int | str] = {"limit": limit}
        if last_key:
            params["lastKey"] = last_key
        return self.get("ShareLinks", params, result_limit=limit)

    def get_share_link(self, link_id):
        return self.get(f"ShareLinks/{quote(str(link_id), safe='')}")

    def create_share_link(self, **fields):
        return self.post("ShareLinks", fields)

    def delete_share_link(self, link_id):
        return self.delete(f"ShareLinks/{quote(str(link_id), safe='')}")

    # ── Mailroom ──────────────────────────────────────────────────────────────

    def list_mailroom(self, limit=50, offset=0):
        return self.get("Mailroom/Items", {"offset": offset}, result_limit=limit)

    def create_mailroom_item(self, **fields):
        return self.post("Mailroom/Items/Assign", fields)

    # ── Teams ─────────────────────────────────────────────────────────────────

    def list_teams(self):
        return self.get("teams")

    def get_team(self, team_id):
        return self.get(f"teams/{quote(str(team_id), safe='')}")

    def create_team(self, **fields):
        return self.post("teams", fields)

    def delete_team(self, team_id):
        return self.delete(f"teams/{quote(str(team_id), safe='')}")

    def list_project_teams(self, project_id):
        return self.get(f"projects/{quote(str(project_id), safe='')}/teams")

    # ── Recently Opened Documents ─────────────────────────────────────────────

    def list_recently_opened_documents(self, limit=50, offset=0):
        return self.get(
            "RecentlyOpenedDocuments",
            {"offset": offset},
            result_limit=limit,
        )

    # ── Classifications ───────────────────────────────────────────────────────

    def list_classifications(self):
        return self.get("classifications")

    # ── Hashtags ──────────────────────────────────────────────────────────────

    def create_hashtag(self, hashtag, **fields):
        return self.post(
            f"hashtags/{quote(str(hashtag), safe='')}", fields if fields else None
        )
