
from notifier import LeadNotifier

notifier = LeadNotifier()

test_lead = {
    "id": "TEST-EMAIL-01",
    "name": "Test Customer",
    "email": "customer@example.com",
    "company": "Test Company",
    "message": "We need automation and have an approved budget."
}

classification = {
    "tag": "Hot",
    "reason": "The customer has a clear need and an approved budget.",
    "draft_reply": "Thank you for your interest. Could we arrange a call this week?"
}

try:
    sent = notifier.notify_hot_lead(test_lead, classification)

    if sent:
        print("SUCCESS: Hot lead notification sent!")
    else:
        print("No email sent. Check the lead classification.")

except Exception as error:
    print(f"FAILED: {type(error).__name__}: {error}")
