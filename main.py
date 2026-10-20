
import json
from pathlib import Path

from cleaner import LeadCleaner
from database import LeadDatabase
from llm_service import LLMService
from notifier import LeadNotifier


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATH = DATA_DIR / "existing_leads.csv"
INCOMING_PATH = DATA_DIR / "incoming_leads.json"


def main():
    print("=" * 50)
    print("JEEVIT LEAD AUTOMATION")
    print("=" * 50)

    # 1. Check input files
    if not CSV_PATH.exists():
        print(f"ERROR: Existing CSV not found: {CSV_PATH}")
        return

    if not INCOMING_PATH.exists():
        print(f"ERROR: Incoming JSON not found: {INCOMING_PATH}")
        return

    # 2. Initialize database and import existing leads
    db = LeadDatabase()

    imported_count = db.import_existing_csv(CSV_PATH)
    print(f"\nExisting leads imported: {imported_count}")

    # 3. Read incoming JSON submissions
    try:
        with INCOMING_PATH.open("r", encoding="utf-8") as file:
            incoming_leads = json.load(file)

        if not isinstance(incoming_leads, list):
            raise ValueError(
                "incoming_leads.json must contain a JSON list."
            )

    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not read incoming leads: {error}")
        return

    print(f"Incoming submissions: {len(incoming_leads)}")

    # 4. Initialize cleaner, LLM, and email notifier
    cleaner = LeadCleaner()

    try:
        llm_service = LLMService()
    except Exception as error:
        print(f"Could not initialize LLM service: {error}")
        return

    notifier = LeadNotifier()

    # 5. Clean the incoming batch
    cleaned_leads = cleaner.clean_batch(incoming_leads)

    # 6. Process each submission independently
    stats = {
        "new": 0,
        "duplicate": 0,
        "already_processed": 0,
        "needs_review": 0,
        "classified": 0,
        "notifications_sent": 0,
        "notification_failures": 0,
        "notifications_retried": 0,
        "failed": 0,
    }

    # Retry previously pending/failed Hot notifications before new submissions.
    # This uses saved classifications and does not call the LLM again.
    print("\nChecking pending Hot lead notifications...")
    for pending in db.get_pending_hot_notifications():
        submission_id = pending.get("submission_id") or "unknown"
        try:
            sent = notifier.notify_hot_lead(
                pending["lead"], pending["classification"]
            )
            if sent:
                db.update_notification_status(submission_id, "sent")
                stats["notifications_sent"] += 1
                stats["notifications_retried"] += 1
        except Exception as error:
            db.update_notification_status(
                submission_id, "failed", str(error)
            )
            stats["notification_failures"] += 1
            print(f"Retry failed for {submission_id}: {error}")

    for lead in cleaned_leads:
        submission_id = lead.get("id") or "unknown"

        print(f"\nProcessing submission: {submission_id}")

        try:
            # Do not process malformed records.
            if lead.get("validation_status") == "processing_error":
                stats["failed"] += 1
                print("Cleaning failed:")
                print(lead.get("validation_errors", []))
                continue

            # 7. Check duplicates and save the submission.
            result = db.save_incoming_lead(lead)
            status = result["status"]

            print(f"Database status: {status}")

            if status == "already_processed":
                stats["already_processed"] += 1
                print("Skipping previously processed submission.")
                continue

            if status == "new":
                stats["new"] += 1
            elif status == "duplicate":
                stats["duplicate"] += 1
            elif status == "needs_review":
                stats["needs_review"] += 1

            # 8. Skip classification if the message is empty.
            if not lead.get("can_classify"):
                print("Skipped LLM: message is empty.")
                continue

            lead_db_id = result.get("lead_db_id")

            if lead_db_id is None:
                stats["failed"] += 1
                print("Cannot classify: database lead ID is missing.")
                continue

            # 9. Classify the lead and draft a reply.
            classification = llm_service.classify_and_draft(lead)

            print(f"Classification: {classification['tag']}")
            print(f"Reason: {classification['reason']}")
            print(f"Draft reply: {classification['draft_reply']}")

            # 10. Save classification and reply draft.
            db.update_classification(
                lead_db_id=lead_db_id,
                tag=classification["tag"],
                draft_reply=classification["draft_reply"],
                submission_id=submission_id,
            )

            stats["classified"] += 1

            # 11. Notify the team if the lead is Hot.
            if classification["tag"] == "Hot":
                try:
                    notification_sent = notifier.notify_hot_lead(
                        lead,
                        classification,
                    )

                    if notification_sent:
                        db.update_notification_status(submission_id, "sent")
                        stats["notifications_sent"] += 1

                except Exception as error:
                    db.update_notification_status(
                        submission_id, "failed", str(error)
                    )
                    stats["notification_failures"] += 1
                    print(
                        f"Notification failed for "
                        f"{submission_id}: {error}"
                    )

                    # The classification is already saved.
                    # An email failure won't stop other leads.

        except Exception as error:
            stats["failed"] += 1
            print(f"Failed to process {submission_id}: {error}")

    # 12. Print a processing summary.
    print("\n" + "=" * 50)
    print("PROCESSING SUMMARY")
    print("=" * 50)

    for name, count in stats.items():
        print(f"{name.replace('_', ' ').title()}: {count}")

    print("\nProcessing finished.")
    print(f"Database file: {DATA_DIR / 'leads.db'}")


if __name__ == "__main__":
    main()
