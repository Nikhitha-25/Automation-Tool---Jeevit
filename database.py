
import csv
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DEFAULT_DB_PATH = DATA_DIR / "leads.db"
DEFAULT_CSV_PATH = DATA_DIR / "existing_leads.csv"


class LeadDatabase:
    """SQLite storage for the JEEVIT Lead Automation project."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    # CONNECTION AND INITIALIZATION
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        """Create the required tables and indexes."""

        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    email_key TEXT NOT NULL DEFAULT '',
                    name_key TEXT NOT NULL DEFAULT '',
                    company TEXT NOT NULL DEFAULT '',
                    company_key TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'website',
                    message TEXT NOT NULL DEFAULT '',
                    tag TEXT,
                    draft_reply TEXT,
                    validation_status TEXT NOT NULL DEFAULT 'valid',
                    processing_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_leads_email_key
                    ON leads(email_key);

                CREATE INDEX IF NOT EXISTS idx_leads_name_company
                    ON leads(name_key, company_key);

                CREATE TABLE IF NOT EXISTS enquiries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id TEXT UNIQUE,
                    lead_db_id INTEGER NOT NULL,
                    original_message TEXT NOT NULL DEFAULT '',
                    received_at TEXT,
                    status TEXT NOT NULL DEFAULT 'received',
                    tag TEXT,
                    draft_reply TEXT,
                    raw_json TEXT,
                    notification_status TEXT NOT NULL DEFAULT 'not_required',
                    notification_error TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lead_db_id)
                        REFERENCES leads(id)
                );

                CREATE INDEX IF NOT EXISTS idx_enquiries_lead
                    ON enquiries(lead_db_id);

                CREATE TABLE IF NOT EXISTS processing_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id TEXT,
                    lead_db_id INTEGER,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (lead_db_id)
                        REFERENCES leads(id)
                );
            """)

            # Safe schema migration for databases created before notification
            # tracking was added. Existing Hot enquiries are eligible for retry.
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(enquiries)").fetchall()
            }
            if "notification_status" not in columns:
                conn.execute(
                    "ALTER TABLE enquiries ADD COLUMN notification_status "
                    "TEXT NOT NULL DEFAULT 'not_required'"
                )
            if "notification_error" not in columns:
                conn.execute(
                    "ALTER TABLE enquiries ADD COLUMN notification_error TEXT"
                )
            conn.execute(
                "UPDATE enquiries SET notification_status = 'pending' "
                "WHERE tag = 'Hot' AND notification_status = 'not_required'"
            )

    # NORMALIZATION HELPERS
    @staticmethod
    def _value(record: dict[str, Any], key: str) -> str:
        value = record.get(key, "")
        return "" if value is None else str(value).strip()

    @staticmethod
    def _email_key(email: str) -> str:
        return email.strip().casefold()

    @staticmethod
    def _name_key(name: str) -> str:
        return " ".join(name.casefold().split())

    @staticmethod
    def _company_key(company: str) -> str:
        company = unicodedata.normalize(
            "NFKD", company.casefold().replace("&", " and ")
        )

        company = "".join(
            char for char in company
            if not unicodedata.combining(char)
        )

        company = re.sub(r"[^\w\s]", " ", company)
        return " ".join(company.split())

    def _keys(
        self, lead: dict[str, Any]
    ) -> tuple[str, str, str]:
        """
        Use the comparison keys produced by cleaner.py when available.
        Otherwise, generate them here.
        """
        email = self._value(lead, "email")
        name = self._value(lead, "name")
        company = self._value(lead, "company")

        return (
            self._value(lead, "email_key")
            or self._email_key(email),

            self._value(lead, "name_key")
            or self._name_key(name),

            self._value(lead, "company_key")
            or self._company_key(company),
        )

    # IMPORT EXISTING CSV
    def import_existing_csv(
        self,
        csv_path: str | Path = DEFAULT_CSV_PATH,
    ) -> int:
        """
        Import the existing leads CSV.

        Returns the number of records newly imported.
        Re-running this method does not duplicate records
        with the same lead_id.
        """

        path = Path(csv_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Existing leads CSV not found: {path}"
            )

        imported = 0

        with path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)

            required = {
                "lead_id", "name", "email", "company"
            }

            if not reader.fieldnames or not required.issubset(
                set(reader.fieldnames)
            ):
                raise ValueError(
                    f"CSV must contain columns: {sorted(required)}"
                )

            with self._connect() as conn:
                for row in reader:
                    lead_id = self._value(row, "lead_id")

                    if not lead_id:
                        raise ValueError(
                            "An existing CSV record has no lead_id."
                        )

                    name = self._value(row, "name")
                    email = self._value(row, "email")
                    company = self._value(row, "company")

                    email_key = self._email_key(email)
                    name_key = self._name_key(name)
                    company_key = self._company_key(company)

                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO leads (
                            lead_id, name, email, email_key,
                            name_key, company, company_key,
                            source, tag, created_at,
                            processing_status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lead_id,
                            name,
                            email,
                            email_key,
                            name_key,
                            company,
                            company_key,
                            self._value(row, "source") or "website",
                            self._value(row, "tag") or None,
                            self._value(row, "created_at") or None,
                            "existing",
                        ),
                    )

                    imported += cursor.rowcount

        return imported

    # DUPLICATE DETECTION
    def find_duplicate(
        self,
        lead: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Match by email first.
        If email is unavailable, use name + company.

        This method checks existing database records.
        """

        email_key, name_key, company_key = self._keys(lead)

        with self._connect() as conn:
            row = None

            if email_key:
                row = conn.execute(
                    """
                    SELECT * FROM leads
                    WHERE email_key = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (email_key,),
                ).fetchone()

            if row is None and name_key and company_key:
                row = conn.execute(
                    """
                    SELECT * FROM leads
                    WHERE name_key = ?
                      AND company_key = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (name_key, company_key),
                ).fetchone()

            return dict(row) if row else None


    # ERROR LOGGING
    def save_error(
        self,
        submission_id: str | None,
        error_type: str,
        error_message: str,
        lead_db_id: int | None = None,
    ) -> None:
        """Save a validation or processing error."""

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO processing_errors (
                    submission_id,
                    lead_db_id,
                    error_type,
                    error_message
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    submission_id,
                    lead_db_id,
                    error_type,
                    error_message,
                ),
            )


    # SAVE INCOMING LEADS
    def save_incoming_lead(
        self,
        lead: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Save a cleaned lead.

        New customer:
            Create a lead and an enquiry.

        Existing customer:
            Preserve the new enquiry without creating
            another customer record.

        Repeated submission ID:
            Do not process the same submission twice.
        """

        submission_id = self._value(lead, "id") or None
        message = self._value(lead, "message")
        received_at = self._value(lead, "received_at") or None

        errors = lead.get("validation_errors", [])

        if not isinstance(errors, list):
            errors = [str(errors)]

        raw_record = lead.get("raw_record", lead)
        raw_json = json.dumps(
            raw_record,
            ensure_ascii=False,
            default=str,
        )

        email_key, name_key, company_key = self._keys(lead)

        # Validate before inserting.
        with self._connect() as conn:
            if submission_id:
                previous = conn.execute(
                    """
                    SELECT status, lead_db_id
                    FROM enquiries
                    WHERE submission_id = ?
                    """,
                    (submission_id,),
                ).fetchone()

                if previous:
                    return {
                        "status": "already_processed",
                        "lead_db_id": previous["lead_db_id"],
                        "submission_id": submission_id,
                    }

            # Start a write transaction so concurrent runs
            # cannot both insert the same customer unnoticed.
            conn.execute("BEGIN IMMEDIATE")

            duplicate = None

            # 1. Prefer an exact normalized email match on the customer record.
            if email_key:
                duplicate = conn.execute(
                    """
                    SELECT * FROM leads
                    WHERE email_key = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (email_key,),
                ).fetchone()

            # 2. Also check email addresses from earlier incoming submissions.
            # A previous enquiry may have been linked to a customer record
            # whose main email field is different.
            if duplicate is None and email_key:
                previous_enquiries = conn.execute(
                    """
                    SELECT e.raw_json, e.lead_db_id
                    FROM enquiries AS e
                    ORDER BY e.id
                    """
                ).fetchall()

                for previous in previous_enquiries:
                    try:
                        previous_raw = json.loads(
                            previous["raw_json"] or "{}"
                        )
                    except (TypeError, json.JSONDecodeError):
                        continue

                    previous_email = self._email_key(
                        str(previous_raw.get("email") or "")
                    )

                    if previous_email and previous_email == email_key:
                        duplicate = conn.execute(
                            "SELECT * FROM leads WHERE id = ?",
                            (previous["lead_db_id"],),
                        ).fetchone()
                        if duplicate is not None:
                            break

            # 3. If email did not identify a match, use normalized name + company.
            if duplicate is None and name_key and company_key:
                duplicate = conn.execute(
                    """
                    SELECT * FROM leads
                    WHERE name_key = ?
                      AND company_key = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (name_key, company_key),
                ).fetchone()

            if duplicate is not None:
                lead_db_id = duplicate["id"]
                status = "duplicate"

            else:
                cursor = conn.execute(
                    """
                    INSERT INTO leads (
                        lead_id, name, email, email_key,
                        name_key, company, company_key,
                        source, message,
                        validation_status, processing_status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        submission_id,
                        self._value(lead, "name"),
                        self._value(lead, "email"),
                        email_key,
                        name_key,
                        self._value(lead, "company"),
                        company_key,
                        "website",
                        message,
                        self._value(lead, "validation_status")
                        or "valid",
                        "needs_review" if errors else "pending",
                        received_at,
                    ),
                )

                lead_db_id = cursor.lastrowid
                status = "needs_review" if errors else "new"

            # Always preserve the individual submission, including
            # a duplicate's new message.
            conn.execute(
                """
                INSERT INTO enquiries (
                    submission_id, lead_db_id, original_message,
                    received_at, status, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    lead_db_id,
                    message,
                    received_at,
                    status,
                    raw_json,
                ),
            )

            for error in errors:
                conn.execute(
                    """
                    INSERT INTO processing_errors (
                        submission_id, lead_db_id,
                        error_type, error_message
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        submission_id,
                        lead_db_id,
                        "validation_error",
                        str(error),
                    ),
                )

            return {
                "status": status,
                "lead_db_id": lead_db_id,
                "submission_id": submission_id,
                "duplicate_of": (
                    duplicate["lead_id"] if duplicate else None
                ),
            }

    
    # SAVE LLM CLASSIFICATION AND REPLY
    def update_classification(
        self,
        lead_db_id: int,
        tag: str,
        draft_reply: str,
        submission_id: str | None = None,
    ) -> None:
        """
        Save a valid LLM classification and draft.

        When submission_id is supplied, also save the result
        on that individual enquiry.
        """

        if tag not in {"Hot", "Warm", "Cold"}:
            raise ValueError(
                "Classification must be Hot, Warm, or Cold."
            )

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE leads
                SET tag = ?,
                    draft_reply = ?,
                    processing_status = 'processed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (tag, draft_reply, lead_db_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Lead database ID {lead_db_id} was not found."
                )

            if submission_id:
                conn.execute(
                    """
                    UPDATE enquiries
                    SET tag = ?,
                        draft_reply = ?,
                        status = CASE
                            WHEN status IN ('duplicate', 'needs_review')
                            THEN status
                            ELSE 'processed'
                        END,
                        notification_status = CASE
                            WHEN ? = 'Hot' THEN 'pending'
                            ELSE 'not_required'
                        END,
                        notification_error = NULL
                    WHERE submission_id = ?
                      AND lead_db_id = ?
                    """,
                    (tag, draft_reply, tag, submission_id, lead_db_id),
                )

    # HOT-LEAD NOTIFICATION TRACKING
    def get_pending_hot_notifications(self) -> list[dict[str, Any]]:
        """Return Hot enquiries whose email has not been marked sent."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*, l.name AS lead_name, l.email AS lead_email,
                       l.company AS lead_company
                FROM enquiries e
                JOIN leads l ON l.id = e.lead_db_id
                WHERE e.tag = 'Hot'
                  AND e.notification_status IN ('pending', 'failed')
                ORDER BY e.id
                """
            ).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    raw = json.loads(item.get("raw_json") or "{}")
                except (TypeError, json.JSONDecodeError):
                    raw = {}
                item["lead"] = {
                    "id": item.get("submission_id") or "N/A",
                    "name": raw.get("name") or item.get("lead_name") or "Unknown",
                    "email": raw.get("email") or item.get("lead_email") or "N/A",
                    "company": raw.get("company") or item.get("lead_company") or "Unknown company",
                    "message": item.get("original_message") or "N/A",
                }
                item["classification"] = {
                    "tag": item.get("tag"),
                    "reason": "Hot lead notification retry from saved classification.",
                    "draft_reply": item.get("draft_reply") or "",
                }
                results.append(item)
            return results

    def update_notification_status(
        self, submission_id: str, status: str, error_message: str | None = None
    ) -> None:
        """Persist notification outcome for an enquiry."""
        if status not in {"pending", "sent", "failed", "not_required"}:
            raise ValueError("Invalid notification status.")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE enquiries
                SET notification_status = ?, notification_error = ?
                WHERE submission_id = ?
                """,
                (status, error_message, submission_id),
            )


    # READ DATA
    def get_leads(self) -> list[dict[str, Any]]:
        """Return all customer records."""

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM leads ORDER BY id"
            ).fetchall()

            return [dict(row) for row in rows]

    def get_enquiries(
        self,
        lead_db_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return all enquiries, optionally for one customer."""

        with self._connect() as conn:
            if lead_db_id is None:
                rows = conn.execute(
                    "SELECT * FROM enquiries ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM enquiries
                    WHERE lead_db_id = ?
                    ORDER BY id
                    """,
                    (lead_db_id,),
                ).fetchall()

            return [dict(row) for row in rows]

    def get_errors(
        self,
        unresolved_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return processing errors for review."""

        with self._connect() as conn:
            if unresolved_only:
                rows = conn.execute(
                    """
                    SELECT * FROM processing_errors
                    WHERE resolved = 0
                    ORDER BY id
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM processing_errors
                    ORDER BY id
                    """
                ).fetchall()

            return [dict(row) for row in rows]

    def mark_error_resolved(self, error_id: int) -> None:
        """Mark an error as resolved after review."""

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE processing_errors
                SET resolved = 1
                WHERE id = ?
                """,
                (error_id,),
            )
