
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


class LeadNotifier:
    """Send email notifications to the team for Hot leads."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_APP_PASSWORD")
        self.receiver_email = os.getenv("NOTIFICATION_EMAIL")

    def notify_hot_lead(self, lead: dict, classification: dict) -> bool:
        """Send a team notification if the lead is Hot."""

        if classification.get("tag") != "Hot":
            print("Notification skipped: lead is not Hot.")
            return False

        required_settings = {
            "SENDER_EMAIL": self.sender_email,
            "SENDER_APP_PASSWORD": self.sender_password,
            "NOTIFICATION_EMAIL": self.receiver_email,
        }

        missing = [
            name for name, value in required_settings.items()
            if not value
        ]

        if missing:
            raise ValueError(
                "Missing email configuration in .env: "
                + ", ".join(missing)
            )

        message = EmailMessage()
        message["Subject"] = (
            f"🔥 Hot Lead: {lead.get('name') or 'Unknown'} "
            f"- {lead.get('company') or 'Unknown company'}"
        )
        message["From"] = self.sender_email
        message["To"] = self.receiver_email

        message.set_content(
            f"""
A new Hot lead has been identified!

Lead ID: {lead.get('id', 'N/A')}
Name: {lead.get('name', 'N/A')}
Email: {lead.get('email', 'N/A')}
Company: {lead.get('company', 'N/A')}

Customer message:
{lead.get('message', 'N/A')}

Classification reason:
{classification.get('reason', 'N/A')}

Draft reply (not sent to the customer):
{classification.get('draft_reply', 'N/A')}

Please review this lead and follow up.
"""
        )

        # Send the notification to the team.
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(message)

        print(
            f"Hot lead notification sent to {self.receiver_email}"
        )
        return True
