"""
nodes/db_lookup.py — Looks up the patient's appointment in the database.

Two outcomes:
  1. Patient FOUND     → perform the requested action (reschedule/cancel/prep)
  2. Patient NOT FOUND → route to new_patient_node for registration

This node is only reached for LOW risk requests.
"""

from medic_aid.database.setup import get_appointment, cancel_appointment, update_appointment

DEFAULT_NEW_DATE = "2026-04-01"
DEFAULT_NEW_TIME = "10:00"


def db_lookup(state: dict) -> dict:
    """Looks up appointment and performs DB action based on intent."""

    patient_id = state.get("patient_id", "")
    intent     = state.get("intent", "")

    appointment = get_appointment(patient_id)

    if not appointment:
        print(f"🆕 Patient {patient_id} not found — routing to new patient registration.")
        nodes_visited = state.get("nodes_visited", [])
        nodes_visited.append("db_lookup")
        return {
            **state,
            "appointment_found":   False,
            "appointment_details": {},
            "nodes_visited":       nodes_visited,
        }

    print(f"✅ Appointment found: {appointment['department']} on {appointment['date']}")

    # Perform the DB action based on intent
    if intent == "cancel":
        cancel_appointment(patient_id)
        appointment["status"] = "cancelled"

    elif intent == "reschedule":
        update_appointment(patient_id, DEFAULT_NEW_DATE, DEFAULT_NEW_TIME)
        appointment["new_date"] = DEFAULT_NEW_DATE
        appointment["new_time"] = DEFAULT_NEW_TIME

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("db_lookup")

    return {
        **state,
        "appointment_found":   True,
        "appointment_details": appointment,
        "nodes_visited":       nodes_visited,
    }