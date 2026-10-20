
import re
import unicodedata
from typing import Any


class LeadCleaner:
    """
    Cleans and validates lead records.

    Responsibilities:
    - Normalize names, emails, and company names.
    - Validate email addresses.
    - Detect missing or invalid fields.
    - Mark leads that need manual review.
    - Prepare normalized values for duplicate detection.

    Duplicate database lookups and inserts belong in database.py.
    """

    EMAIL_PATTERN = re.compile(
        r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
        r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
        re.IGNORECASE,
    )

    def clean_text(self, value: Any) -> str:
        """Convert a value to clean text and normalize whitespace."""
        if value is None:
            return ""

        if not isinstance(value, str):
            value = str(value)

        value = unicodedata.normalize("NFKC", value)
        return " ".join(value.split())

    def normalize_name(self, name: Any) -> str:
        """Normalize spacing and capitalization in a person's name."""
        name = self.clean_text(name)
        return name.title() if name else ""

    def normalize_email(self, email: Any) -> str:
        """Trim whitespace and lowercase an email for comparison."""
        return self.clean_text(email).lower()

    def normalize_company(self, company: Any) -> str:
        """
        Create a comparison key for company names.

        Example:
        'Fern & Fox' and 'Fern and Fox' produce the same key.
        The display value remains separate.
        """
        company = self.clean_text(company).casefold()
        company = company.replace("&", " and ")
        company = unicodedata.normalize("NFKD", company)

        # Ignore accents in the comparison key.
        company = "".join(
            char for char in company
            if not unicodedata.combining(char)
        )

        # Ignore punctuation and differences in whitespace.
        company = re.sub(r"[^\w\s]", " ", company)
        return " ".join(company.split())

    def validate_email(self, email: str) -> bool:
        """Check basic email syntax; this does not verify mailbox existence."""
        if not email or len(email) > 254:
            return False

        if len(email.split("@")) != 2:
            return False

        local_part, domain = email.rsplit("@", 1)

        if len(local_part) > 64 or len(domain) > 253:
            return False

        return bool(self.EMAIL_PATTERN.fullmatch(email))

    def clean_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        """
        Clean one lead and return a structured record.

        Missing or invalid information is recorded rather than silently
        deleting the lead.
        """
        if not isinstance(lead, dict):
            raise TypeError("Each lead must be a dictionary.")

        # Keep the original input for troubleshooting.
        raw_record = dict(lead)

        name = self.normalize_name(lead.get("name"))
        email = self.normalize_email(lead.get("email"))
        company = self.clean_text(lead.get("company"))
        message = self.clean_text(lead.get("message"))
        lead_id = self.clean_text(lead.get("id"))
        received_at = self.clean_text(lead.get("received_at"))

        errors: list[str] = []

        if not name:
            errors.append("Missing name")

        if not email:
            errors.append("Missing email")
        elif not self.validate_email(email):
            errors.append("Invalid email address")

        if not message:
            errors.append("Missing message")

        if not company:
            errors.append("Missing company")

        # A lead without a usable message should not be classified by an LLM.
        can_classify = bool(message)

        # A missing/invalid email prevents email delivery, but does not
        # necessarily prevent classification or reply drafting.
        can_email = bool(email) and self.validate_email(email)

        # Missing names, email issues, or missing messages require review.
        # Missing company is recorded but does not automatically block work.
        needs_review = any(
            error in errors
            for error in (
                "Missing name",
                "Missing email",
                "Invalid email address",
                "Missing message",
            )
        )

        return {
            "id": lead_id,
            "received_at": received_at,
            "name": name,
            "email": email,
            "company": company,
            "message": message,

            # Comparison keys used by database.py.
            "email_key": email,
            "name_key": name.casefold(),
            "company_key": self.normalize_company(company),

            # Processing and validation metadata.
            "validation_status": (
                "needs_review" if needs_review else "valid"
            ),
            "validation_errors": errors,
            "can_classify": can_classify,
            "can_email": can_email,

            # Keep raw input for auditing and debugging.
            "raw_record": raw_record,
        }

    def clean_batch(
        self, leads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Clean a batch while keeping individual failures visible."""
        cleaned_leads = []

        for index, lead in enumerate(leads):
            try:
                cleaned_leads.append(self.clean_lead(lead))
            except (TypeError, ValueError) as exc:
                # Keep a failed record visible instead of stopping the batch.
                raw_record = (
                    dict(lead) if isinstance(lead, dict)
                    else {"raw_value": repr(lead)}
                )

                cleaned_leads.append({
                    **raw_record,
                    "validation_status": "processing_error",
                    "validation_errors": [
                        f"Cleaning failed at batch index {index}: {exc}"
                    ],
                    "can_classify": False,
                    "can_email": False,
                    "raw_record": raw_record,
                })

        return cleaned_leads
