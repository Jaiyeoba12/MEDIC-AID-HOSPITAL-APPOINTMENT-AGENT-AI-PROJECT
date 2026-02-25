"""
nodes/agent_node.py — Autonomous agent for LOW risk cases.

Handles the full conversation loop for:
  - reschedule : asks preferred date/time → parses → updates DB → confirms
  - cancel     : asks confirmation → executes or keeps appointment
  - prep       : answers immediately with i18n instructions
  - new_patient: asks preferred date/time → saves to DB → confirms with reference number

HITL is reserved for MEDIUM and HIGH risk only.

Middleware applied:
  - ModelRetryMiddleware     → @retry_middleware on LLM calls
  - ModelCallLimitMiddleware → call_tracker on every LLM call
  - SummarizationMiddleware  → audit log after completion
  - PIIMiddleware            → patient info masked in logs
"""

import os
import json
from openai import OpenAI
from medic_aid.middleware.middleware import call_tracker, retry_middleware, summarize_trace

# ── Follow-up questions ────────────────────────────────────────────
FOLLOWUP_QUESTIONS = {
    "reschedule": {
        "en": "I found your {dept} appointment on {date} at {time}. What date and time would you prefer for your new appointment? (e.g. March 20 at 2pm)",
        "fr": "J'ai trouvé votre rendez-vous en {dept} le {date} à {time}. Quelle date et heure préférez-vous? (ex: 20 mars à 14h)"
    },
    "cancel": {
        "en": "I found your {dept} appointment on {date} at {time}. Just to confirm — would you like to cancel this appointment? Please reply YES to confirm.",
        "fr": "J'ai trouvé votre rendez-vous en {dept} le {date} à {time}. Pour confirmer — souhaitez-vous annuler? Répondez OUI pour confirmer."
    },
    "new_patient": {
        "en": "Welcome to Medic-Aid, {name}! We have received your registration for the {dept} department.\n\nTo complete your booking, what date and time would you prefer for your first appointment? (e.g. March 25 at 10am)",
        "fr": "Bienvenue chez Medic-Aid, {name}! Nous avons reçu votre inscription pour le département {dept}.\n\nPour finaliser votre rendez-vous, quelle date et heure préférez-vous? (ex: 25 mars à 10h)"
    },
}

# ── Completion messages ────────────────────────────────────────────
COMPLETION_MESSAGES = {
    "reschedule": {
        "en": "Done! Your {dept} appointment has been successfully rescheduled to {new_date} at {new_time}. You will receive a reminder closer to your appointment date.",
        "fr": "C'est fait! Votre rendez-vous en {dept} a été reprogrammé avec succès au {new_date} à {new_time}."
    },
    "cancel": {
        "en": "Done! Your {dept} appointment on {date} has been successfully cancelled. Feel free to reach out if you need to rebook.",
        "fr": "C'est fait! Votre rendez-vous en {dept} du {date} a été annulé avec succès."
    },
    "prep": {
        "en": "Here are the preparation instructions for your {dept} appointment on {date}.",
        "fr": "Voici vos instructions de préparation pour votre rendez-vous en {dept} le {date}."
    },
    "new_patient": {
        "en": "Your appointment has been confirmed!\n\nReference Number: {reference}\nDepartment: {dept}\nDate: {new_date} at {new_time}\n\nPlease arrive 15 minutes early and bring a valid photo ID and your health card. We look forward to seeing you!",
        "fr": "Votre rendez-vous a été confirmé!\n\nNuméro de référence: {reference}\nDépartement: {dept}\nDate: {new_date} à {new_time}\n\nVeuillez arriver 15 minutes à l'avance avec une pièce d'identité et votre carte santé."
    },
}


@retry_middleware
def _parse_date_from_reply(patient_reply: str) -> dict:
    """Uses GPT-4o-mini to extract date and time from patient's free-text reply."""
    call_tracker.check_and_increment("agent_node_parse_date")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = """Extract the date and time from the patient's message.
Return ONLY a JSON object: {"date": "YYYY-MM-DD", "time": "HH:MM"}
If you cannot determine the date or time, use defaults: {"date": "2026-04-01", "time": "10:00"}
Convert month names to numbers. Use 24-hour time format."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": patient_reply},
        ],
        temperature=0,
        max_tokens=50,
    )
    raw = response.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"date": "2026-04-01", "time": "10:00"}


def agent_node(state: dict) -> dict:
    """
    Autonomous agent for LOW risk cases.
    Manages a two-stage conversation loop for all intents.
    """
    from medic_aid.database.setup import cancel_appointment, update_appointment, get_connection

    intent        = state.get("intent", "")
    language      = state.get("language", "en")
    appointment   = state.get("appointment_details", {})
    dept          = appointment.get("department", state.get("department", "general"))
    date          = appointment.get("date", "your appointment date")
    time_str      = appointment.get("time", "")
    conv_stage    = state.get("agent_conv_stage", "ask")
    patient_reply = state.get("agent_patient_reply", "")
    patient_name  = state.get("patient_name", "")
    reference     = appointment.get("reference", "")

    nodes_visited = state.get("nodes_visited", [])
    if "agent_node" not in nodes_visited:
        nodes_visited.append("agent_node")

    # ── PREP: answer immediately, no follow-up ─────────────────────
    if intent == "prep":
        i18n_dir  = os.path.join(os.path.dirname(__file__), "../i18n")
        lang_file = "fr.json" if language == "fr" else "en.json"
        with open(os.path.join(i18n_dir, lang_file)) as f:
            strings = json.load(f)

        prep_text  = strings["prep_instructions"].get(dept, "")
        dept_label = strings["departments"].get(dept, dept)
        prefix     = COMPLETION_MESSAGES["prep"][language].format(dept=dept_label, date=date)
        final      = f"{prefix}\n\n{prep_text}"

        print(f"[Agent] Prep instructions served for {dept} ({language.upper()})")
        masked_log = summarize_trace(
            nodes_visited=nodes_visited, intent=intent,
            risk_level="LOW", status="READY",
            patient_id=state.get("patient_id", ""),
            patient_name=patient_name,
        )
        return {
            **state,
            "draft_response":   final,
            "final_response":   final,
            "terminal_status":  "READY",
            "agent_conv_stage": "done",
            "human_approved":   False,
            "nodes_visited":    nodes_visited,
            "masked_log":       masked_log,
        }

    # ── RESCHEDULE: ask preferred date → execute ───────────────────
    if intent == "reschedule":
        if conv_stage == "ask" or not patient_reply:
            question = FOLLOWUP_QUESTIONS["reschedule"][language].format(
                dept=dept, date=date, time=time_str
            )
            print(f"[Agent] Asking reschedule follow-up")
            return {
                **state,
                "draft_response":   question,
                "final_response":   "",
                "terminal_status":  "NEED_INFO",
                "agent_conv_stage": "confirm",
                "nodes_visited":    nodes_visited,
            }
        else:
            parsed   = _parse_date_from_reply(patient_reply)
            new_date = parsed.get("date", "2026-04-01")
            new_time = parsed.get("time", "10:00")

            update_appointment(state.get("patient_id", ""), new_date, new_time)

            message = COMPLETION_MESSAGES["reschedule"][language].format(
                dept=dept.capitalize(), new_date=new_date, new_time=new_time
            )
            print(f"[Agent] Rescheduled to {new_date} at {new_time}")
            masked_log = summarize_trace(
                nodes_visited=nodes_visited, intent=intent,
                risk_level="LOW", status="READY",
                patient_id=state.get("patient_id", ""),
                patient_name=patient_name,
            )
            return {
                **state,
                "draft_response":    message,
                "final_response":    message,
                "terminal_status":   "READY",
                "agent_conv_stage":  "done",
                "appointment_details": {**appointment, "new_date": new_date, "new_time": new_time},
                "human_approved":    False,
                "nodes_visited":     nodes_visited,
                "masked_log":        masked_log,
            }

    # ── CANCEL: ask confirmation → execute ────────────────────────
    if intent == "cancel":
        if conv_stage == "ask" or not patient_reply:
            question = FOLLOWUP_QUESTIONS["cancel"][language].format(
                dept=dept, date=date, time=time_str
            )
            print(f"[Agent] Asking cancel confirmation")
            return {
                **state,
                "draft_response":   question,
                "final_response":   "",
                "terminal_status":  "NEED_INFO",
                "agent_conv_stage": "confirm",
                "nodes_visited":    nodes_visited,
            }
        else:
            confirmed = any(
                word in patient_reply.upper()
                for word in ["YES", "OUI", "CONFIRM", "OK", "SURE", "CANCEL", "ANNULER"]
            )
            if confirmed:
                cancel_appointment(state.get("patient_id", ""))
                message = COMPLETION_MESSAGES["cancel"][language].format(
                    dept=dept.capitalize(), date=date
                )
                print(f"[Agent] Appointment cancelled")
            else:
                message = (
                    "No problem! Your appointment has been kept as scheduled. Let us know if you need anything else."
                    if language == "en" else
                    "Pas de problème! Votre rendez-vous est maintenu. Contactez-nous si vous avez besoin d'aide."
                )

            masked_log = summarize_trace(
                nodes_visited=nodes_visited, intent=intent,
                risk_level="LOW", status="READY",
                patient_id=state.get("patient_id", ""),
                patient_name=patient_name,
            )
            return {
                **state,
                "draft_response":   message,
                "final_response":   message,
                "terminal_status":  "READY",
                "agent_conv_stage": "done",
                "human_approved":   False,
                "nodes_visited":    nodes_visited,
                "masked_log":       masked_log,
            }

    # ── NEW PATIENT: ask preferred date → save → confirm ──────────
    if intent == "new_patient":
        if conv_stage == "ask" or not patient_reply:
            # Stage 1: Ask for preferred date and time
            question = FOLLOWUP_QUESTIONS["new_patient"][language].format(
                name=patient_name,
                dept=dept.capitalize()
            )
            print(f"[Agent] Asking new patient for preferred appointment date")
            return {
                **state,
                "draft_response":   question,
                "final_response":   "",
                "terminal_status":  "NEED_INFO",
                "agent_conv_stage": "confirm",
                "nodes_visited":    nodes_visited,
            }
        else:
            # Stage 2: Parse preferred date, update DB, confirm booking
            parsed   = _parse_date_from_reply(patient_reply)
            new_date = parsed.get("date", "2026-04-01")
            new_time = parsed.get("time", "10:00")

            # Update the pending appointment with preferred date
            # Status stays 'pending' until staff confirms in the Staff Portal
            try:
                conn = get_connection()
                conn.execute(
                    "UPDATE appointments SET date = ?, time = ?, status = 'pending' WHERE patient_id = ?",
                    (new_date, new_time, state.get("patient_id", ""))
                )
                conn.commit()
                conn.close()
                print(f"[Agent] New patient date saved: {new_date} at {new_time} — awaiting staff confirmation")
            except Exception as e:
                print(f"[Agent] DB update error: {e}")

            if language == "fr":
                message = (
                    f"Merci, {patient_name}! Votre demande de rendez-vous a bien été enregistrée.\n\n"
                    f"Numéro de référence: {reference}\n"
                    f"Département: {dept.capitalize()}\n"
                    f"Date souhaitée: {new_date} à {new_time}\n"
                    f"Statut: En attente de confirmation du personnel\n\n"
                    f"Un membre de notre équipe confirmera votre rendez-vous sous peu."
                )
            else:
                message = (
                    f"Thank you, {patient_name}! Your appointment request has been saved.\n\n"
                    f"Reference Number: {reference}\n"
                    f"Department: {dept.capitalize()}\n"
                    f"Requested Date: {new_date} at {new_time}\n"
                    f"Status: Pending staff confirmation\n\n"
                    f"A member of our team will confirm your appointment shortly."
                )

            masked_log = summarize_trace(
                nodes_visited=nodes_visited, intent=intent,
                risk_level="LOW", status="READY",
                patient_id=state.get("patient_id", ""),
                patient_name=patient_name,
            )
            return {
                **state,
                "draft_response":    message,
                "final_response":    message,
                "terminal_status":   "READY",
                "agent_conv_stage":  "done",
                "appointment_details": {
                    **appointment,
                    "date":   new_date,
                    "time":   new_time,
                    "status": "pending",
                },
                "human_approved":    False,
                "nodes_visited":     nodes_visited,
                "masked_log":        masked_log,
            }

    # Fallback
    return {**state, "terminal_status": "NEED_INFO", "nodes_visited": nodes_visited}