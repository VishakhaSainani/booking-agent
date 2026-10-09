# Cedar Lane Auto Detailing — AI Receptionist
## System Requirements & Technical Specification

---

## 1. Executive Summary & Objective

**Cedar Lane Auto Detailing** is a busy local auto detailing shop receiving approximately 30 calls per day. Callers have diverse inquiries ranging from booking and rescheduling appointments to asking about pricing, preparation guidelines, vehicle compatibility, or expressing dissatisfaction with charges.

The objective is to build an autonomous AI Receptionist that:
1. **Picks up calls/messages and accurately handles routine shop interactions**.
2. **Maintains two-way synchronization with Google Calendar** for real-time availability checks, booking creation, conflict resolution, and reschedules.
3. **Maintains persistent customer records and audit trails in Google Sheets** across a `Contacts` customer registry and a chronological `Call Logs` ledger.
4. **Enforces clear decision boundaries**: handles standard operational tasks autonomously while gracefully escalating sensitive or complex requests (billing disputes, damage claims, custom commercial fleet quotes) to a human manager.
5. **Ships in two distinct phases**:
   - **Phase 1**: Core agent logic + functional text chat interface (prioritizing correctness, slot conflict handling, and tool execution).
   - **Phase 2**: Real-time voice agent integration via **Vapi** tuned for human-like conversational responsiveness with a strict **<1.2 second response latency target**.

---

## 2. Business Domain & Operating Rules

### 2.1 Shop Operating Hours
* **Monday – Saturday**: 8:00 AM – 6:00 PM (Local Time)
* **Sunday**: Closed
* **Appointment Granularity**: Appointments can start on the hour or half-hour (e.g., 8:00 AM, 8:30 AM, ..., 4:30 PM).
* **Buffer Policy**: No appointments may extend past 6:00 PM closing time.

### 2.2 Services, Durations & Pricing Menu

| Service Name | Description | Duration | Base Price Range |
| :--- | :--- | :--- | :--- |
| **Express Wash & Vac** | Exterior hand wash, rim cleaning, interior vacuum, and window wipe-down. | 45 minutes | $50 (Sedan) / $70 (SUV/Truck) |
| **Interior Detail & Wash** | Deep carpet/seat shampoo, leather conditioning, full steam cleaning, and exterior wash. | 90 minutes (1.5 hrs) | $150 (Sedan) / $190 (SUV/Truck) |
| **Full Detail** | Complete interior deep clean plus multi-stage exterior decontamination, clay bar, and sealant/wax. | 180 minutes (3 hrs) | $250 (Sedan) / $320 (SUV/Truck) |
| **Ceramic Coating / Paint Correction** | Multi-day paint correction and nano-ceramic application. | Multi-day | Custom ($800+) — **Requires Human Quote** |

### 2.3 Vehicle Compatibility Matrix
* **Supported**: Sedans, Coupes, Hatchbacks, SUVs, Crossovers, Pickup Trucks, Passenger Minivans.
* **Special / Oversized (Human Quote Required)**: Commercial cargo vans, lifted dually trucks, RVs, motorhomes, boats, and heavy commercial machinery. The agent informs the caller that special sizing requires manager review and logs the request.

### 2.4 Preparation Guidelines (Caller FAQs)
When callers ask how to prep their vehicle before dropping it off:
1. Remove all personal belongings, valuables, sunglasses, and documents from the vehicle.
2. Clear the trunk and glovebox if an interior detail service is scheduled.
3. Unbuckle or remove child car seats (for liability reasons, detailers cannot reinstall child seats).
4. Bring vehicle keys/fob and inform staff of any sensitive electronics or aftermarket switches.

### 2.5 "Running Late" Policy
* **Grace Period**: Up to 15 minutes late is automatically accommodated. The agent notes the delay on the calendar event and notifies the shop log.
* **Excessive Delay (>15 mins)**: The agent checks if subsequent appointments allow for accommodation; if not, politely offers to reschedule or adjust to an Express service to avoid delaying other customers.

### 2.6 Decision Boundary: Autonomous vs. Human Escalation

| Scenario | Handled By AI? | Action & Protocol |
| :--- | :--- | :--- |
| Check open slots / availability | **Yes** | Queries Google Calendar, checks business hours, presents open slots. |
| Book new appointment | **Yes** | Collects name, phone, service, vehicle type; inserts event into Calendar; upserts into Sheets. |
| Reschedule existing appointment | **Yes** | Finds existing booking by caller phone/name, frees old slot, reserves new slot. |
| Cancel appointment | **Yes** | Removes/cancels event, logs cancellation reason in Sheets. |
| Pricing, hours, prep questions | **Yes** | Answers directly from factual business domain knowledge. |
| Check vehicle type coverage | **Yes** | Confirms standard vehicle or triggers escalation for oversized vehicles. |
| Caller running late | **Yes** | Acknowledges, updates calendar notes, logs to sheets. |
| **Disputed charges / Billing complaints** | **NO (Human Handoff)** | Empathetically listens, takes down invoice/charge details, tags row in Sheets as `NEEDS_HUMAN_CALLBACK`, assures manager follow-up. |
| **Damage claims / Liability issues** | **NO (Human Handoff)** | De-escalates calmly, collects vehicle and incident specifics, flags high-priority human escalation. |
| **Commercial fleet discounts** | **NO (Human Handoff)** | Collects fleet size and company name, schedules manager callback. |

---

## 3. External Integrations Specification

### 3.1 Google Calendar Integration
* **Authentication**: Google Cloud Service Account (`credentials.json`) with calendar edit permissions.
* **Calendar ID**: Designated Cedar Lane appointments calendar.
* **Core Capabilities**:
  1. `list_day_events(date: str)`: Retrieves busy intervals for the target date.
  2. `check_slot_availability(date: str, requested_time: str, duration_minutes: int) -> bool`:
     - Checks if requested time window overlaps any existing calendar event or falls outside 8 AM – 6 PM.
  3. `find_alternative_slots(date: str, requested_time: str, duration_minutes: int, limit: int = 3) -> list[str]`:
     - If the requested time is busy, calculates the closest available open slots (e.g., if 3:30 PM is booked, suggests 4:30 PM).
  4. `create_appointment_event(customer_name, phone, service, vehicle_type, start_iso, end_iso)`:
     - Title: `[Detailing] {customer_name} - {service}`
     - Description: Contact phone, vehicle model, prep reminder, booking status.
  5. `update_appointment_event(event_id, new_start_iso, new_end_iso)`:
     - Shifts existing booking to new slot.
  6. `cancel_appointment_event(event_id)`:
     - Deletes event or marks `[CANCELLED]` in title.

### 3.2 Google Sheets Integration
* **Spreadsheet Tabs**:
  1. **Tab 1: `Contacts`** (Customer Directory)
     - `Phone Number` (Primary Key / Lookup)
     - `Customer Name`
     - `Vehicle Type`
     - `Total Bookings`
     - `Last Contact Date`
     - `Notes / Preferences`
  2. **Tab 2: `Call Logs`** (Audit Trail & Activity Log)
     - `Timestamp` (ISO 8601)
     - `Caller Phone`
     - `Caller Name`
     - `Call Intent` (`Booking`, `Reschedule`, `Cancellation`, `Inquiry`, `Complaint`, `Running Late`)
     - `Outcome / Action Taken`
     - `Needs Human Follow-up?` (`YES` / `NO`)
     - `Summary`
     - `Vapi Call ID` (populated in Phase 2)

---

## 4. Phased Implementation Roadmap

### Phase 1: Core Agent Logic & Text Chat Interface
* **Core LLM Engine**: OpenAI Function Calling (`gpt-4o-mini` or `gpt-4o`) with structured tool definitions.
* **Deterministic Tool Layer**:
  - `check_availability(date, time, service_type)`
  - `book_appointment(customer_name, phone_number, date, time, service_type, vehicle_type)`
  - `reschedule_appointment(customer_name, phone_number, current_date, new_date, new_time)`
  - `cancel_appointment(customer_name, phone_number, date)`
  - `report_running_late(customer_name, phone_number, minutes_late)`
  - `escalate_to_human(customer_name, phone_number, reason, details)`
* **Lightweight Chat UI**:
  - Web interface with message history and simulated phone number input.
  - Live activity sidebar displaying tool executions, calendar state, and sheet log entries for transparent demonstration.
* **Verification Metric**: 100% correct appointment slot allocation, conflict handling, contact capture, and sheet synchronization.

### Phase 2: Voice Integration with Vapi (<1.2s Latency)
* **Vapi Architecture**:
  - Audio Input $\to$ Deepgram Nova-2 (STT) $\to$ Vapi Assistant Engine $\to$ Custom Webhook Tools $\to$ Cartesia Sonic (TTS) $\to$ Audio Output.
* **Webhook Endpoint**:
  - `POST /api/vapi/webhook`
  - Handles `message.type == "tool-calls"`: parses arguments, calls Google services, returns immediate tool execution results.
  - Handles `message.type == "end-of-call-report"`: saves complete call transcript, call duration, recording URL, and AI-generated call summary to Google Sheets.
* **Latency Engineering (Sub-1.2s Knobs)**:
  - **Transcriber**: Deepgram `nova-2`, `endpointing: 280ms`, `smart_format: true`.
  - **LLM**: `gpt-4o-mini` (or Groq `llama-3.3-70b-versatile`) with low temperature (0.2).
  - **Voice**: Cartesia `sonic-english` (Time to First Byte < 100ms).
  - **Silence Timeout**: `silenceTimeoutSeconds = 0.5s` (avoids dead air after caller stops speaking).
  - **Filler Phrasing**: Prompt instructs the agent to naturally acknowledge actions (*"Let me check that for you..."*) while tools execute.

---

## 5. Submission Artifacts

1. **GitHub Repository**:
   - Clean modular codebase, unit tests, `.env.example`, setup script, and architecture documentation.
2. **Video 1 (Phase 1 Chat)**:
   - Screen recording demonstrating:
     - Asking for a pre-booked slot (e.g. Thursday 3:30 PM).
     - Agent detecting conflict and offering an open alternative (e.g. 4:30 PM).
     - Booking confirmation with name & phone.
     - Live Google Calendar and Google Sheets updating in real time.
3. **Video 2 (Phase 2 Vapi Phone Call)**:
   - Recording of a live voice phone call showing:
     - Conversational flow, natural interruptions, sub-1.2s responsiveness.
     - Booking an appointment and asking a shop question.
     - Live sync to Google Calendar and end-of-call logging to Google Sheets.
