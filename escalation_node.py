"""
nodes/escalation_node.py — Handles HIGH risk / emergency situations.

Middleware applied:
  - SummarizationMiddleware → generates masked audit log
  - PIIMiddleware           → patient info masked in log

This node does NOT call the LLM. It returns a hardcoded safe emergency
message and directs the patient to 911 / emergency services immediately.
No HITL review — emergency responses are sent instantly.
"""

from medic_aid.middleware.middleware import summarize_trace

EMERGENCY_RESPONSE = {
    "en": (
        "⚠️ MEDIC-AID ALERT: Based on your message, this may be a medical emergency. "
        "Please call 911 immediately or go to your nearest emergency room. "
        "Do NOT wait for an appointment. Our staff has been notified."
    ),
    "fr": (
        "⚠️ ALERTE MEDIC-AID: D'après votre message, il pourrait s'agir d'une urgence médicale. "
        "Veuillez appeler le 911 immédiatement ou vous rendre aux urgences les plus proches. "
        "N'attendez PAS un rendez-vous. Notre personnel a été informé."
    ),
}


def escalation_node(state: dict) -> dict:
    """Handles emergency/high-risk cases with immediate hardcoded safe response."""

    language = state.get("language", "en")
    response = EMERGENCY_RESPONSE.get(language, EMERGENCY_RESPONSE["en"])

    print("🚨 [ESCALATION] Emergency response issued — no HITL required.")

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("escalation_node")

    # SummarizationMiddleware — build PII-safe audit log
    masked_log = summarize_trace(
        nodes_visited=nodes_visited,
        intent=state.get("intent", "emergency"),
        risk_level="HIGH",
        status="ESCALATE",
        patient_id=state.get("patient_id", ""),
        patient_name=state.get("patient_name", ""),
    )

    return {
        **state,
        "draft_response":  response,
        "final_response":  response,
        "terminal_status": "ESCALATE",
        "human_approved":  False,
        "human_edited":    False,
        "masked_log":      masked_log,
        "nodes_visited":   nodes_visited,
    }