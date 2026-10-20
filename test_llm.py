
from llm_service import LLMService

service = LLMService()

test_lead = {
    "name": "Hannah Brooks",
    "company": "Peak Roast",
    "message": (
        "We have 12 coffee shops, an approved budget of £8,000, "
        "and want to automate onboarding emails this month. "
        "Can we arrange a call this week?"
    ),
}

try:
    result = service.classify_and_draft(test_lead)

    print("\nClassification:", result["tag"])
    print("Reason:", result["reason"])
    print("Draft reply:", result["draft_reply"])

except Exception as error:
    print("LLM processing failed:", error)
