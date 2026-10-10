#!/usr/bin/env python3
"""Filevine API client. OAuth 2.0 client credentials, region-specific host, Bearer auth."""

import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Lock
from urllib.parse import quote

import requests
from mcp.server.mcpserver.exceptions import ToolError

from filevine_mcp import credentials
from filevine_mcp.regions import region_config
from filevine_mcp.url_security import validate_public_https

from filevine_mcp.private_file import write_private_file

logger = logging.getLogger(__name__)
_TOKEN_REFRESH_LOCK = Lock()

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
REGION = os.environ.get("FILEVINE_REGION", "us").strip().lower()
FILEVINE_PAT = os.environ.get("FILEVINE_PAT", "")

_region_cfg = region_config(REGION, REGIONS)
BASE_URL = _region_cfg["api"]
IDENTITY_URL = _region_cfg["identity"]
TOKEN_URL = f"{IDENTITY_URL}/connect/token"
REQUEST_TIMEOUT = 30
MAX_RETRY_SLEEP = 60


def _path_id(value, parameter: str) -> str:
    """Validate a plain identifier before URL quoting or any HTTP request."""
    expected = (
        "a non-empty plain identifier (ASCII letters, digits, -, _, ., ~); not . or .."
    )
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or str(value) in {".", ".."}
        or re.fullmatch(r"[A-Za-z0-9._~-]+", str(value)) is None
    ):
        message = f"Invalid argument '{parameter}': use {expected}."
        raise FilevineClientError(message)
    return quote(str(value), safe="")


class FilevineClientError(ToolError, RuntimeError):
    """A safe, actionable failure suitable for returning to an MCP client."""


def _retry_after_seconds(resp, default=10):
    """Honor numeric and HTTP-date delays without sleeping beyond the budget."""
    value = resp.headers.get("Retry-After", default)
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return default
    if not math.isfinite(seconds):
        return default
    return max(0, math.ceil(seconds))


def _json_response(resp):
    try:
        return resp.json()
    except ValueError:
        raise FilevineClientError("Filevine returned an unreadable response.") from None


def _token_response(resp):
    """Decode a token envelope without trusting its shape or values."""
    payload = _json_response(resp)
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("access_token"), str)
        or not payload.get("access_token")
    ):
        raise FilevineClientError(
            "Filevine returned an invalid authorization response. Re-run filevine-mcp-setup."
        )
    expires_in = payload.get("expires_in", 3600)
    if (
        isinstance(expires_in, bool)
        or not isinstance(expires_in, (int, float))
        or (isinstance(expires_in, float) and not math.isfinite(expires_in))
        or expires_in < 0
        or expires_in > 315_360_000
    ):
        raise FilevineClientError(
            "Filevine returned an invalid authorization response. Re-run filevine-mcp-setup."
        )
    return payload


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
        write_private_file(self.token_file, json.dumps(tokens, indent=2))
        self.tokens = tokens

    @property
    def access_token(self):
        return self.tokens.get("access_token", "")

    def is_expired(self):
        expires_at = self.tokens.get("expires_at", 0)
        return time.time() >= expires_at - 60

    def fetch(self):
        # HTTP tools run in worker threads with separate TokenManager instances.
        # Serialize rotation and reuse tokens another request has already saved.
        with _TOKEN_REFRESH_LOCK:
            if getattr(self, "token_file", None) is not None:
                latest = self._load()
                if latest != self.tokens and latest.get("access_token"):
                    self.tokens = latest
                    return latest
            return self._fetch()

    def _fetch(self):
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
            tokens = _token_response(resp)
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
        if not 200 <= resp.status_code < 300:
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
        return self.get(f"users/{_path_id(user_id, 'user_id')}")

    def get_user_tasks(self, user_id, limit=50, offset=0):
        return self.get(
            f"users/{_path_id(user_id, 'user_id')}/tasks",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_user_appointments(self, user_id, limit=50, offset=0):
        return self.get(
            f"users/{_path_id(user_id, 'user_id')}/appointments",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_user_recent_projects(self, user_id):
        return self.get(f"users/{_path_id(user_id, 'user_id')}/recentprojects")

    def get_user_project_access(self, user_id, limit=50, offset=0):
        return self.get(
            f"users/{_path_id(user_id, 'user_id')}/projects/access",
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
        return self.get(f"Projects/{_path_id(project_id, 'project_id')}")

    def create_project(self, **fields):
        return self.post("Projects", fields)

    def update_project(self, project_id, **fields):
        return self.patch(f"Projects/{_path_id(project_id, 'project_id')}", fields)

    def archive_project(self, project_id):
        return self.delete(f"projects/{_path_id(project_id, 'project_id')}")

    def get_project_vitals(self, project_id):
        return self.get(f"Projects/{_path_id(project_id, 'project_id')}/Vitals")

    def get_project_form(self, project_id, selector):
        return self.get(
            f"Projects/{_path_id(project_id, 'project_id')}/Forms/{_path_id(selector, 'selector')}"
        )

    def update_project_form(self, project_id, selector, **fields):
        return self.patch(
            f"Projects/{_path_id(project_id, 'project_id')}/Forms/{_path_id(selector, 'selector')}",
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
            f"projects/{_path_id(project_id, 'project_id')}/contacts",
            params,
            result_limit=limit,
        )

    def add_contact_to_project(self, project_id, contact_id, **fields):
        body = {"contactId": contact_id, **fields}
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/contacts", body
        )

    def update_project_contact(self, project_id, project_contact_id, **fields):
        return self.patch(
            f"Projects/{_path_id(project_id, 'project_id')}/contacts/{_path_id(project_contact_id, 'project_contact_id')}",
            fields,
        )

    def remove_contact_from_project(self, project_id, project_contact_id):
        return self.delete(
            f"Projects/{_path_id(project_id, 'project_id')}/contacts/{_path_id(project_contact_id, 'project_contact_id')}"
        )

    # ── Project Collections (Custom Sections) ─────────────────────────────────

    def list_collection_items(self, project_id, selector, limit=50, offset=0):
        return self.get(
            f"Projects/{_path_id(project_id, 'project_id')}/Collections/{_path_id(selector, 'selector')}",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_collection_item(self, project_id, selector, unique_id):
        return self.get(
            f"Projects/{_path_id(project_id, 'project_id')}/Collections/{_path_id(selector, 'selector')}/{_path_id(unique_id, 'unique_id')}"
        )

    def create_collection_item(self, project_id, selector, **fields):
        return self.post(
            f"Projects/{_path_id(project_id, 'project_id')}/Collections/{_path_id(selector, 'selector')}",
            fields,
        )

    def update_collection_item(self, project_id, selector, unique_id, **fields):
        return self.patch(
            f"Projects/{_path_id(project_id, 'project_id')}/Collections/{_path_id(selector, 'selector')}/{_path_id(unique_id, 'unique_id')}",
            fields,
        )

    def delete_collection_item(self, project_id, selector, unique_id):
        return self.delete(
            f"Projects/{_path_id(project_id, 'project_id')}/Collections/{_path_id(selector, 'selector')}/{_path_id(unique_id, 'unique_id')}"
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
            f"projects/{_path_id(project_id, 'project_id')}/team",
            params,
            result_limit=limit,
        )

    def get_project_team_member(self, project_id, user_id):
        return self.get(
            f"projects/{_path_id(project_id, 'project_id')}/team/{_path_id(user_id, 'user_id')}"
        )

    def update_project_team_member(self, project_id, user_id, **fields):
        return self.patch(
            f"projects/{_path_id(project_id, 'project_id')}/team/{_path_id(user_id, 'user_id')}",
            fields,
        )

    def remove_project_team_member(self, project_id, user_id):
        return self.delete(
            f"projects/{_path_id(project_id, 'project_id')}/team/{_path_id(user_id, 'user_id')}"
        )

    def add_team_member(self, project_id, **fields):
        return self.post(f"projects/{_path_id(project_id, 'project_id')}/team", fields)

    # ── Project Appointments ──────────────────────────────────────────────────

    def list_project_appointments(self, project_id, limit=50, offset=0):
        return self.get(
            f"Projects/{_path_id(project_id, 'project_id')}/Appointments",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def create_project_appointment(self, project_id, **fields):
        return self.post(
            f"Projects/{_path_id(project_id, 'project_id')}/Appointments", fields
        )

    # ── Project Notes ─────────────────────────────────────────────────────────

    def list_project_notes(self, project_id, limit=50, offset=0):
        return self.get(
            f"Projects/{_path_id(project_id, 'project_id')}/Notes",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def pin_note_to_project(self, project_id, note_id):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/notes/{_path_id(note_id, 'note_id')}/pin"
        )

    def unpin_note_from_project(self, project_id, note_id):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/notes/{_path_id(note_id, 'note_id')}/unpin"
        )

    # ── Project Deadlines ─────────────────────────────────────────────────────

    def list_project_deadlines(self, project_id, limit=50, offset=0):
        return self.get(
            f"projects/{_path_id(project_id, 'project_id')}/deadlines",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_project_deadline(self, project_id, deadline_id):
        return self.get(
            f"projects/{_path_id(project_id, 'project_id')}/deadlines/{_path_id(deadline_id, 'deadline_id')}"
        )

    def create_project_deadline(self, project_id, **fields):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/deadlines", fields
        )

    def update_project_deadline(self, project_id, deadline_id, **fields):
        return self.patch(
            f"projects/{_path_id(project_id, 'project_id')}/deadlines/{_path_id(deadline_id, 'deadline_id')}",
            fields,
        )

    def delete_project_deadline(self, project_id, deadline_id):
        return self.delete(
            f"projects/{_path_id(project_id, 'project_id')}/deadlines/{_path_id(deadline_id, 'deadline_id')}"
        )

    # ── Project Emails ────────────────────────────────────────────────────────

    def list_project_emails(self, project_id, limit=50, offset=0):
        return self.get(
            f"projects/{_path_id(project_id, 'project_id')}/emails",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def add_email_to_project(self, project_id, **fields):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/emails", fields
        )

    # ── Project Invoices ──────────────────────────────────────────────────────

    def create_invoice(self, project_id, **fields):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/invoices", fields
        )

    def update_invoice(self, project_id, invoice_id, **fields):
        return self.put(
            f"projects/{_path_id(project_id, 'project_id')}/invoices/{_path_id(invoice_id, 'invoice_id')}",
            fields,
        )

    def delete_invoice(self, project_id, invoice_id):
        return self.delete(
            f"projects/{_path_id(project_id, 'project_id')}/invoices/{_path_id(invoice_id, 'invoice_id')}"
        )

    def finalize_invoice(self, project_id, invoice_id):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/invoices/{_path_id(invoice_id, 'invoice_id')}/finalize"
        )

    def get_project_invoices(self, project_id, limit=50, offset=0):
        return self.get(
            f"billing/projects/{_path_id(project_id, 'project_id')}/invoices",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_invoice_pdf(self, invoice_id):
        return self.get(f"billing/invoices/{_path_id(invoice_id, 'invoice_id')}/pdf")

    def approve_invoice(self, invoice_id):
        return self.post(
            f"billing/invoices/{_path_id(invoice_id, 'invoice_id')}/approve"
        )

    def mark_invoice_sent(self, invoice_id):
        return self.post(
            f"billing/invoices/{_path_id(invoice_id, 'invoice_id')}/mark-as-sent"
        )

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, limit=50, offset=0):
        return self.get(
            "Contacts",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact(self, contact_id):
        return self.get(f"Contacts/{_path_id(contact_id, 'contact_id')}")

    def create_contact(self, **fields):
        return self.post("Contacts", fields)

    def update_contact(self, contact_id, **fields):
        return self.patch(f"Contacts/{_path_id(contact_id, 'contact_id')}", fields)

    def get_contact_addresses(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{_path_id(contact_id, 'contact_id')}/addresses",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact_emails(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{_path_id(contact_id, 'contact_id')}/emailaddresses",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact_phones(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{_path_id(contact_id, 'contact_id')}/phones",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_contact_projects(self, contact_id, limit=50, offset=0):
        return self.get(
            f"Contacts/{_path_id(contact_id, 'contact_id')}/projects",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_countries(self):
        return self.get("Contacts/Countries")

    def remove_tag_from_contacts(self, tag_name):
        return self.delete(f"Contacts/tags/{_path_id(tag_name, 'tag_name')}")

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def list_tasks(self, limit=50, offset=0):
        return self.get("tasks", {"offset": offset}, result_limit=limit)

    def list_project_tasks(self, project_id, limit=50, offset=0):
        return self.get(
            f"projects/{_path_id(project_id, 'project_id')}/tasks",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_task(self, task_id):
        return self.get(f"tasks/{_path_id(task_id, 'task_id')}")

    def create_task(self, **fields):
        return self.post("tasks", fields)

    def update_task(self, task_id, **fields):
        return self.patch(f"tasks/{_path_id(task_id, 'task_id')}", fields)

    def delete_task(self, task_id):
        return self.delete(f"tasks/{_path_id(task_id, 'task_id')}")

    def complete_task(self, task_id):
        return self.post(f"tasks/{_path_id(task_id, 'task_id')}/complete")

    def incomplete_task(self, task_id):
        return self.post(f"tasks/{_path_id(task_id, 'task_id')}/incomplete")

    def assign_task(self, task_id, assignee_id):
        return self.patch(
            f"tasks/{_path_id(task_id, 'task_id')}/assign/{_path_id(assignee_id, 'assignee_id')}"
        )

    def pin_task(self, task_id):
        return self.post(f"tasks/{_path_id(task_id, 'task_id')}/pin")

    def unpin_task(self, task_id):
        return self.post(f"tasks/{_path_id(task_id, 'task_id')}/unpin")

    def snooze_task(self, task_id, due_date):
        return self.put(
            f"tasks/{_path_id(task_id, 'task_id')}/snooze", {"dueDate": due_date}
        )

    # ── Notes ─────────────────────────────────────────────────────────────────

    def list_notes(self, limit=50, offset=0):
        return self.get("Notes", {"offset": offset}, result_limit=limit)

    def get_note(self, note_id):
        return self.get(f"Notes/{_path_id(note_id, 'note_id')}")

    def create_note(self, **fields):
        return self.post("Notes", fields)

    def update_note(self, note_id, **fields):
        return self.patch(f"Notes/{_path_id(note_id, 'note_id')}", fields)

    def pin_note(self, note_id):
        return self.post(f"Notes/{_path_id(note_id, 'note_id')}/pin")

    def unpin_note(self, note_id):
        return self.post(f"Notes/{_path_id(note_id, 'note_id')}/unpin")

    def list_note_comments(
        self,
        note_id,
        limit=50,
        offset=0,
        order_by_descending=True,
    ):
        return self.get(
            f"Notes/{_path_id(note_id, 'note_id')}/Comments",
            {
                "orderByDescending": order_by_descending,
                "limit": limit,
                "offset": offset,
            },
            result_limit=limit,
        )

    def get_note_comment(self, note_id, comment_id):
        return self.get(
            f"Notes/{_path_id(note_id, 'note_id')}/Comments/{_path_id(comment_id, 'comment_id')}"
        )

    def create_note_comment(self, note_id, **fields):
        return self.post(f"Notes/{_path_id(note_id, 'note_id')}/Comments", fields)

    def update_note_comment(self, note_id, comment_id, **fields):
        return self.patch(
            f"Notes/{_path_id(note_id, 'note_id')}/Comments/{_path_id(comment_id, 'comment_id')}",
            fields,
        )

    def remove_tag_from_notes(self, tag_name):
        return self.delete(f"Notes/tags/{_path_id(tag_name, 'tag_name')}")

    # ── Documents ─────────────────────────────────────────────────────────────

    def list_documents(self, limit=50, offset=0):
        return self.get(
            "Documents",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_document(self, document_id):
        return self.get(f"Documents/{_path_id(document_id, 'document_id')}")

    def create_document(self, **fields):
        return self.post("Documents", fields)

    def update_document(self, document_id, **fields):
        return self.patch(f"Documents/{_path_id(document_id, 'document_id')}", fields)

    def delete_document(self, document_id):
        return self.delete(f"Documents/{_path_id(document_id, 'document_id')}")

    def get_document_download_locator(self, document_id):
        return self.get(f"Documents/{_path_id(document_id, 'document_id')}/locator")

    def add_document_revision(self, document_id, **fields):
        return self.post(
            f"Documents/{_path_id(document_id, 'document_id')}/Revisions", fields
        )

    def lock_document(self, document_id):
        return self.post(f"Documents/{_path_id(document_id, 'document_id')}/lock")

    def unlock_document(self, document_id):
        return self.post(f"Documents/{_path_id(document_id, 'document_id')}/unlock")

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
            f"Projects/{_path_id(project_id, 'project_id')}/Documents/{_path_id(document_id, 'document_id')}"
        )

    def remove_tag_from_documents(self, tag_name):
        return self.delete(f"Documents/tags/{_path_id(tag_name, 'tag_name')}")

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
        return self.get(f"Folders/{_path_id(folder_id, 'folder_id')}")

    def create_folder(self, **fields):
        return self.post("Folders", fields)

    def update_folder(self, folder_id, **fields):
        return self.patch(f"Folders/{_path_id(folder_id, 'folder_id')}", fields)

    def delete_folder(self, folder_id):
        return self.delete(f"Folders/{_path_id(folder_id, 'folder_id')}")

    # ── Billing ───────────────────────────────────────────────────────────────

    def get_org_billing_codes(self):
        return self.get("Billing/AvailableBillingCodes")

    def get_org_billing_settings(self):
        return self.get("Billing/org/Settings")

    def get_project_billing_vitals(self, project_id):
        return self.get(
            f"Billing/projects/{_path_id(project_id, 'project_id')}/billingVitals"
        )

    def get_project_billing_settings(self, project_id):
        return self.get(
            f"Billing/projects/{_path_id(project_id, 'project_id')}/billingsettings"
        )

    def get_project_billing_codes(self, project_id):
        return self.get(
            f"Billing/{_path_id(project_id, 'project_id')}/AvailableBillingCodes"
        )

    def get_project_transactions(self, project_id, limit=50, offset=0):
        return self.get(
            f"Billing/projects/{_path_id(project_id, 'project_id')}/transactions",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_project_funds(self, project_id):
        return self.get(f"Billing/projects/{_path_id(project_id, 'project_id')}/funds")

    def get_project_fund_transactions(self, project_id, limit=50, offset=0):
        return self.get(
            f"Billing/projects/{_path_id(project_id, 'project_id')}/fundslist",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def create_billing_item(self, project_id, **fields):
        return self.post(
            f"projects/{_path_id(project_id, 'project_id')}/BillingItem", fields
        )

    def update_billing_item(self, project_id, billing_item_id, **fields):
        return self.put(
            f"projects/{_path_id(project_id, 'project_id')}/BillingItem/{_path_id(billing_item_id, 'billing_item_id')}",
            fields,
        )

    def delete_billing_item(self, billing_item_id):
        return self.delete(
            f"Billing/Delete/BillingItem/{_path_id(billing_item_id, 'billing_item_id')}"
        )

    def get_billing_item(self, project_id, billing_item_id):
        return self.get(
            f"billing/projects/{_path_id(project_id, 'project_id')}/billing-items/{_path_id(billing_item_id, 'billing_item_id')}"
        )

    def create_payment(self, project_id, **fields):
        return self.post(
            f"billing/projects/{_path_id(project_id, 'project_id')}/payment", fields
        )

    def create_payment_and_apply(self, project_id, **fields):
        return self.post(
            f"billing/projects/{_path_id(project_id, 'project_id')}/payment/apply",
            fields,
        )

    def get_payment_link(self, project_id):
        return self.get(
            f"billing/projects/{_path_id(project_id, 'project_id')}/payment-link"
        )

    def get_org_rate_schedules(self):
        return self.get("Billing/org/rateschedules")

    def set_project_rate_schedule(self, project_id, rate_schedule_id):
        return self.put(
            f"Billing/projects/{_path_id(project_id, 'project_id')}/rateschedule/{_path_id(rate_schedule_id, 'rate_schedule_id')}"
        )

    # ── Webhooks ──────────────────────────────────────────────────────────────

    def list_webhook_events(self):
        return self.get("webhooks/Events")

    def list_webhook_subscriptions(self):
        return self.get("webhooks/subscriptions")

    def get_webhook_subscription(self, subscription_id):
        return self.get(
            f"webhooks/subscription/{_path_id(subscription_id, 'subscription_id')}"
        )

    def create_webhook_subscription(self, event_name, target_url, **fields):
        validate_public_https(target_url)
        _validate_webhook_fields(fields)
        body = {**fields, "eventName": event_name, "targetUrl": target_url}
        return self.post("webhooks/subscription", body)

    def update_webhook_subscription(self, subscription_id, **fields):
        _validate_webhook_fields({k: v for k, v in fields.items() if k != "targetUrl"})
        if "targetUrl" in fields:
            validate_public_https(fields["targetUrl"])
        return self.put(
            f"webhooks/subscription/{_path_id(subscription_id, 'subscription_id')}",
            fields,
        )

    def delete_webhook_subscription(self, subscription_id):
        return self.delete(
            f"webhooks/subscription/{_path_id(subscription_id, 'subscription_id')}"
        )

    # ── Project Types ─────────────────────────────────────────────────────────

    def list_project_types(self, limit=50, offset=0):
        return self.get(
            "ProjectTypes",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_project_type(self, project_type_id):
        return self.get(f"ProjectTypes/{_path_id(project_type_id, 'project_type_id')}")

    # ── Document Series ───────────────────────────────────────────────────────

    def list_document_series(self, limit=50, last_id=0):
        return self.get(
            "DocumentSeries",
            {"limit": limit, "lastId": last_id},
            result_limit=limit,
        )

    def get_document_series(self, series_id):
        return self.get(f"DocumentSeries/{_path_id(series_id, 'series_id')}")

    # ── Reports ───────────────────────────────────────────────────────────────

    def list_reports(self, limit=50, offset=0):
        return self.get(
            "Reports",
            {"limit": limit, "offset": offset},
            result_limit=limit,
        )

    def get_report(self, report_id):
        return self.get(f"Reports/{_path_id(report_id, 'report_id')}")

    # ── Share Links ───────────────────────────────────────────────────────────

    def list_share_links(self, limit=50, last_key=""):
        params: dict[str, int | str] = {"limit": limit}
        if last_key:
            params["lastKey"] = last_key
        return self.get("ShareLinks", params, result_limit=limit)

    def get_share_link(self, link_id):
        return self.get(f"ShareLinks/{_path_id(link_id, 'link_id')}")

    def create_share_link(self, **fields):
        return self.post("ShareLinks", fields)

    def delete_share_link(self, link_id):
        return self.delete(f"ShareLinks/{_path_id(link_id, 'link_id')}")

    # ── Mailroom ──────────────────────────────────────────────────────────────

    def list_mailroom(self, limit=50, offset=0):
        return self.get("Mailroom/Items", {"offset": offset}, result_limit=limit)

    def create_mailroom_item(self, **fields):
        return self.post("Mailroom/Items/Assign", fields)

    # ── Teams ─────────────────────────────────────────────────────────────────

    def list_teams(self):
        return self.get("teams")

    def get_team(self, team_id):
        return self.get(f"teams/{_path_id(team_id, 'team_id')}")

    def create_team(self, **fields):
        return self.post("teams", fields)

    def delete_team(self, team_id):
        return self.delete(f"teams/{_path_id(team_id, 'team_id')}")

    def list_project_teams(self, project_id):
        return self.get(f"projects/{_path_id(project_id, 'project_id')}/teams")

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
            f"hashtags/{_path_id(hashtag, 'hashtag')}", fields if fields else None
        )


# Exact aliases after case/separator normalization, including nested JSON values.
DESTINATION_KEYS = frozenset(
    {
        "url",
        "uri",
        "targeturl",
        "targeturi",
        "callbackurl",
        "callbackuri",
        "baseurl",
        "baseurlpattern",
        "webhookurl",
        "webhookuri",
        "destinationurl",
        "destinationuri",
        "redirecturl",
        "redirecturi",
        "endpointurl",
        "endpointuri",
        "uploadurl",
        "storageurl",
        "pluginurl",
    }
)


def _validate_webhook_fields(fields):
    """Validate explicit destination aliases recursively without substring matching."""
    if isinstance(fields, dict):
        for key, value in fields.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in DESTINATION_KEYS:
                validate_public_https(value)
            _validate_webhook_fields(value)
    elif isinstance(fields, list):
        for value in fields:
            _validate_webhook_fields(value)
