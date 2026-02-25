"""
nodes/new_patient_node.py — Handles first-time / unrecognized patients.

When a patient ID is not found in the database, instead of just returning
NEED_INFO, this node:
  1. Registers them in the DB with status = 'pending'
  2. Generates a unique reference number
  3. Prepares their details for HITL staff review

Middleware applied:
  - PIIMiddleware           -> patient info masked in logs
  - SummarizationMiddleware -> audit log generated
"""

import uuid
from datetime import datetime
from medic_aid.database.setup import get_connection
from medic_aid.middleware.middleware import summarize_trace


def register_new_patient(patient_id, patient_name, department, reference):
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO appointments
            (patient_id, patient_name, department, date, time, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (patient_id, patient_name, department, "2026-03-10", "09:00"))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Warning: {e}")
        return False
    finally:
        conn.close()


def new_patient_node(state: dict) -> dict:
    patient_id   = state.get("patient_id", "")
    patient_name = state.get("patient_name", "")
    department   = state.get("department", "general")
    language     = state.get("language", "en")

    reference = f"REF-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    register_new_patient(patient_id, patient_name, department, reference)

    print(f"New patient registered: {patient_id} | Ref: {reference}")

    if language == "fr":
        draft = (
            f"Bienvenue chez Medic-Aid, {patient_name}!\n\n"
            f"Votre demande d'inscription a ete recue.\n"
            f"Reference: {reference}\n"
            f"Departement: {department.capitalize()}\n"
            f"Statut: En attente de confirmation du personnel."
        )
    else:
        draft = (
            f"Welcome to Medic-Aid, {patient_name}!\n\n"
            f"Your registration request has been received.\n"
            f"Reference Number: {reference}\n"
            f"Department: {department.capitalize()}\n"
            f"Status: Pending staff confirmation."
        )

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("new_patient_node")

    masked_log = summarize_trace(
        nodes_visited=nodes_visited,
        intent="new_patient_registration",
        risk_level="LOW",
        status="READY",
        patient_id=patient_id,
        patient_name=patient_name,
    )

    return {
        **state,
        "intent":              "new_patient",
        "risk_level":          "LOW",
        "terminal_status":     "READY",
        "appointment_found":   True,
        "appointment_details": {
            "patient_id":   patient_id,
            "patient_name": patient_name,
            "department":   department,
            "date":         "Pending confirmation",
            "time":         "Pending confirmation",
            "status":       "pending",
            "reference":    reference,
        },
        "draft_response":  draft,
        "masked_log":      masked_log,
        "nodes_visited":   nodes_visited,
    }
