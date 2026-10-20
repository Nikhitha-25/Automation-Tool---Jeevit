
import csv
import json
from pathlib import Path
from database import LeadDatabase

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "data" / "final_leads_updated.csv"

db = LeadDatabase()
leads = {lead["id"]: lead for lead in db.get_leads()}
enquiries = db.get_enquiries()

columns = [
    "submission_id",
    "received_at",
    "name",
    "email",
    "company",
    "message",
    "status",
    "classification",
    "draft_reply",
    "notification_status",
]

with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=columns)
    writer.writeheader()

    for enquiry in enquiries:
        lead = leads.get(enquiry["lead_db_id"], {})

        try:
            raw = json.loads(enquiry.get("raw_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            raw = {}

        writer.writerow({
            "submission_id": enquiry.get("submission_id", ""),
            "received_at": enquiry.get("received_at", ""),
            "name": raw.get("name") or lead.get("name", ""),
            "email": raw.get("email") or lead.get("email", ""),
            "company": raw.get("company") or lead.get("company", ""),
            "message": enquiry.get("original_message", ""),
            "status": enquiry.get("status", ""),
            "classification": enquiry.get("tag") or "",
            "draft_reply": enquiry.get("draft_reply") or "",
            "notification_status": enquiry.get(
                "notification_status", ""
            ),
        })

print(f"Exported {len(enquiries)} enquiries to: {OUTPUT_FILE}")
