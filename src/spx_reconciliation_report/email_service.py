"""Local Google OAuth and Gmail sending service."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import http.server
import json
import os
import secrets
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable


GOOGLE = "GOOGLE"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_from_seconds(seconds: int | float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(seconds))))\
        .replace(microsecond=0).isoformat()


def _request(url: str, *, data: bytes | None = None, headers: dict | None = None,
             method: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        # Keep provider diagnostics limited to stable error codes; response bodies may
        # contain account details or other sensitive information.
        if exc.code in {401, 403}:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                payload = {}
            details = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = str(details.get("code", "")) if isinstance(details, dict) else ""
            errors = details.get("errors", []) if isinstance(details, dict) else []
            if errors and isinstance(errors[0], dict):
                code = str(errors[0].get("reason", code))
            normalized = code.casefold()
            if exc.code == 403 and "accessnotconfigured" in normalized:
                message = "Gmail API is disabled for this OAuth project. Enable Gmail API in Google Cloud Console, then reconnect the sender account."
            elif exc.code == 403 and ("insufficientpermissions" in normalized or
                                      "authorization_requestdenied" in normalized or
                                      "erroraccessdenied" in normalized):
                message = "The sender account has not granted permission to send mail. Reconnect the sender and approve Gmail send permission."
            else:
                message = f"Authentication failed (HTTP {exc.code}). Reconnect the sender account and try again."
            raise RuntimeError(message) from exc
        raise RuntimeError(f"Email provider request failed (HTTP {exc.code}).") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError("Connection timeout while contacting the email provider.") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError("Connection timeout while contacting the email provider.") from exc
        raise RuntimeError("Could not reach the email provider.") from exc
    except OSError as exc:
        raise RuntimeError("Could not reach the email provider.") from exc
    if not payload:
        return {}
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Email provider returned an invalid response.") from exc


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Secure email token storage is only available on Windows.")
    source = ctypes.create_string_buffer(data)
    source_blob = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    result_blob = _DataBlob()
    crypt = ctypes.windll.crypt32
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source_blob), None, None, None, None,
                                      0, ctypes.byref(result_blob))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source_blob), "SPX Reconciliation email token",
                                    None, None, None, 0, ctypes.byref(result_blob))
    if not ok:
        raise RuntimeError("Windows could not securely process the email token.")
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result_blob.pbData)


class EmailAccountRepository:
    def __init__(self, database):
        self.database = database

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as db:
            rows = db.execute("SELECT id,provider,email,connected_at FROM email_accounts WHERE provider=? ORDER BY connected_at", (GOOGLE,)).fetchall()
        return [dict(row) for row in rows]

    def get(self, account_id: str) -> dict[str, Any] | None:
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM email_accounts WHERE id=? AND provider=?",
                             (account_id, GOOGLE)).fetchone()
        if row is None:
            return None
        account = dict(row)
        account["access_token"] = _dpapi(bytes(account["access_token"]), decrypt=True).decode("utf-8")
        account["refresh_token"] = _dpapi(bytes(account["refresh_token"]), decrypt=True).decode("utf-8")
        return account

    def upsert(self, provider: str, email_address: str, tokens: dict[str, Any], scope: str) -> str:
        if provider != GOOGLE:
            raise ValueError("Only Google email accounts are supported.")
        now = _now()
        account_id = str(uuid.uuid4())
        access_token = _dpapi(str(tokens["access_token"]).encode(), decrypt=False)
        refresh_token = _dpapi(str(tokens.get("refresh_token", "")).encode(), decrypt=False)
        expires_at = _utc_from_seconds(tokens.get("expires_in", 3600))
        with self.database.connect() as db:
            existing = db.execute("SELECT id,refresh_token FROM email_accounts WHERE provider=? AND email=?",
                                  (provider, email_address)).fetchone()
            if existing:
                account_id = existing["id"]
                if not tokens.get("refresh_token"):
                    refresh_token = bytes(existing["refresh_token"])
                db.execute("""UPDATE email_accounts SET access_token=?,refresh_token=?,token_expires_at=?,
                    scope=?,updated_at=? WHERE id=?""",
                           (access_token, refresh_token, expires_at, scope, now, account_id))
            else:
                db.execute("""INSERT INTO email_accounts(id,provider,email,access_token,refresh_token,
                    token_expires_at,scope,connected_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                           (account_id, provider, email_address, access_token, refresh_token,
                            expires_at, scope, now, now))
        return account_id

    def update_tokens(self, account_id: str, tokens: dict[str, Any]) -> None:
        with self.database.connect() as db:
            row = db.execute("SELECT refresh_token FROM email_accounts WHERE id=?", (account_id,)).fetchone()
            if row is None:
                raise RuntimeError("Email account is no longer connected.")
            refresh_token = (_dpapi(str(tokens["refresh_token"]).encode(), decrypt=False)
                             if tokens.get("refresh_token") else bytes(row["refresh_token"]))
            db.execute("UPDATE email_accounts SET access_token=?,refresh_token=?,token_expires_at=?,updated_at=? WHERE id=?",
                       (_dpapi(str(tokens["access_token"]).encode(), decrypt=False), refresh_token,
                        _utc_from_seconds(tokens.get("expires_in", 3600)), _now(), account_id))

    def disconnect(self, account_id: str) -> None:
        with self.database.connect() as db:
            db.execute("DELETE FROM email_accounts WHERE id=?", (account_id,))

    def add_history(self, account_id: str | None, template_id: str | None, recipients: list[str],
                    subject: str, status: str, error: str | None = None) -> None:
        with self.database.connect() as db:
            db.execute("""INSERT INTO email_send_history(id,email_account_id,template_id,recipients,
                subject,status,sent_at,error_message) VALUES(?,?,?,?,?,?,?,?)""",
                       (str(uuid.uuid4()), account_id, template_id, json.dumps(recipients),
                        subject, status, _now(), error))

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connect() as db:
            rows = db.execute("""SELECT h.*,a.email account_email FROM email_send_history h
                LEFT JOIN email_accounts a ON a.id=h.email_account_id ORDER BY h.sent_at DESC LIMIT ?""",
                              (limit,)).fetchall()
        return [dict(row) for row in rows]

    def recipient_history(self, send_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as db:
            rows = db.execute("""SELECT recipient_group,recipient_type,email,status,error_message,sent_at
                FROM email_send_recipient_log WHERE send_history_id=?
                ORDER BY recipient_group,recipient_type,email""", (send_id,)).fetchall()
        return [dict(row) for row in rows]

    def add_batch_history(self, workspace_id: str, account_id: str, template_id: str, subject: str,
                          total_records: int, attachment_name: str,
                          groups: list[dict[str, list[str]]], results: list[dict[str, Any]]) -> str:
        send_id, sent_at = str(uuid.uuid4()), _now()
        recipients = [email for group in groups for key in ("to", "cc", "bcc") for email in group[key]]
        success = sum(result["status"] == "SENT" for result in results)
        failed = len(results) - success
        status = "SENT" if not failed else "FAILED" if not success else "PARTIAL"
        with self.database.connect() as db:
            db.execute("""INSERT INTO email_send_history(
                id,email_account_id,template_id,recipients,subject,status,sent_at,error_message,
                workspace_id,total_records,attachment_name,total_recipients,success_count,failed_count
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (send_id, account_id, template_id, json.dumps(recipients), subject, status,
                        sent_at, None, workspace_id, total_records, attachment_name, len(recipients),
                        success, failed))
            for group_index, result in enumerate(results, 1):
                for recipient_type in ("to", "cc", "bcc"):
                    for email_address in result[recipient_type]:
                        db.execute("""INSERT INTO email_send_recipient_log(
                            id,send_history_id,recipient_group,recipient_type,email,status,error_message,sent_at
                        ) VALUES(?,?,?,?,?,?,?,?)""",
                                   (str(uuid.uuid4()), send_id, group_index, recipient_type.upper(),
                                    email_address, result["status"], result["error"], sent_at))
        return send_id


class EmailRecipientGroupRepository:
    def __init__(self, database):
        self.database = database

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as db:
            rows = db.execute("SELECT * FROM email_recipient_groups ORDER BY name COLLATE NOCASE").fetchall()
        return [{**dict(row), "to": json.loads(row["to_json"]),
                 "cc": json.loads(row["cc_json"]), "bcc": json.loads(row["bcc_json"])} for row in rows]

    def save(self, name: str, to: list[str], cc: list[str], bcc: list[str]) -> None:
        with self.database.connect() as db:
            db.execute("""INSERT INTO email_recipient_groups(id,name,to_json,cc_json,bcc_json,updated_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                to_json=excluded.to_json,cc_json=excluded.cc_json,bcc_json=excluded.bcc_json,
                updated_at=excluded.updated_at""",
                       (str(uuid.uuid4()), name.strip(), json.dumps(to), json.dumps(cc), json.dumps(bcc), _now()))

    def delete(self, name: str) -> None:
        with self.database.connect() as db:
            db.execute("DELETE FROM email_recipient_groups WHERE name=?", (name,))


class EmailProviderService:
    """Google OAuth lifecycle and Gmail send interface."""

    def __init__(self, repository: EmailAccountRepository):
        self.repository = repository

    @staticmethod
    def load_config() -> dict[str, str]:
        env = dict(os.environ)
        candidates = (Path(__file__).resolve().parents[2] / ".env", Path.cwd() / ".env")
        for env_path in dict.fromkeys(candidates):
            if not env_path.exists():
                continue
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip("\"'"))
        return {
            "google_client_id": env.get("GOOGLE_CLIENT_ID", ""),
            "google_client_secret": env.get("GOOGLE_CLIENT_SECRET", ""),
            "redirect_url": env.get("OAUTH_REDIRECT_URL", "http://localhost:8765/callback"),
        }

    def connect(self, provider: str, on_status: Callable[[str], None] | None = None) -> str:
        if provider != GOOGLE:
            raise ValueError("Only Google email accounts are supported.")
        config = self.load_config()
        client_id = config["google_client_id"]
        client_secret = config["google_client_secret"]
        if not client_id:
            raise RuntimeError("GOOGLE_CLIENT_ID is not configured. Add OAuth credentials to the developer .env file.")
        redirect = urllib.parse.urlparse(config["redirect_url"])
        if redirect.scheme != "http" or redirect.hostname not in {"localhost", "127.0.0.1"} or not redirect.port:
            raise RuntimeError("OAUTH_REDIRECT_URL must be a localhost URL with an explicit port, such as http://localhost:8765/callback.")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(__import__("hashlib").sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        callback = {"code": None, "error": None}

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path != redirect.path or not secrets.compare_digest(query.get("state", [""])[0], state):
                    self.send_error(400)
                    return
                callback["code"] = query.get("code", [None])[0]
                callback["error"] = query.get("error", [None])[0]
                body = ("<html><meta charset='utf-8'><title>SPX Email</title>"
                        "<body style='font:16px Segoe UI;text-align:center;padding:60px'>"
                        "You can close this window and return to SPX Reconciliation.</body></html>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        try:
            server = http.server.HTTPServer((redirect.hostname, redirect.port), CallbackHandler)
        except OSError as exc:
            raise RuntimeError("The local OAuth callback port is unavailable. Close other app instances and try again.") from exc
        server.timeout = 180
        scopes = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email openid"
        authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
        token_url = "https://oauth2.googleapis.com/token"
        extra = {"access_type": "offline", "prompt": "consent"}
        params = {"client_id": client_id, "redirect_uri": config["redirect_url"], "response_type": "code",
                  "scope": scopes, "state": state, "code_challenge": challenge,
                  "code_challenge_method": "S256", **extra}
        try:
            import webbrowser
            if not webbrowser.open(authorization_url + "?" + urllib.parse.urlencode(params)):
                raise RuntimeError("Could not open the sign-in page in your browser.")
            if on_status:
                on_status("Đã mở trang đăng nhập. Hãy hoàn tất xác thực trong trình duyệt; SPX đang chờ phản hồi…")
            server.handle_request()
        finally:
            server.server_close()
        if callback["error"]:
            raise RuntimeError("Nhà cung cấp OAuth đã từ chối hoặc hủy xác thực. Hãy thử kết nối lại.")
        if not callback["code"]:
            raise RuntimeError(
                "Không nhận được phản hồi xác thực sau 3 phút. Hãy kiểm tra Redirect URI "
                "của OAuth phải khớp chính xác với OAUTH_REDIRECT_URL trong file .env, "
                "rồi thử kết nối lại."
            )
        form = {"client_id": client_id, "grant_type": "authorization_code", "code": callback["code"],
                "redirect_uri": config["redirect_url"], "code_verifier": verifier}
        if client_secret:
            form["client_secret"] = client_secret
        tokens = _request(token_url, data=urllib.parse.urlencode(form).encode(),
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        if not tokens.get("access_token"):
            raise RuntimeError("Authorization did not return an access token.")
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        identity = _request("https://openidconnect.googleapis.com/v1/userinfo", headers=headers)
        email_address = identity.get("email")
        if not email_address:
            raise RuntimeError("The provider did not return an email address.")
        self.repository.upsert(provider, email_address, tokens, scopes)
        return email_address

    def _valid_access_token(self, account: dict[str, Any]) -> str:
        expiry = account.get("token_expires_at") or ""
        try:
            expired = datetime.fromisoformat(expiry) <= datetime.now(timezone.utc) + timedelta(seconds=60)
        except ValueError:
            expired = True
        if not expired:
            return account["access_token"]
        if not account.get("refresh_token"):
            raise RuntimeError("Email account is no longer connected. Please reconnect it.")
        config = self.load_config()
        provider = account["provider"]
        if provider != GOOGLE:
            raise RuntimeError("Only Google email accounts are supported. Connect a Google account.")
        url, client_id, client_secret = "https://oauth2.googleapis.com/token", config["google_client_id"], config["google_client_secret"]
        form = {"client_id": client_id, "grant_type": "refresh_token", "refresh_token": account["refresh_token"]}
        if client_secret:
            form["client_secret"] = client_secret
        try:
            tokens = _request(url, data=urllib.parse.urlencode(form).encode(),
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
        except RuntimeError as exc:
            raise RuntimeError("Email account is no longer connected. Please reconnect it.") from exc
        if not tokens.get("access_token"):
            raise RuntimeError("Email account is no longer connected. Please reconnect it.")
        self.repository.update_tokens(account["id"], tokens)
        return tokens["access_token"]

    def send(self, account_id: str, *, to: list[str], cc: list[str], bcc: list[str],
             subject: str, html_body: str, attachment_name: str | None = None,
             attachment: bytes | None = None) -> None:
        account = self.repository.get(account_id)
        if not account:
            raise RuntimeError("Email account is no longer connected. Please reconnect it.")
        if account["provider"] != GOOGLE:
            raise RuntimeError("Only Google email accounts are supported. Connect a Google account.")
        access_token = self._valid_access_token(account)
        message = EmailMessage()
        message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)
        message["Subject"] = subject
        message.set_content("This email contains an HTML message. Please use an HTML-capable email client.")
        message.add_alternative(html_body, subtype="html")
        if attachment_name and attachment is not None:
            message.add_attachment(attachment, maintype="application",
                                   subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   filename=attachment_name)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
        _request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                 data=json.dumps({"raw": raw}).encode(),
                 headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})


def parse_recipients(value: str) -> list[str]:
    import re
    parts = [item.strip() for item in value.replace(";", ",").replace("\n", ",").split(",") if item.strip()]
    valid = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$", re.I)
    if any(not valid.fullmatch(address) for address in parts):
        raise ValueError("Please check the email addresses and try again.")
    normalized = list(dict.fromkeys(item.lower() for item in parts))
    return normalized

