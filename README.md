# Cedar Lane Auto Detailing — AI Receptionist

An autonomous, production-ready AI Receptionist for **Cedar Lane Auto Detailing** built with **Google Gemini**, **FastAPI**, **Google Calendar**, **Google Sheets**, and **Vapi** voice integration with a strict sub-1.2s response latency target.

---

## 🌟 Key Features

1. **Two-Way Google Calendar Sync**: Real-time slot collision detection, business hours enforcement (8:00 AM – 6:00 PM Mon–Sat, closed Sunday), closing-time buffer calculations, and automated nearest-slot alternative ranking.
2. **Persistent Audit Trail in Google Sheets**:
   - `Contacts` registry: Tracks customer primary keys, total bookings count, vehicle types, and preferences.
   - `Call Logs` ledger: Chronological audit trail logging call intents, outcomes, summaries, and human escalation flags.
3. **Strict Decision Boundaries**:
   - *Autonomous*: Slot lookups, bookings, reschedules, cancellations, late notifications, prep guidelines, pricing FAQs.
   - *Escalated to Human*: Billing disputes, damage claims, commercial fleet quotes, oversized vehicles, custom ceramic coating quotes (`NEEDS_HUMAN_CALLBACK`).
4. **Phase 1 Interactive Web Chat & Live Monitor**:
   - Split-screen dashboard with chat interface and real-time activity sidebar showing tool executions, calendar schedules, and live sheets synchronization.
5. **Phase 2 Sub-1.2s Real-Time Voice Integration (Vapi)**:
   - Deepgram Nova-2 (STT) + Google Gemini (LLM) + Cartesia Sonic (TTS) with 280ms endpointing and 0.5s silence timeout.
   - Webhook endpoint (`POST /api/vapi/webhook`) handling live tool execution and end-of-call report persistence.

---

## 🏛️ System Architecture

```
                               ┌────────────────────────────────┐
                               │   Caller / Web Chat / Phone    │
                               └──────────────┬─────────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     │                                                 │
          [Phase 1: Web Interface]                         [Phase 2: Vapi Voice Engine]
         FastAPI REST & Static UI                           Deepgram STT ➔ Cartesia TTS
                     │                                                 │
                     └────────────────────────┬────────────────────────┘
                                              │
                              ┌───────────────▼───────────────┐
                              │     ReceptionistAgent         │
                              │  Gemini Tool Calling Engine   │
                              └───────────────┬───────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      │                                               │
           ┌──────────▼──────────┐                         ┌──────────▼──────────┐
           │   CalendarAdapter   │                         │    SheetsAdapter    │
           │  Collision Detection│                         │  Contacts & Logs    │
           └──────────┬──────────┘                         └──────────┬──────────┘
                      │                                               │
          ┌───────────┴───────────┐                       ┌───────────┴───────────┐
          │                       │                       │                       │
┌─────────▼─────────┐   ┌─────────▼─────────┐   ┌─────────▼─────────┐   ┌─────────▼─────────┐
│ InMemoryCalendar  │   │  Google Calendar  │   │  InMemorySheets   │   │   Google Sheets   │
│ (Offline / Tests) │   │ (Service Account) │   │ (Offline / Tests) │   │ (Service Account) │
└───────────────────┘   └───────────────────┘   └───────────────────┘   └───────────────────┘
```

---

## 🚀 Quickstart Guide

### 1. Requirements
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or standard `python3` / `venv`

### 2. Setup Virtual Environment & Dependencies
```bash
# Clone the repository
git clone git@github-personal.com:VishakhaSainani/booking-agent.git
cd booking-agent

# Create and activate virtual environment
uv venv --python 3.11 .venv
source .venv/bin/activate

# Install dependencies in editable mode with test tools
uv pip install -e ".[dev]"
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API Key | `""` (runs offline simulation if unset) |
| `GEMINI_MODEL` | Gemini Model identifier | `gemini-2.5-flash` |
| `USE_MOCK_INTEGRATIONS` | `true` for in-memory development, `false` for live Google APIs | `true` |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to Google Cloud Service Account JSON | `credentials.json` |
| `GOOGLE_CALENDAR_ID` | Target Google Calendar ID | `primary` |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Target Google Sheets ID | `""` |
| `PORT` | Web server port | `8000` |

### 4. Run the Application
Launch the server using the provided launch script:
```bash
./start.sh
```
Or with Uvicorn directly:
```bash
uvicorn cedar_lane_ai.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser.

---

## 🎬 Video Walkthrough Guides

### 📹 Video 1 Walkthrough: Phase 1 Chat & Real-Time Sync
Follow this exact sequence to record the Phase 1 submission demo:

1. **Open the Dashboard**: Navigate to `http://localhost:8000`.
2. **Seed the Conflict Scenario**: Click the **"⚡ Seed Conflict Demo"** button in the header.
   - *What happens*: Seeds an existing appointment on **Thursday, October 15, 2026 at 3:30 PM – 5:00 PM** for client *David Miller* (Interior Detail).
3. **Ask for the Busy Slot**:
   - Click the chip: `⚠️ Thursday 3:30 PM (Conflict Test)` or type:
     > *"Can I book an Interior Detail for Thursday October 15th at 3:30 PM?"*
   - **Agent Behavior**: The agent inspects the calendar, detects that 3:30 PM is booked, and **proactively offers alternative open slots** (e.g. 2:00 PM).
   - **Sidebar**: The *Live Tool Calls* tab displays the executed `check_availability` tool call showing `available: false` and the calculated alternative slots.
4. **Confirm Booking with Customer Details**:
   - Reply with:
     > *"Let's go with 2:00 PM. My name is Jane Doe, phone is +1 (555) 234-5678, driving a Honda Civic Sedan."*
   - **Agent Behavior**: Confirms the booking at 2:00 PM, gives the exact price ($150 for Sedan Interior Detail), and recites the vehicle preparation reminders.
   - **Sidebar**:
     - *Live Tool Calls*: Shows `book_appointment` executed successfully.
     - *Calendar State Tab*: Shows Jane Doe's new booking at 2:00 PM – 3:30 PM.
     - *Google Sheets Sync Tab*: Shows Jane Doe upserted in the `Contacts` registry and logged in the `Call Logs` ledger.
5. **Test Escalation Boundary**:
   - Click the chip: `🚨 Disputed Charge Escalation` or type:
     > *"I was overcharged $50 on my credit card from my last visit!"*
   - **Agent Behavior**: De-escalates politely, refuses to make unauthorized financial decisions, logs the issue, and assures a manager callback.
   - **Sidebar**: The `Call Logs` tab highlights `needs_human_followup: YES (Follow Up)`.

---

### 🎙️ Video 2 Walkthrough: Phase 2 Real-Time Voice Integration (Vapi)

1. **Expose Local Server**:
   ```bash
   ngrok http 8000
   ```
2. **Inspect Assistant Blueprint**:
   Visit `http://localhost:8000/api/vapi/assistant-config` to view the pre-tuned sub-1.2s voice configuration.
3. **Vapi Dashboard Setup**:
   - Set **Server URL** to `https://<your-ngrok-domain>/api/vapi/webhook`.
   - Transcriber: Deepgram `nova-2` with `endpointing: 280ms`.
   - Voice: Cartesia `sonic-english`.
   - Silence Timeout: `0.5s`.
   - Import the tools schema provided by `/api/vapi/assistant-config`.
4. **Demonstrate Phone Call**:
   - Place a voice call to the assigned Vapi phone number.
   - Ask for pricing or availability.
   - Complete a booking over the phone.
   - Observe live sync in Google Calendar and the end-of-call report logged to Google Sheets upon hanging up.

---

## 🧪 Automated Testing & Validation

All tests run in **zero-cost, safe offline mode** using mocks and deterministic adapters:
```bash
# Run the complete test suite
.venv/bin/pytest -v

# Run linter and code quality checks
.venv/bin/ruff check .
```

### Test Coverage Highlights:
- `test_domain_models.py`: Pricing matrix for sedans vs SUVs, Sunday rejection, operating hours boundaries, closing buffers, oversized vehicle classification.
- `test_calendar_adapter.py`: Slot collision arithmetic, nearest-slot alternative ranking, reschedule slot shift, cancellation slot freeing.
- `test_sheets_adapter.py`: Customer upsert with booking counters, 10-digit phone normalization, audit trail logging.
- `test_agent_tools.py`: All 6 deterministic shop tools and conversational turns.
- `test_web_api.py`: FastAPI endpoints, state snapshots, demo seeder, static web asset serving.
- `test_vapi_webhook.py`: Real-time tool-call webhooks and end-of-call report logging.

---

## 📁 Repository Structure

```
booking-agent/
├── cedar_lane_ai/
│   ├── adapters/
│   │   ├── calendar_base.py        # CalendarAdapter ABC
│   │   ├── in_memory_calendar.py   # In-memory slot collision & ranking
│   │   ├── google_calendar.py      # Google Calendar REST API adapter
│   │   ├── sheets_base.py          # SheetsAdapter ABC
│   │   ├── in_memory_sheets.py     # In-memory Contacts & Call Logs
│   │   └── google_sheets.py        # Google Sheets v4 REST API adapter
│   ├── api/
│   │   ├── app.py                  # FastAPI server & endpoints
│   │   ├── vapi.py                 # Vapi voice webhook & latency tuning
│   │   └── static/
│   │       ├── index.html          # Phase 1 interactive chat interface
│   │       ├── style.css           # Modern aesthetic UI styles
│   │       └── app.js              # Real-time dashboard state manager
│   ├── domain/
│   │   └── models.py               # Services, pricing, hours, entities
│   ├── services/
│   │   ├── prompts.py              # Cedar Lane shop system prompt
│   │   ├── tools.py                # 6 deterministic shop tools & schemas
│   │   └── agent.py                # Gemini function calling coordinator
│   └── config.py                   # Pydantic Settings & environment config
├── tests/                          # 26 automated unit & integration tests
├── .env.example                    # Environment variable template
├── pyproject.toml                  # PEP 621 packaging & tool configuration
├── start.sh                        # One-command server startup script
├── REQUIREMENTS.md                 # Original system specification
└── README.md                       # Architecture & demonstration guide
```

---

## 📄 License
MIT License. Built for Cedar Lane Auto Detailing.
