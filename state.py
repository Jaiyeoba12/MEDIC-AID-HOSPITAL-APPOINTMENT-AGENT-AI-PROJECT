"""
state.py — The shared notebook carried through the entire workflow.

Every node reads from and writes to this state dictionary.
New fields added for agent conversation loop (LOW risk autonomous handling).
"""

from typing import TypedDict, Optional


class AppointmentState(TypedDict):
    # ── Patient Input ──────────────────────────────────────────────
    patient_id:   str
    patient_name: str
    raw_message:  str
    language:     str
    department:   str

    # ── Workflow Decisions ─────────────────────────────────────────
    intent:          str    # reschedule | cancel | prep | new_patient | emergency | unknown
    risk_level:      str    # LOW | MEDIUM | HIGH
    terminal_status: str    # READY | NEED_INFO | ESCALATE

    # ── Database Result ────────────────────────────────────────────
    appointment_found:   bool
    appointment_details: dict

    # ── Responses ──────────────────────────────────────────────────
    draft_response: str   # Agent/AI generated response
    final_response: str   # Final response sent to patient

    # ── Agent Conversation Loop (LOW risk only) ────────────────────
    agent_conv_stage:    str   # "ask" | "confirm" | "done"
    agent_patient_reply: str   # Patient's answer to agent follow-up question

    # ── Audit Trail ────────────────────────────────────────────────
    run_id:        str
    nodes_visited: list
    masked_log:    str

    # ── HITL (MEDIUM / HIGH risk only) ────────────────────────────
    human_approved: bool
    human_edited:   bool