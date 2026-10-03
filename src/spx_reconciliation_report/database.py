"""SQLite storage and parameterized workspace data queries."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .columns import COLUMNS, COLUMN_BY_FIELD, DEFAULT_FIELDS, SEARCH_FIELDS


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "null")
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


class Database:
    VERSION = 5

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def initialize(self) -> None:
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > self.VERSION:
                raise RuntimeError("Database version is newer than this application supports.")
            if version == 0:
                fields = ",".join(f"{c.field} {'REAL' if c.kind == 'number' else 'TEXT'}" for c in COLUMNS)
                db.executescript(f"""
                    CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                    CREATE TABLE import_files(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,original_filename TEXT NOT NULL,stored_file_path TEXT,sheet_name TEXT NOT NULL,row_count INTEGER NOT NULL DEFAULT 0,imported_at TEXT NOT NULL,FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE);
                    CREATE TABLE main_data(id INTEGER PRIMARY KEY AUTOINCREMENT,workspace_id TEXT NOT NULL,import_file_id TEXT NOT NULL,{fields},FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,FOREIGN KEY(import_file_id) REFERENCES import_files(id) ON DELETE CASCADE);
                    CREATE TABLE workspace_settings(workspace_id TEXT PRIMARY KEY,visible_columns_json TEXT,column_order_json TEXT,column_widths_json TEXT,filters_json TEXT,updated_at TEXT NOT NULL,FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE);
                    CREATE INDEX idx_main_data_workspace ON main_data(workspace_id);
                    CREATE INDEX idx_main_data_receive_status ON main_data(workspace_id,receive_status);
                    CREATE INDEX idx_main_data_current_station ON main_data(workspace_id,current_station);
                    CREATE INDEX idx_main_data_create_time ON main_data(workspace_id,create_time);
                    CREATE INDEX idx_main_data_receiver_id ON main_data(workspace_id,receiver_id);
                    CREATE INDEX idx_main_data_trip_number ON main_data(workspace_id,line_haul_trip_number);
                    PRAGMA user_version=1;
                """)
                version = 1
            if version < 2:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS email_templates(
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        html_content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_email_templates_updated
                        ON email_templates(updated_at DESC);
                    PRAGMA user_version=2;
                """)
                version = 2
            if version < 3:
                # Add the newly supported source columns to existing databases.
                # They are text fields to preserve IDs and source values exactly.
                existing = {row[1] for row in db.execute("PRAGMA table_info(main_data)")}
                for field in (
                    "to_number", "to_high_value", "spx_tracking_number",
                    "order_high_value", "to_status", "high_value", "sender_id",
                ):
                    if field not in existing:
                        db.execute(f"ALTER TABLE main_data ADD COLUMN {field} TEXT")
                db.execute("PRAGMA user_version=3")
                version = 3
            if version < 4:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS email_accounts(
                        id TEXT PRIMARY KEY, provider TEXT NOT NULL, email TEXT NOT NULL,
                        access_token BLOB NOT NULL, refresh_token BLOB NOT NULL,
                        token_expires_at TEXT, scope TEXT, connected_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS email_send_history(
                        id TEXT PRIMARY KEY, email_account_id TEXT, template_id TEXT,
                        recipients TEXT NOT NULL, subject TEXT NOT NULL,
                        status TEXT NOT NULL, sent_at TEXT NOT NULL, error_message TEXT,
                        FOREIGN KEY(email_account_id) REFERENCES email_accounts(id) ON DELETE SET NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_email_history_sent_at
                        ON email_send_history(sent_at DESC);
                    PRAGMA user_version=4;
                """)
                version = 4
            if version < 5:
                db.executescript("""
                    ALTER TABLE email_send_history ADD COLUMN workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL;
                    ALTER TABLE email_send_history ADD COLUMN total_records INTEGER NOT NULL DEFAULT 0;
                    ALTER TABLE email_send_history ADD COLUMN attachment_name TEXT;
                    ALTER TABLE email_send_history ADD COLUMN total_recipients INTEGER NOT NULL DEFAULT 0;
                    ALTER TABLE email_send_history ADD COLUMN success_count INTEGER NOT NULL DEFAULT 0;
                    ALTER TABLE email_send_history ADD COLUMN failed_count INTEGER NOT NULL DEFAULT 0;
                    CREATE TABLE email_send_recipient_log(
                        id TEXT PRIMARY KEY,
                        send_history_id TEXT NOT NULL,
                        recipient_group INTEGER NOT NULL,
                        recipient_type TEXT NOT NULL,
                        email TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        sent_at TEXT NOT NULL,
                        FOREIGN KEY(send_history_id) REFERENCES email_send_history(id) ON DELETE CASCADE
                    );
                    CREATE INDEX idx_email_recipient_log_history ON email_send_recipient_log(send_history_id);
                    CREATE TABLE email_recipient_groups(
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        to_json TEXT NOT NULL,
                        cc_json TEXT NOT NULL,
                        bcc_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    PRAGMA user_version=5;
                """)

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""SELECT w.*,COALESCE(SUM(i.row_count),0) total_records,MAX(i.imported_at) last_imported_at,
                (SELECT original_filename FROM import_files f WHERE f.workspace_id=w.id ORDER BY imported_at DESC LIMIT 1) last_file_name
                FROM workspaces w LEFT JOIN import_files i ON i.workspace_id=w.id GROUP BY w.id ORDER BY w.updated_at DESC""").fetchall()
            return [dict(r) for r in rows]

    def create_workspace(self, name: str, description: str = "") -> str:
        wid, now = str(uuid.uuid4()), _now()
        with self.connect() as db:
            db.execute("INSERT INTO workspaces VALUES(?,?,?,?,?)", (wid, name.strip(), description.strip() or None, now, now))
            db.execute("INSERT INTO workspace_settings VALUES(?,?,?,?,?,?)", (wid, json.dumps(DEFAULT_FIELDS), json.dumps(DEFAULT_FIELDS), "{}", "{}", now))
        return wid

    def rename_workspace(self, wid: str, name: str, description: str = "") -> None:
        with self.connect() as db:
            db.execute("UPDATE workspaces SET name=?,description=?,updated_at=? WHERE id=?", (name.strip(), description.strip() or None, _now(), wid))

    def delete_workspace(self, wid: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM workspaces WHERE id=?", (wid,))

    def get_settings(self, wid: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM workspace_settings WHERE workspace_id=?", (wid,)).fetchone()
        if row is None:
            return {"visible": DEFAULT_FIELDS.copy(), "order": DEFAULT_FIELDS.copy(), "widths": {}, "filters": {}}
        visible = _load(row["visible_columns_json"], DEFAULT_FIELDS.copy())
        order = _load(row["column_order_json"], DEFAULT_FIELDS.copy())
        # Settings saved by older app versions do not know about newer columns.
        # Include those columns so imported values are visible immediately.
        visible.extend(field for field in DEFAULT_FIELDS if field not in visible)
        order.extend(field for field in DEFAULT_FIELDS if field not in order)
        return {"visible": visible,
                "order": order,
                "widths": _load(row["column_widths_json"], {}), "filters": _load(row["filters_json"], {})}

    def save_settings(self, wid: str, settings: dict[str, Any]) -> None:
        allowed = set(COLUMN_BY_FIELD)
        visible = [v for v in settings.get("visible", DEFAULT_FIELDS) if v in allowed]
        order = [v for v in settings.get("order", DEFAULT_FIELDS) if v in allowed]
        widths = {k: v for k, v in settings.get("widths", {}).items() if k in allowed}
        filters = {k: v for k, v in settings.get("filters", {}).items() if k in allowed}
        with self.connect() as db:
            db.execute("UPDATE workspace_settings SET visible_columns_json=?,column_order_json=?,column_widths_json=?,filters_json=?,updated_at=? WHERE workspace_id=?",
                       (json.dumps(visible), json.dumps(order), json.dumps(widths), json.dumps(filters), _now(), wid))

    @staticmethod
    def _where(wid: str, search: str, filters: dict[str, dict]) -> tuple[str, list[Any]]:
        parts, args = ["workspace_id=?"], [wid]
        if search.strip():
            parts.append("(" + " OR ".join(f"CAST({f} AS TEXT) LIKE ? ESCAPE '\\'" for f in SEARCH_FIELDS) + ")")
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            args.extend([f"%{escaped}%"] * len(SEARCH_FIELDS))
        for field, rule in filters.items():
            if field not in COLUMN_BY_FIELD or not isinstance(rule, dict):
                continue
            op, val = rule.get("op", "contains"), rule.get("value")
            if val is None or val == "":
                continue
            if op == "in" and isinstance(val, list) and val:
                parts.append(f"{field} IN ({','.join('?' for _ in val)})"); args.extend(val)
            elif op == "contains":
                safe = str(val).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                parts.append(f"CAST({field} AS TEXT) LIKE ? ESCAPE '\\'"); args.append(f"%{safe}%")
            elif op in {"equals", "starts", "ends"}:
                safe = str(val).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                parts.append(f"CAST({field} AS TEXT) LIKE ? ESCAPE '\\'" if op != "equals" else f"{field}=?")
                args.append((safe + "%" if op == "starts" else "%" + safe) if op != "equals" else val)
            elif op == "between" and isinstance(val, list) and len(val) == 2:
                parts.append(f"{field} BETWEEN ? AND ?"); args.extend(val)
            elif op in {">", ">=", "<", "<="}:
                parts.append(f"{field} {op} ?"); args.append(val)
        return " AND ".join(parts), args

    def row_count(self, wid: str, search: str = "", filters: dict[str, dict] | None = None) -> int:
        where, args = self._where(wid, search, filters or {})
        with self.connect() as db:
            return int(db.execute(f"SELECT COUNT(*) FROM main_data WHERE {where}", args).fetchone()[0])

    def get_matching_ids(self, wid: str, search: str = "", filters: dict[str, dict] | None = None) -> list[int]:
        where, args = self._where(wid, search, filters or {})
        with self.connect() as db:
            return [int(row[0]) for row in db.execute(
                f"SELECT id FROM main_data WHERE {where} ORDER BY id", args
            ).fetchall()]

    def get_rows_by_ids(self, wid: str, record_ids: Iterable[int],
                        progress: Callable[[int, int], None] | None = None) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(int(value) for value in record_ids))
        if not ids:
            return []
        found: dict[int, dict[str, Any]] = {}
        fields = ",".join(DEFAULT_FIELDS)
        with self.connect() as db:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                rows = db.execute(
                    f"SELECT id,{fields} FROM main_data WHERE workspace_id=? AND id IN ({','.join('?' for _ in chunk)})",
                    (wid, *chunk),
                ).fetchall()
                found.update((int(row["id"]), dict(row)) for row in rows)
                if progress:
                    progress(min(start + len(chunk), len(ids)), len(ids))
        return [found[record_id] for record_id in ids if record_id in found]

    def get_rows(self, wid: str, page: int = 0, page_size: int = 100, search: str = "",
                 filters: dict[str, dict] | None = None, sort_field: str | None = None, sort_direction: str = "asc") -> list[dict[str, Any]]:
        where, args = self._where(wid, search, filters or {})
        order = "main_data.id ASC"
        if sort_field in COLUMN_BY_FIELD and sort_direction.lower() in {"asc", "desc"}:
            order = f"{sort_field} {sort_direction.upper()},main_data.id ASC"
        limit = max(1, min(page_size, 500))
        with self.connect() as db:
            rows = db.execute(f"""
                WITH ranked AS (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY workspace_id ORDER BY id ASC) AS stt
                    FROM main_data WHERE workspace_id=?
                )
                SELECT main_data.id, ranked.stt AS _stt,{','.join(DEFAULT_FIELDS)}
                FROM main_data JOIN ranked ON ranked.id=main_data.id
                WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?
            """, (wid, *args, limit, max(0, page) * limit)).fetchall()
            return [dict(row) for row in rows]

    def distinct_values(self, wid: str, field: str) -> list[str]:
        if field not in COLUMN_BY_FIELD:
            raise ValueError("Unknown column")
        with self.connect() as db:
            return [str(r[0]) for r in db.execute(f"SELECT DISTINCT {field} FROM main_data WHERE workspace_id=? AND {field} IS NOT NULL ORDER BY {field} LIMIT 500", (wid,))]

    def set_import_source(self, import_id: str, source: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE import_files SET stored_file_path=? WHERE id=?", (source, import_id))

    def import_rows(self, wid: str, filename: str, source: str | None, sheet: str,
                    rows: Iterable[dict[str, Any]], progress: Callable[[int], None] | None = None) -> tuple[str, int]:
        import_id, now = str(uuid.uuid4()), _now()
        fields = [c.field for c in COLUMNS]
        sql = f"INSERT INTO main_data(workspace_id,import_file_id,{','.join(fields)}) VALUES({','.join('?' for _ in range(len(fields)+2))})"
        with self.connect() as db:
            db.execute("BEGIN")
            db.execute("INSERT INTO import_files(id,workspace_id,original_filename,stored_file_path,sheet_name,row_count,imported_at) VALUES(?,?,?,?,?,0,?)", (import_id,wid,filename,source,sheet,now))
            batch, inserted = [], 0
            for row in rows:
                batch.append((wid, import_id, *(row.get(f) for f in fields)))
                if len(batch) >= 1000:
                    db.executemany(sql, batch)
                    inserted += len(batch)
                    batch.clear()
                    if progress:
                        progress(inserted)
            if batch:
                db.executemany(sql, batch)
                inserted += len(batch)
                if progress:
                    progress(inserted)
            db.execute("UPDATE import_files SET row_count=? WHERE id=?", (inserted, import_id))
            db.execute("UPDATE workspaces SET updated_at=? WHERE id=?", (now,wid))
        return import_id, inserted
