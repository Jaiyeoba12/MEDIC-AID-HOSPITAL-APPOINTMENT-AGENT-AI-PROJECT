"""
nodes/need_info_node.py — Handles cases where we need more information.

Middleware applied:
  - SummarizationMiddleware → generates masked audit log
  - PIIMiddleware           → patient info masked in log

Triggered when intent is 'unknown' or appointment is not found.
Returns a bilingual NEED_INFO status asking the patient to clarify.
"""

from medic_aid.middleware.middleware import summarize_trace

NEED_INFO_RESPONSE = {
    "en": (
        "Thank you for reaching out to Medic-Aid. We weren't able to fully understand "
        "your request or locate your appointment. Could you please provide your Patient ID "
        "and clarify whether you'd like to reschedule, cancel, or get preparation instructions?"
    ),
    "fr": (
        "Merci de contacter Medic-Aid. Nous n'avons pas pu comprendre votre demande "
        "ou trouver votre rendez-vous. Pourriez-vous fournir votre identifiant patient "
        "et préciser si vous souhaitez reprogrammer, annuler ou obtenir des instructions de préparation?"
    ),
}


def need_info_node(state: dict) -> dict:
    """Returns a bilingual response asking the patient for more information."""

    language = state.get("language", "en")
    response = NEED_INFO_RESPONSE.get(language, NEED_INFO_RESPONSE["en"])

    print("ℹ️  [NEED_INFO] Requesting clarification from patient.")

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("need_info_node")

    # SummarizationMiddleware — build PII-safe audit log
    masked_log = summarize_trace(
        nodes_visited=nodes_visited,
        intent=state.get("intent", "unknown"),
        risk_level=state.get("risk_level", "MEDIUM"),
        status="NEED_INFO",
        patient_id=state.get("patient_id", ""),
        patient_name=state.get("patient_name", ""),
    )

    return {
        **state,
        "draft_response":  response,
        "final_response":  response,
        "terminal_status": "NEED_INFO",
        "human_approved":  False,
        "human_edited":    False,
        "masked_log":      masked_log,
        "nodes_visited":   nodes_visited,
    }