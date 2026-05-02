#!/usr/bin/env python3
"""Filevine API client. OAuth 2.0 client credentials, region-specific host, Bearer auth."""

import json
import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

REGIONS = {
    "us": {
        "api": "https://api.filevineapp.com",
        "identity": "https://identity.filevineapp.com",
    },
    "ca": {
        "api": "https://api.filevineapp.ca",
        "identity": "https://identity.filevineapp.ca",
    },
    "cjis": {
        "api": "https://api.filevinegov.com",
        "identity": "https://identity.filevinegov.com",
    },
}

CONFIG_DIR = Path.home() / ".filevine-mcp"
API_PREFIX = "/fv-app/v2"


def _load_env():
    env_file = CONFIG_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


_load_env()

CLIENT_ID = os.environ.get("FILEVINE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("FILEVINE_CLIENT_SECRET", "")
ORG_ID = os.environ.get("FILEVINE_ORG_ID", "")
REGION = os.environ.get("FILEVINE_REGION", "us").lower()

_region_cfg = REGIONS.get(REGION, REGIONS["us"])
BASE_URL = _region_cfg["api"]
IDENTITY_URL = _region_cfg["identity"]
TOKEN_URL = f"{IDENTITY_URL}/connect/token"


class TokenManager:
    def __init__(self):
        self.token_file = CONFIG_DIR / "tokens.json"
        self.tokens = self._load()

    def _load(self):
        if self.token_file.exists():
            with open(self.token_file) as f:
                return json.load(f)
        return {}

    def save(self, tokens):
        self.tokens = tokens
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_file, "w") as f:
            json.dump(tokens, f, indent=2)
        os.chmod(self.token_file, 0o600)

    @property
    def access_token(self):
        return self.tokens.get("access_token", "")

    def is_expired(self):
        expires_at = self.tokens.get("expires_at", 0)
        return time.time() >= expires_at - 60

    def fetch(self):
        resp = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "openid",
        })
        if resp.status_code == 200:
            tokens = resp.json()
            expires_in = tokens.get("expires_in", 3600)
            tokens["expires_at"] = time.time() + expires_in
            tokens["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self.save(tokens)
            return tokens
        raise RuntimeError(f"Token fetch failed ({resp.status_code}): {resp.text}")

    def get_valid_token(self):
        if not self.access_token or self.is_expired():
            self.fetch()
        return self.access_token


class FileVineClient:
    def __init__(self):
        self.tm = TokenManager()
        self.session = requests.Session()
        self._refresh_headers()

    def _refresh_headers(self):
        token = self.tm.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if ORG_ID:
            headers["x-fv-orgId"] = ORG_ID
        self.session.headers.update(headers)

    def _request(self, method, path, params=None, json_body=None, _rate_retries=0):
        if self.tm.is_expired():
            self._refresh_headers()

        url = f"{BASE_URL}{API_PREFIX}/{path.lstrip('/')}"
        resp = self.session.request(method, url, params=params, json=json_body)

        if resp.status_code == 401:
            self.tm.fetch()
            self._refresh_headers()
            resp = self.session.request(method, url, params=params, json=json_body)

        if resp.status_code == 429 and _rate_retries < 3:
            retry_after = int(resp.headers.get("Retry-After", 10))
            print(f"Rate limited. Waiting {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            return self._request(method, path, params=params, json_body=json_body,
                                  _rate_retries=_rate_retries + 1)

        if resp.status_code == 204 or not resp.content:
            return {"success": True}

        if not resp.ok:
            raise RuntimeError(f"Filevine API error {resp.status_code}: {resp.text[:400]}")

        return resp.json()

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

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

    def list_users(self):
        return self.get("Users")

    def get_user(self, user_id):
        return self.get(f"users/{user_id}")

    def get_user_tasks(self, user_id, page=1, page_size=50):
        return self.get(f"users/{user_id}/tasks",
                        {"requestedPage": page, "pageSize": page_size})

    def get_user_appointments(self, user_id):
        return self.get(f"users/{user_id}/appointments")

    def get_user_recent_projects(self, user_id):
        return self.get(f"users/{user_id}/recentprojects")

    def get_user_project_access(self, user_id):
        return self.get(f"users/{user_id}/projects/access")

    # ── Projects (Matters) ────────────────────────────────────────────────────

    def list_projects(self, page=1, page_size=50):
        return self.get("Projects", {"requestedPage": page, "pageSize": page_size})

    def get_project(self, project_id):
        return self.get(f"Projects/{project_id}")

    def create_project(self, **fields):
        return self.post("Projects", fields)

    def update_project(self, project_id, **fields):
        return self.patch(f"Projects/{project_id}", fields)

    def archive_project(self, project_id):
        return self.delete(f"projects/{project_id}")

    def get_project_vitals(self, project_id):
        return self.get(f"Projects/{project_id}/Vitals")

    def get_project_form(self, project_id, selector):
        return self.get(f"Projects/{project_id}/Forms/{selector}")

    def update_project_form(self, project_id, selector, **fields):
        return self.patch(f"Projects/{project_id}/Forms/{selector}", fields)

    # ── Project Contacts ──────────────────────────────────────────────────────

    def get_project_contacts(self, project_id):
        return self.get(f"projects/{project_id}/contacts")

    def add_contact_to_project(self, project_id, contact_id, **fields):
        body = {"contactId": contact_id, **fields}
        return self.post(f"projects/{project_id}/contacts", body)

    def update_project_contact(self, project_id, project_contact_id, **fields):
        return self.patch(f"Projects/{project_id}/contacts/{project_contact_id}", fields)

    def remove_contact_from_project(self, project_id, project_contact_id):
        return self.delete(f"Projects/{project_id}/contacts/{project_contact_id}")

    # ── Project Collections (Custom Sections) ─────────────────────────────────

    def list_collection_items(self, project_id, selector, page=1, page_size=50):
        return self.get(f"Projects/{project_id}/Collections/{selector}",
                        {"requestedPage": page, "pageSize": page_size})

    def get_collection_item(self, project_id, selector, unique_id):
        return self.get(f"Projects/{project_id}/Collections/{selector}/{unique_id}")

    def create_collection_item(self, project_id, selector, **fields):
        return self.post(f"Projects/{project_id}/Collections/{selector}", fields)

    def update_collection_item(self, project_id, selector, unique_id, **fields):
        return self.patch(f"Projects/{project_id}/Collections/{selector}/{unique_id}", fields)

    def delete_collection_item(self, project_id, selector, unique_id):
        return self.delete(f"Projects/{project_id}/Collections/{selector}/{unique_id}")

    # ── Project Teams ─────────────────────────────────────────────────────────

    def get_project_team(self, project_id):
        return self.get(f"projects/{project_id}/team")

    def get_project_team_member(self, project_id, user_id):
        return self.get(f"projects/{project_id}/team/{user_id}")

    def update_project_team_member(self, project_id, user_id, **fields):
        return self.patch(f"projects/{project_id}/team/{user_id}", fields)

    def remove_project_team_member(self, project_id, user_id):
        return self.delete(f"projects/{project_id}/team/{user_id}")

    def add_team_member(self, project_id, **fields):
        return self.post(f"projects/{project_id}/team", fields)

    # ── Project Appointments ──────────────────────────────────────────────────

    def list_project_appointments(self, project_id):
        return self.get(f"Projects/{project_id}/Appointments")

    def create_project_appointment(self, project_id, **fields):
        return self.post(f"Projects/{project_id}/Appointments", fields)

    # ── Project Notes ─────────────────────────────────────────────────────────

    def list_project_notes(self, project_id):
        return self.get(f"Projects/{project_id}/Notes")

    def pin_note_to_project(self, project_id, note_id):
        return self.post(f"projects/{project_id}/notes/{note_id}/pin")

    def unpin_note_from_project(self, project_id, note_id):
        return self.post(f"projects/{project_id}/notes/{note_id}/unpin")

    # ── Project Deadlines ─────────────────────────────────────────────────────

    def list_project_deadlines(self, project_id):
        return self.get(f"projects/{project_id}/deadlines")

    def get_project_deadline(self, project_id, deadline_id):
        return self.get(f"projects/{project_id}/deadlines/{deadline_id}")

    def create_project_deadline(self, project_id, **fields):
        return self.post(f"projects/{project_id}/deadlines", fields)

    def update_project_deadline(self, project_id, deadline_id, **fields):
        return self.patch(f"projects/{project_id}/deadlines/{deadline_id}", fields)

    def delete_project_deadline(self, project_id, deadline_id):
        return self.delete(f"projects/{project_id}/deadlines/{deadline_id}")

    # ── Project Emails ────────────────────────────────────────────────────────

    def list_project_emails(self, project_id):
        return self.get(f"projects/{project_id}/emails")

    def add_email_to_project(self, project_id, **fields):
        return self.post(f"projects/{project_id}/emails", fields)

    # ── Project Invoices ──────────────────────────────────────────────────────

    def create_invoice(self, project_id, **fields):
        return self.post(f"projects/{project_id}/invoices", fields)

    def update_invoice(self, project_id, invoice_id, **fields):
        return self.put(f"projects/{project_id}/invoices/{invoice_id}", fields)

    def delete_invoice(self, project_id, invoice_id):
        return self.delete(f"projects/{project_id}/invoices/{invoice_id}")

    def finalize_invoice(self, project_id, invoice_id):
        return self.post(f"projects/{project_id}/invoices/{invoice_id}/finalize")

    def get_project_invoices(self, project_id):
        return self.get(f"billing/projects/{project_id}/invoices")

    def get_invoice_pdf(self, invoice_id):
        return self.get(f"billing/invoices/{invoice_id}/pdf")

    def approve_invoice(self, invoice_id):
        return self.post(f"billing/invoices/{invoice_id}/approve")

    def mark_invoice_sent(self, invoice_id):
        return self.post(f"billing/invoices/{invoice_id}/mark-as-sent")

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, page=1, page_size=50):
        return self.get("Contacts", {"requestedPage": page, "pageSize": page_size})

    def get_contact(self, contact_id):
        return self.get(f"Contacts/{contact_id}")

    def create_contact(self, **fields):
        return self.post("Contacts", fields)

    def update_contact(self, contact_id, **fields):
        return self.patch(f"Contacts/{contact_id}", fields)

    def get_contact_addresses(self, contact_id):
        return self.get(f"Contacts/{contact_id}/addresses")

    def get_contact_emails(self, contact_id):
        return self.get(f"Contacts/{contact_id}/emailaddresses")

    def get_contact_phones(self, contact_id):
        return self.get(f"Contacts/{contact_id}/phones")

    def get_contact_projects(self, contact_id):
        return self.get(f"Contacts/{contact_id}/projects")

    def get_countries(self):
        return self.get("Contacts/Countries")

    def remove_tag_from_contacts(self, tag_name):
        return self.delete(f"Contacts/tags/{tag_name}")

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def list_tasks(self, page=1, page_size=50):
        return self.get("tasks", {"requestedPage": page, "pageSize": page_size})

    def list_project_tasks(self, project_id):
        return self.get(f"projects/{project_id}/tasks")

    def get_task(self, task_id):
        return self.get(f"tasks/{task_id}")

    def create_task(self, **fields):
        return self.post("tasks", fields)

    def update_task(self, task_id, **fields):
        return self.patch(f"tasks/{task_id}", fields)

    def delete_task(self, task_id):
        return self.delete(f"tasks/{task_id}")

    def complete_task(self, task_id):
        return self.post(f"tasks/{task_id}/complete")

    def uncomplete_task(self, task_id):
        return self.post(f"tasks/{task_id}/uncomplete")

    def assign_task(self, task_id, assignee_id):
        return self.patch(f"tasks/{task_id}/assign/{assignee_id}")

    def pin_task(self, task_id):
        return self.post(f"tasks/{task_id}/pin")

    def unpin_task(self, task_id):
        return self.post(f"tasks/{task_id}/unpin")

    def snooze_task(self, task_id, due_date):
        return self.put(f"tasks/{task_id}/snooze", {"dueDate": due_date})

    # ── Notes ─────────────────────────────────────────────────────────────────

    def list_notes(self, page=1, page_size=50):
        return self.get("Notes", {"requestedPage": page, "pageSize": page_size})

    def get_note(self, note_id):
        return self.get(f"Notes/{note_id}")

    def create_note(self, **fields):
        return self.post("Notes", fields)

    def update_note(self, note_id, **fields):
        return self.patch(f"Notes/{note_id}", fields)

    def pin_note(self, note_id):
        return self.post(f"Notes/{note_id}/pin")

    def unpin_note(self, note_id):
        return self.post(f"Notes/{note_id}/unpin")

    def list_note_comments(self, note_id):
        return self.get(f"Notes/{note_id}/Comments")

    def get_note_comment(self, note_id, comment_id):
        return self.get(f"Notes/{note_id}/Comments/{comment_id}")

    def create_note_comment(self, note_id, **fields):
        return self.post(f"Notes/{note_id}/Comments", fields)

    def update_note_comment(self, note_id, comment_id, **fields):
        return self.patch(f"Notes/{note_id}/Comments/{comment_id}", fields)

    def remove_tag_from_notes(self, tag_name):
        return self.delete(f"Notes/tags/{tag_name}")

    # ── Documents ─────────────────────────────────────────────────────────────

    def list_documents(self, page=1, page_size=50):
        return self.get("Documents", {"requestedPage": page, "pageSize": page_size})

    def get_document(self, document_id):
        return self.get(f"Documents/{document_id}")

    def create_document(self, **fields):
        return self.post("Documents", fields)

    def update_document(self, document_id, **fields):
        return self.patch(f"Documents/{document_id}", fields)

    def delete_document(self, document_id):
        return self.delete(f"Documents/{document_id}")

    def get_document_download_locator(self, document_id):
        return self.get(f"Documents/{document_id}/locator")

    def add_document_revision(self, document_id, **fields):
        return self.post(f"Documents/{document_id}/Revisions", fields)

    def lock_document(self, document_id):
        return self.post(f"Documents/{document_id}/lock")

    def unlock_document(self, document_id):
        return self.post(f"Documents/{document_id}/unlock")

    def move_documents(self, document_ids: list, folder_id):
        return self.post("Documents/move", {"documentIds": document_ids, "folderId": folder_id})

    def copy_documents(self, document_ids: list, folder_id):
        return self.post("Documents/copy", {"documentIds": document_ids, "folderId": folder_id})

    def batch_upload_documents(self, **fields):
        return self.post("Documents/batch/upload", fields)

    def confirm_batch_upload(self, **fields):
        return self.post("Documents/batch/upload/confirm", fields)

    def batch_download_documents(self, document_ids: list):
        return self.post("Documents/batch/download", {"documentIds": document_ids})

    def search_documents(self, query, page=1, page_size=50):
        return self.get("DocumentSearch",
                        {"query": query, "requestedPage": page, "pageSize": page_size})

    def add_document_to_project(self, project_id, document_id):
        return self.post(f"Projects/{project_id}/Documents/{document_id}")

    def remove_tag_from_documents(self, tag_name):
        return self.delete(f"Documents/tags/{tag_name}")

    # ── Folders ───────────────────────────────────────────────────────────────

    def list_folders(self, page=1, page_size=50):
        return self.get("Folders", {"requestedPage": page, "pageSize": page_size})

    def get_folder(self, folder_id):
        return self.get(f"Folders/{folder_id}")

    def create_folder(self, **fields):
        return self.post("Folders", fields)

    def update_folder(self, folder_id, **fields):
        return self.patch(f"Folders/{folder_id}", fields)

    def delete_folder(self, folder_id):
        return self.delete(f"Folders/{folder_id}")

    # ── Billing ───────────────────────────────────────────────────────────────

    def get_org_billing_codes(self):
        return self.get("Billing/AvailableBillingCodes")

    def get_org_billing_settings(self):
        return self.get("Billing/org/Settings")

    def get_project_billing_vitals(self, project_id):
        return self.get(f"Billing/projects/{project_id}/billingVitals")

    def get_project_billing_settings(self, project_id):
        return self.get(f"Billing/projects/{project_id}/billingsettings")

    def get_project_billing_codes(self, project_id):
        return self.get(f"Billing/{project_id}/AvailableBillingCodes")

    def get_project_transactions(self, project_id):
        return self.get(f"Billing/projects/{project_id}/transactions")

    def get_project_funds(self, project_id):
        return self.get(f"Billing/projects/{project_id}/funds")

    def get_project_fund_transactions(self, project_id):
        return self.get(f"Billing/projects/{project_id}/fundslist")

    def create_billing_item(self, project_id, **fields):
        return self.post(f"projects/{project_id}/BillingItem", fields)

    def update_billing_item(self, project_id, billing_item_id, **fields):
        return self.put(f"projects/{project_id}/BillingItem/{billing_item_id}", fields)

    def delete_billing_item(self, billing_item_id):
        return self.delete(f"Billing/Delete/BillingItem/{billing_item_id}")

    def get_billing_item(self, project_id, billing_item_id):
        return self.get(f"billing/projects/{project_id}/billing-items/{billing_item_id}")

    def create_payment(self, project_id, **fields):
        return self.post(f"billing/projects/{project_id}/payment", fields)

    def create_payment_and_apply(self, project_id, **fields):
        return self.post(f"billing/projects/{project_id}/payment/apply", fields)

    def get_payment_link(self, project_id):
        return self.get(f"billing/projects/{project_id}/payment-link")

    def get_org_rate_schedules(self):
        return self.get("Billing/org/rateschedules")

    def get_rate_schedules(self):
        return self.get("rate-schedules")

    def set_project_rate_schedule(self, project_id, rate_schedule_id):
        return self.put(f"Billing/projects/{project_id}/rateschedule/{rate_schedule_id}")

    # ── Webhooks ──────────────────────────────────────────────────────────────

    def list_webhook_events(self):
        return self.get("webhooks/Events")

    def list_webhook_subscriptions(self):
        return self.get("webhooks/subscriptions")

    def get_webhook_subscription(self, subscription_id):
        return self.get(f"webhooks/subscription/{subscription_id}")

    def create_webhook_subscription(self, event_name, target_url, **fields):
        body = {"eventName": event_name, "targetUrl": target_url, **fields}
        return self.post("webhooks/subscription", body)

    def update_webhook_subscription(self, subscription_id, **fields):
        return self.put(f"webhooks/subscription/{subscription_id}", fields)

    def delete_webhook_subscription(self, subscription_id):
        return self.delete(f"webhooks/subscription/{subscription_id}")

    # ── Project Types ─────────────────────────────────────────────────────────

    def list_project_types(self):
        return self.get("ProjectTypes")

    def get_project_type(self, project_type_id):
        return self.get(f"ProjectTypes/{project_type_id}")

    # ── Document Series ───────────────────────────────────────────────────────

    def list_document_series(self):
        return self.get("DocumentSeries")

    def get_document_series(self, series_id):
        return self.get(f"DocumentSeries/{series_id}")

    # ── Reports ───────────────────────────────────────────────────────────────

    def list_reports(self):
        return self.get("Reports")

    def get_report(self, report_id):
        return self.get(f"Reports/{report_id}")

    # ── Share Links ───────────────────────────────────────────────────────────

    def list_share_links(self):
        return self.get("ShareLinks")

    def get_share_link(self, link_id):
        return self.get(f"ShareLinks/{link_id}")

    def create_share_link(self, **fields):
        return self.post("ShareLinks", fields)

    def delete_share_link(self, link_id):
        return self.delete(f"ShareLinks/{link_id}")

    # ── Mailroom ──────────────────────────────────────────────────────────────

    def list_mailroom(self):
        return self.get("Mailroom")

    def create_mailroom_item(self, **fields):
        return self.post("Mailroom", fields)

    # ── Teams ─────────────────────────────────────────────────────────────────

    def list_teams(self):
        return self.get("teams")

    def get_team(self, team_id):
        return self.get(f"teams/{team_id}")

    def create_team(self, **fields):
        return self.post("teams", fields)

    def update_team(self, team_id, **fields):
        return self.put(f"teams/{team_id}", fields)

    def delete_team(self, team_id):
        return self.delete(f"teams/{team_id}")

    def list_project_teams(self, project_id):
        return self.get(f"projects/{project_id}/teams")

    # ── Recently Opened Documents ─────────────────────────────────────────────

    def list_recently_opened_documents(self):
        return self.get("RecentlyOpenedDocuments")

    # ── Classifications ───────────────────────────────────────────────────────

    def list_classifications(self):
        return self.get("classifications")

    # ── Hashtags ──────────────────────────────────────────────────────────────

    def create_hashtag(self, **fields):
        return self.post("hashtags", fields)
