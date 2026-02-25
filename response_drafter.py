"""
nodes/response_drafter.py — Generates a draft response using GPT-4o-mini.

Middleware applied:
  - ModelCallLimitMiddleware  → via call_tracker (prevents runaway costs)
  - ModelRetryMiddleware      → via @retry_middleware decorator (handles timeouts)
  - PIIMiddleware             → masked_log updated after node runs

For 'prep' intent: pulls structured prep instructions directly from i18n JSON
instead of relying on GPT to generate them, ensuring accuracy.
"""

import os
import json
from openai import OpenAI
from medic_aid.middleware.middleware import call_tracker, retry_middleware

# Load prep instructions from i18n files
I18N_DIR = os.path.join(os.path.dirname(__file__), "../i18n")

with open(os.path.join(I18N_DIR, "en.json"), "r") as f:
    EN_STRINGS = json.load(f)

with open(os.path.join(I18N_DIR, "fr.json"), "r") as f:
    FR_STRINGS = json.load(f)


def _get_strings(language: str) -> dict:
    return FR_STRINGS if language == "fr" else EN_STRINGS


@retry_middleware
def _call_llm(system_prompt: str, user_message: str) -> str:
    """Calls GPT-4o-mini with retry middleware applied."""
    call_tracker.check_and_increment("response_drafter")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.4,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def response_drafter(state: dict) -> dict:
    """
    Drafts a patient-facing response based on intent + appointment data.

    For 'prep' intent: returns structured instructions from i18n files directly.
    For 'reschedule' / 'cancel': uses GPT-4o-mini with retry + call limit middleware.
    """

    intent      = state.get("intent", "unknown")
    language    = state.get("language", "en")
    appointment = state.get("appointment_details", {})
    found       = state.get("appointment_found", False)
    dept        = appointment.get("department", "general")
    date        = appointment.get("date", "your appointment date")
    new_date    = appointment.get("new_date", "2026-04-01")
    new_time    = appointment.get("new_time", "10:00")
    strings     = _get_strings(language)

    # ── Prep intent: use structured i18n instructions directly ─────
    # This ensures accurate, approved prep instructions — not AI-generated guesses
    if intent == "prep" and found:
        prep_text  = strings["prep_instructions"].get(dept, "")
        dept_label = strings["departments"].get(dept, dept)

        if language == "fr":
            draft = (
                f"Voici les instructions de préparation pour votre rendez-vous en {dept_label} "
                f"du {date} :\n\n{prep_text}\n\n"
                f"N'hésitez pas à nous contacter si vous avez des questions."
            )
        else:
            draft = (
                f"Here are the preparation instructions for your {dept_label} "
                f"appointment on {date}:\n\n{prep_text}\n\n"
                f"Please don't hesitate to contact us if you have any questions."
            )

        print(f"📝 Prep instructions served from i18n ({language.upper()})")

    # ── Reschedule / Cancel: use GPT-4o-mini with middleware ───────
    else:
        lang_instruction = "Respond in French." if language == "fr" else "Respond in English."

        if not found:
            context = strings.get("not_found", "Appointment not found.")
        elif intent == "cancel":
            context = strings["cancel_confirm"].format(
                dept=strings["departments"].get(dept, dept), date=date
            )
        elif intent == "reschedule":
            context = strings["reschedule_confirm"].format(
                dept=strings["departments"].get(dept, dept),
                date=new_date, time=new_time
            )
        else:
            context = "The patient has a general inquiry about their appointment."

        system_prompt = (
            f"You are a warm, professional medical receptionist at Medic-Aid hospital.\n"
            f"Write a SHORT, clear, empathetic response confirming the following action.\n"
            f"{lang_instruction}\n"
            f"Keep it under 3 sentences. Be specific. Do NOT provide clinical advice.\n"
            f"Action confirmed: {context}"
        )

        draft = _call_llm(system_prompt, state.get("raw_message", ""))
        print(f"📝 Draft response generated via GPT-4o-mini ({len(draft)} chars)")

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("response_drafter")

    # Update masked log (PIIMiddleware)
    masked_log = (
        f"response_drafter completed | intent={intent} | "
        f"dept={dept} | lang={language} | patient=[PATIENT_ID]"
    )

    return {
        **state,
        "draft_response": draft,
        "nodes_visited":  nodes_visited,
        "masked_log":     masked_log,
    }