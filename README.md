# JEEVIT Lead Automation

An AI-assisted lead-processing workflow that cleans incoming website enquiries, detects likely duplicates, classifies leads as **Hot**, **Warm**, or **Cold**, drafts a first reply, stores results in SQLite, and emails the team when a Hot lead is identified.

## Features

- **Data cleaning and validation:** Normalizes names, email addresses, and company names; identifies missing or invalid fields.
- **Duplicate detection:** Checks incoming submissions against existing customer records and avoids processing a repeated submission ID twice.
- **LLM classification:** Uses Groq to classify enquiries as Hot, Warm, or Cold and generate a short reply draft.
- **SQLite storage:** Keeps customer records, individual enquiries, and processing errors in a local database.
- **Hot-lead notifications:** Sends a Gmail notification to a configured recipient when a lead is classified as Hot.
- **Notification retry support:** Tracks pending/sent/failed Hot-lead notifications so pending notifications can be retried without calling the LLM again.
- **Visible processing results:** Prints per-submission status and a processing summary to the terminal.

## Workflow

1. Load the existing customer records from `data/existing_leads.csv`.
2. Read incoming form submissions from `data/incoming_leads.json`.
3. Clean and validate each submission.
4. Check whether the submission was already processed and whether the customer appears to be a duplicate.
5. Save the customer record and enquiry in SQLite.
6. For submissions with a usable message, call the Groq LLM to assign a tag and draft a reply.
7. Save the classification and draft reply.
8. If the tag is `Hot`, send a Gmail notification to the configured recipient.
9. Print a processing summary and report failures.

> The JSON file simulates website submissions for this assignment. A real deployment could receive the same data through a secured webhook.

## Project structure

```text
jeevit-lead-automation/
├── data/
│   ├── existing_leads.csv       # Provided existing customer records
│   ├── incoming_leads.json      # Sample incoming form submissions
│   └── leads.db                 # Created automatically by SQLite
├── cleaner.py                   # Cleaning and validation
├── database.py                  # SQLite tables and data access
├── llm_service.py               # Groq classification and reply drafting
├── notifier.py                  # Gmail Hot-lead notifications
├── main.py                      # Workflow orchestration
├── test_llm.py                  # Optional LLM smoke test
├── test_mail.py                 # Optional email smoke test
├── requirements.txt
├── .env                         # Local secrets; do not commit
├── .gitignore
└── README.md
```

Your local filenames may differ slightly; update the test-file names in the commands below if needed.

## Requirements

- Python 3.10 or newer (Python 3.12 is recommended)
- A Groq API key and a model available to your Groq account
- A Gmail account with 2-Step Verification enabled and an App Password
- Internet access for Groq API calls and Gmail SMTP

## Setup on Windows / PowerShell

### 1. Open the project directory

```powershell
cd C:\Users\User\Desktop\Jeevit\jeevit-lead-automation
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can run the project with the virtual environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root. Add your own values; do not copy real credentials into the README or source code.

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_sender_gmail@gmail.com
SENDER_APP_PASSWORD=your_google_app_password
NOTIFICATION_EMAIL=your_recipient_email@gmail.com
```

Notes:
- `GROQ_MODEL` must be a model ID currently supported by your Groq account.
- `SENDER_APP_PASSWORD` is a Google App Password, not your normal Gmail password.
- `NOTIFICATION_EMAIL` can be the same address as `SENDER_EMAIL`.
- Keep `.env` in `.gitignore`. If a credential is exposed, revoke or rotate it.

### 5. Check the input files

Confirm these files exist:

- `data/existing_leads.csv`
- `data/incoming_leads.json`

The CSV is expected to include `lead_id`, `name`, `email`, and `company` columns. Incoming JSON is expected to be a list of submission objects. Each submission should ideally include an `id`, `name`, `email`, `company`, `message`, and optionally `received_at`.

### 6. Run the workflow

```powershell
python main.py
```

The database file `data/leads.db` is created automatically. The workflow prints the status of each submission and a summary of new leads, duplicates, classifications, notification results, and failures.

### 7. Optional: test the integrations separately

If these test scripts are included in your project:

```powershell
python test_llm.py
python test_mail.py
```

The email test sends a real test message to `NOTIFICATION_EMAIL`.

## Database overview

The SQLite database uses these tables:

- **`leads`** — one customer-level record per recognized lead, including contact details, tag, draft reply, and processing status.
- **`enquiries`** — individual form submissions. Multiple enquiries can point to one customer record.
- **`processing_errors`** — validation and processing issues for review.
- **Notification tracking fields/table** — depending on the version of `database.py`, notification status is stored separately so pending Hot-lead alerts can be retried.

Do not delete `data/leads.db` just to rerun the program unless you intentionally want to reset the local test database. Removing it loses the saved processing history and can cause submissions to be processed again.

## Classification and notifications

The LLM returns:
- `tag`: `Hot`, `Warm`, or `Cold`
- `reason`: a short explanation for the classification
- `draft_reply`: a suggested response for the team to review

Only Hot classifications trigger the Gmail notifier. The draft reply is included in the team alert for review; it is not automatically sent to the customer.

The LLM can make mistakes. Treat classifications and drafts as decision support, validate the returned schema, and use human review for uncertain or incomplete submissions.

## Duplicate handling and known limitations

- Exact email matching and normalized name/company matching are useful but do not catch every real-world duplicate.
- Email aliases (for example, plus-addressing) and company-name typos can cause duplicate detection to miss a match.
- Fuzzy matching can also incorrectly merge two different customers, so uncertain matches should be flagged for human review rather than merged automatically.
- A submission with a missing name or invalid email may still contain a genuine enquiry. Preserve the enquiry and mark it for review.
- A Hot classification on incomplete or suspicious data should not automatically be treated as proof of identity or buying intent.
- SMTP acceptance does not guarantee inbox placement; check recipient settings, Spam, and provider logs if an alert is missing.
- If the same notification is retried after an ambiguous SMTP/network failure, duplicate emails are possible unless delivery is confirmed and status is updated reliably.

## Error handling

The workflow is designed to continue with later submissions when an individual submission fails. Check the terminal output and `processing_errors` table for issues. For production use, add structured logs, retry limits with exponential backoff, monitoring, and alerts for persistent failures.

## Security

- Never commit `.env`, app passwords, API keys, or customer data.
- Use a secrets manager in production.
- Restrict access to the database and logs.
- Treat form messages as untrusted input; prompt-injection text in a customer message must not override the system's classification instructions.
- Do not send draft replies to customers without an explicit approval workflow.

## Suggested next improvements

1. Add automated unit and integration tests for cleaning, deduplication, classification, and notification failures.
2. Add a review queue for invalid data and uncertain duplicate matches.
3. Use a secured webhook and a queue/background workers for real-time, higher-volume intake.
4. Move to PostgreSQL when concurrent processing and production deployment require it.
5. Track notification delivery status and safely retry failed notifications.
6. Measure classification precision/recall, duplicate-detection accuracy, latency, and cost.
7. Add a small admin view to review leads, enquiries, drafts, and errors.

## AI-assisted development disclosure

If AI coding tools were used while developing this assignment, disclose which tools were used and how their output was reviewed. For example, describe that generated suggestions were reviewed, tested, and adapted to the project rather than claiming unverified behavior.

## Demo checklist

For a short screen recording:

1. Show the project structure and `.env` variable names without revealing secret values.
2. Run the workflow and show cleaning, duplicate handling, classifications, and saved drafts.
3. Show a Hot lead notification arriving in the recipient inbox.
4. Run the workflow again to demonstrate that already-processed submissions are skipped and sent notifications are not resent.
5. Show the database tables and explain how errors and incomplete records are surfaced.

## License

This project was created as an assignment/demo. Add a license if you intend to distribute it publicly.
