"""Persistence and safe variable handling for reusable email templates."""
from __future__ import annotations

import html
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_reconciliation_summary(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Build email template values for TO/order totals and trip breakdowns."""
    groups: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"tos": set(), "orders": set()}
    )
    all_tos: set[str] = set()
    all_orders: set[str] = set()

    for index, row in enumerate(rows, 1):
        trip = str(row.get("line_haul_trip_number") or "").strip() or "(Không có mã chuyến)"
        date_value = row.get("create_time") or row.get("complete_time") or row.get("driver_scan_time")
        date_label = _format_summary_date(date_value)
        key = (trip, date_label)
        to_number = str(row.get("to_number") or "").strip()
        tracking_number = str(row.get("spx_tracking_number") or "").strip()
        # Distinct IDs avoid counting repeated Excel rows more than once.
        to_id = to_number or f"__missing_to_{index}"
        order_id = tracking_number or f"__missing_order_{index}"
        groups[key]["tos"].add(to_id)
        groups[key]["orders"].add(order_id)
        all_tos.add(to_id)
        all_orders.add(order_id)

    lines = []
    for (trip, date_label), counts in sorted(groups.items()):
        lines.extend((
            f"LH_Trip: {trip}",
            f"Thời gian: {date_label}",
            f"Số lượng TO: {len(counts['tos']):,}",
            f"Số lượng Order: {len(counts['orders']):,}",
            "",
        ))
    if lines:
        lines.extend(("---", ""))
    return {
        "trip_summary": "\n".join(lines).rstrip(),
        "total_to_count": f"{len(all_tos):,}",
        "total_order_count": f"{len(all_orders):,}",
    }


def _format_summary_date(value: Any) -> str:
    if value in (None, ""):
        return "—"
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return raw[:10]


class EmailTemplateRepository:
    """SQLite repository backed by the application's shared Database."""

    def __init__(self, database):
        self.database = database

    def get_all(self) -> list[dict[str, Any]]:
        with self.database.connect() as db:
            rows = db.execute(
                "SELECT * FROM email_templates ORDER BY updated_at DESC, name COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, template_id: str) -> dict[str, Any] | None:
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM email_templates WHERE id=?", (template_id,)).fetchone()
        return dict(row) if row else None

    def create(self, name: str, subject: str, html_content: str) -> str:
        template_id, now = str(uuid.uuid4()), _now()
        with self.database.connect() as db:
            db.execute(
                "INSERT INTO email_templates(id,name,subject,html_content,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (template_id, name.strip(), subject.strip(), html_content, now, now),
            )
        return template_id

    def update(self, template_id: str, name: str, subject: str, html_content: str) -> None:
        with self.database.connect() as db:
            db.execute(
                "UPDATE email_templates SET name=?,subject=?,html_content=?,updated_at=? WHERE id=?",
                (name.strip(), subject.strip(), html_content, _now(), template_id),
            )

    def delete(self, template_id: str) -> None:
        with self.database.connect() as db:
            db.execute("DELETE FROM email_templates WHERE id=?", (template_id,))


class TemplateVariableResolver:
    """Resolve known ``{variable}`` tokens while leaving unknown tokens intact."""

    TOKEN_PATTERN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}|\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    @classmethod
    def extract_variables(cls, content: str) -> list[str]:
        return list(dict.fromkeys(next(value for value in match.groups() if value)
                                  for match in cls.TOKEN_PATTERN.finditer(content or "")))

    @classmethod
    def resolve(cls, content: str, values: dict[str, Any], *, escape_html: bool = True) -> str:
        def replace(match: re.Match[str]) -> str:
            key = next(value for value in match.groups() if value)
            if key not in values:
                return match.group(0)
            value = str(values[key])
            return html.escape(value, quote=True) if escape_html else value

        return cls.TOKEN_PATTERN.sub(replace, content or "")


def sanitize_preview_html(content: str) -> str:
    """Remove active or embedded content before presenting a template preview."""
    safe = content or ""
    safe = re.sub(
        r"<\s*(script|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
        "", safe, flags=re.IGNORECASE | re.DOTALL,
    )
    safe = re.sub(
        r"<\s*(script|iframe|object|embed)\b[^>]*/?\s*>",
        "", safe, flags=re.IGNORECASE,
    )
    safe = re.sub(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", safe, flags=re.IGNORECASE)
    safe = re.sub(r"javascript\s*:", "", safe, flags=re.IGNORECASE)
    safe = re.sub(r"@import\s+[^;]+;?", "", safe, flags=re.IGNORECASE)
    safe = re.sub(r"url\(\s*(['\"]?)\s*javascript:[^)]*\)", "none", safe, flags=re.IGNORECASE)
    return safe
