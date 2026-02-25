# Medic-Aid — Intelligent Hospital Appointment Assistant

**MBAN 5510 Final Project**
Saint Mary's University | Instructor: Michael Zhang | Deadline: February 25, 2026

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green)](https://github.com/langchain-ai/langgraph)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)](https://streamlit.io)

---

## Project Overview

Medic-Aid is a middleware-driven, stateful hospital appointment assistance system built with LangGraph and GPT-4o-mini. It serves a multi-specialty hospital with five departments and handles patient requests through a risk-based routing architecture that determines whether a request is handled autonomously by an AI agent, escalated to human staff review, or immediately escalated as an emergency.

The system goes beyond the minimum project requirements by implementing a dual-portal interface (Patient Portal and Staff Portal), a bilingual experience in English and French with automatic language detection, a real SQLite appointment database with live lookups and updates, new patient registration with reference number generation, a hospital directory and navigation guide per department, and a fully autonomous agent conversation loop for low-risk cases.

---

## Supported Departments

| Department | Code | Specialty |
|---|---|---|
| Cardiology | cardiology | Heart and vascular |
| Imaging and Radiology | radiology | MRI, X-rays, scans |
| Dental | dental | Dental procedures |
| General Practice | general | Primary care |
| Orthopedics | orthopedics | Bones and joints |

---

## Architecture and Workflow

The system is built as a LangGraph stateful workflow with nine nodes. The core design principle is risk-based routing: the severity of a patient request determines which path is taken and who (agent or human) handles it.

```
Patient Input
     |
[language_detector]   Detects EN or FR automatically
     |
[intent_classifier]   Classifies: reschedule | cancel | prep | emergency | unknown
     |
[risk_evaluator]      Assigns: LOW | MEDIUM | HIGH
     |
     +------------------+------------------+
   HIGH               MEDIUM              LOW
     |                   |                  |
[escalation_node]  [need_info_node]    [db_lookup]
     |                   |             |         |
  ESCALATE         NEED_INFO        FOUND     NOT FOUND
  (immediate)      Staff HITL          |           |
                   review queue  [response_    [new_patient_
                                  drafter]       node]
                                      |           |
                                 [agent_node] <---+
                                 Autonomous handling:
                                 - Asks follow-up questions
                                 - Confirms before acting
                                 - Executes and explains
                                      |
                                   READY
```

### Risk Levels and Routing

**LOW risk** — handled autonomously by the AI agent without human review. The agent follows a conversation loop: it asks the patient a follow-up question if needed, waits for confirmation, executes the action in the database, and explains what was done.

**MEDIUM risk** — routed to the Staff Portal HITL Review Queue. A staff member reviews the case, edits or approves the draft response, and sends it to the patient.

**HIGH risk** — immediately escalated. A hardcoded emergency response is returned directing the patient to call 911 or visit the nearest emergency room. No AI drafting and no human review delay.

### Terminal Statuses

| Status | Meaning |
|---|---|
| READY | Request processed and response sent |
| NEED_INFO | More information required or staff review pending |
| ESCALATE | Emergency detected, patient directed to emergency services |

---

## Agent Conversation Loop (LOW Risk)

For reschedule and cancel intents, the agent does not act immediately. It follows a structured two-stage conversation:

**Reschedule:**
1. Agent asks: "I found your appointment on [date]. What date and time would you prefer?"
2. Patient replies with their preferred date and time in natural language.
3. Agent parses the reply using GPT-4o-mini, updates the database, and confirms the new appointment.

**Cancel:**
1. Agent asks: "Just to confirm, would you like to cancel your [dept] appointment on [date]? Reply YES to confirm."
2. If the patient confirms, the agent cancels the appointment and sends a confirmation.
3. If the patient declines, the appointment is kept and the patient is informed.

**Preparation instructions:**
The agent answers immediately with structured instructions from the i18n files. No follow-up is needed.

This design ensures the agent never acts on ambiguous input and always explains what it did, which satisfies the requirement for traceable, accountable agent behavior.

---

## Middleware Components

All middleware components are implemented in `medic_aid/middleware/middleware.py` and integrate with the shared LangGraph AppointmentState dictionary.

| Middleware | Location | Integration with State |
|---|---|---|
| PIIMiddleware | middleware.py | Masks patient_name and patient_id in all log outputs written to masked_log |
| OpenAIModerationMiddleware | middleware.py | Called inside risk_evaluator node; result influences risk_level in state |
| ModelRetryMiddleware | middleware.py | Applied as @retry_middleware decorator on LLM call functions in agent_node and response_drafter |
| ModelCallLimitMiddleware | middleware.py | call_tracker increments on every LLM call; reset at start of each run in run_workflow() |
| SummarizationMiddleware | middleware.py | Called in all terminal nodes to write a readable PII-safe summary to masked_log |
| ContextEditingMiddleware | hitl_node.py | Staff reviewer edits the draft in the HITL panel; edited text replaces final_response in state |
| HumanInTheLoopMiddleware | hitl_node.py | Pauses the CLI workflow for staff input; in Streamlit, the Staff Portal review queue serves this role |

---

## Dual Portal Design

### Patient Portal

Accessible without login. Patients submit requests by providing their Patient ID, name, department, and a message. The system auto-detects their language and routes the request through the workflow. For LOW risk requests, the agent handles the conversation interactively. For MEDIUM risk, the patient is notified that their request has been forwarded to staff.

### Staff Portal

Accessible via password authentication (demo password: admin123). The portal has three sections:

**HITL Review Queue** — shows all patient requests that require human review. Staff can read the patient's original message, view the AI-generated draft, edit it if needed, and approve or reject it. Approving a new patient registration also updates their status in the database from pending to confirmed.

**All Appointments** — displays the complete list of appointments in the database with status filtering. Staff can view confirmed, pending, rescheduled, and cancelled appointments.

**New Patient Registrations** — lists patients who registered through the portal and are awaiting staff confirmation. Staff can confirm or reject each registration individually.

---

## Bilingual Support

The system supports English and French. Language is detected automatically from the patient's message using the langdetect library. If detection fails or the language is unsupported, the system defaults to English.

All patient-facing responses, preparation instructions, follow-up questions, confirmation messages, error messages, and the hospital directory are available in both languages. The UI switches language across all labels, placeholders, and help text when the patient selects their preferred language.

---

## Hospital Directory

After every successful response, the system displays the department's location within the hospital, including floor and room number, the nearest entrance, parking information, elevator directions, wheelchair accessibility details, arrival tips, and the department contact number. This information is stored in `medic_aid/i18n/directory.json` and is served in both English and French. The directory card is not shown for emergency escalations.

---

## Environment Setup

### Prerequisites

- Python 3.11 or higher
- pip or uv package manager
- OpenAI API key

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/medic-aid.git
cd medic-aid

# 2. Install dependencies
pip install langgraph langchain langchain-openai openai streamlit python-dotenv langdetect

# 3. Set up environment variables
cp .env.example .env
# Open .env and add your key:
# OPENAI_API_KEY=sk-your-key-here

# 4. Seed the database
python medic_aid/database/setup.py
```

---

## Running the Application

### Streamlit Web UI

```bash
export OPENAI_API_KEY=$(grep OPENAI_API_KEY .env | cut -d '=' -f2)
streamlit run app.py
```

Open your browser to http://localhost:8501

### CLI — Interactive Mode

```bash
python cli.py
```

### CLI — Argument Mode

```bash
# Reschedule (LOW risk — agent handles)
python cli.py --patient-id P001 --name "Alice Martin" --dept cardiology \
  --message "I need to reschedule my appointment" --no-hitl

# Emergency escalation (HIGH risk)
python cli.py --patient-id P004 --name "David Singh" --dept cardiology \
  --message "I have severe chest pain" --no-hitl

# French cancel request (LOW risk)
python cli.py --patient-id P002 --name "Bob Tremblay" --dept radiology \
  --message "Je voudrais annuler mon rendez-vous" --no-hitl
```

---

## Human-in-the-Loop Workflow

HITL applies to MEDIUM risk cases only. LOW risk cases are handled autonomously by the agent. HIGH risk cases bypass HITL entirely and receive an immediate emergency response.

### In CLI mode

1. The workflow runs through all nodes automatically.
2. When a MEDIUM risk case reaches the need_info_node, the terminal pauses and displays the draft response.
3. The staff reviewer types A to approve or E to edit before sending.
4. The final response (approved or edited) is saved to final_response in state.

### In Streamlit Staff Portal

1. MEDIUM risk requests are added to the HITL Review Queue automatically.
2. Staff log in to the Staff Portal using the password admin123.
3. Each queued request shows the patient's message, intent, risk level, and the AI-generated draft.
4. Staff can edit the draft in an editable text area and click Approve and Send or Reject.
5. For new patient registrations, approving also updates the database status from pending to confirmed.

---

## Running Tests

```bash
python tests/test_scenarios.py
```

The test suite covers six scenarios:

1. Normal reschedule — English, existing patient, LOW risk
2. Normal cancel — French, existing patient, LOW risk
3. Preparation instructions — existing patient, LOW risk
4. Emergency escalation — English, HIGH risk
5. Unknown intent — NEED_INFO, MEDIUM risk
6. Emergency escalation — French, HIGH risk

---

## Expected CLI Output

```
Medic-Aid — Run ID: RUN-20260223-143022-A1B2
Patient: P001 | Message: I need to reschedule...
------------------------------------------------------------
Language detected: English
Intent classified: RESCHEDULE
Risk level: LOW
Appointment found: cardiology on 2026-03-10
Agent asking follow-up question...

FINAL RUN SUMMARY
------------------------------------------------------------
  Run ID         : RUN-20260223-143022-A1B2
  Terminal Status: READY
  Intent         : RESCHEDULE
  Risk Level     : LOW
  Language       : English
  Human Approved : False
  Human Edited   : False
  Path Taken     : language_detector -> intent_classifier -> risk_evaluator
                   -> db_lookup -> response_drafter -> agent_node
  Masked Log     : Intent: RESCHEDULE | Risk: LOW | Status: READY |
                   Patient: [PATIENT_ID] | Path: language_detector -> ...
```

---

## Design Decisions and Assumptions

1. Risk-based routing was chosen over a uniform HITL model because it reflects real hospital operations: routine administrative tasks do not require staff time, while unusual or unclear requests benefit from human judgment.

2. The agent conversation loop uses two workflow runs for follow-up questions. The first run produces the follow-up question. The second run receives the patient's reply and executes the action. This keeps the LangGraph state clean and avoids complex multi-turn state management within a single graph execution.

3. Language detection uses the langdetect library. If detection is uncertain or the language is not English or French, the system defaults to English.

4. Preparation instructions are served directly from the i18n JSON files rather than generated by the LLM. This ensures accuracy and consistency for medically adjacent content.

5. Emergency detection uses both keyword matching and GPT-4o-mini intent classification for redundancy. If either method identifies an emergency, the HIGH risk path is taken.

6. PII masking is applied at the log level only. The live UI and staff reviewers always see real patient data.

7. SQLite is used for simplicity and portability. In a production environment this would be replaced with a proper hospital database system.

8. The system does not provide clinical advice. All content is administrative. Emergency cases are directed to 911 and emergency services.

---

## Project Structure

```
medic-aid/
├── .env.example
├── .gitignore
├── pyproject.toml
├── app.py                        Streamlit web UI (dual portal)
├── cli.py                        CLI entry point
├── data/
│   └── appointments.db           SQLite database (auto-created on first run)
├── medic_aid/
│   ├── state.py                  Shared AppointmentState definition
│   ├── graph.py                  LangGraph workflow and routing logic
│   ├── nodes/
│   │   ├── language_detector.py  Detects EN or FR
│   │   ├── intent_classifier.py  Classifies patient intent via GPT-4o-mini
│   │   ├── risk_evaluator.py     Assigns LOW / MEDIUM / HIGH risk
│   │   ├── db_lookup.py          Database lookup and action execution
│   │   ├── new_patient_node.py   Registers new patients with reference number
│   │   ├── response_drafter.py   Drafts responses for agent_node
│   │   ├── agent_node.py         Autonomous agent for LOW risk cases
│   │   ├── hitl_node.py          CLI human review for MEDIUM risk
│   │   ├── escalation_node.py    Immediate emergency response
│   │   └── need_info_node.py     Handles unknown or unclear requests
│   ├── middleware/
│   │   └── middleware.py         All seven middleware components
│   ├── database/
│   │   └── setup.py              Database creation, seeding, and CRUD operations
│   └── i18n/
│       ├── en.json               English strings and prep instructions
│       ├── fr.json               French strings and prep instructions
│       └── directory.json        Hospital directory per department (EN and FR)
└── tests/
    └── test_scenarios.py         Six automated test scenarios
```

---

## Demo Video

LinkedIn demo link: [ADD YOUR LINKEDIN LINK HERE]

The demo covers the following scenarios:

- LOW risk scenario: patient reschedules via agent conversation loop (follow-up question, reply, confirmation)
- MEDIUM risk scenario: unknown intent routed to Staff Portal HITL review queue
- HIGH risk scenario: emergency message triggering immediate escalation
- Bilingual scenario: French-language request with French response and directory

---

## Important Notice

This system is not a substitute for professional medical advice. Emergency handling directs users to call 911 or visit the nearest emergency room. The system does not diagnose or treat medical conditions.

---

Built using LangGraph, GPT-4o-mini, Streamlit, and SQLite.