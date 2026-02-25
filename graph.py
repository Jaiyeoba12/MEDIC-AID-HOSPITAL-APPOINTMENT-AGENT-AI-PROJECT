"""
graph.py — The LangGraph workflow for Medic-Aid.

Risk-based routing:
  LOW    → 🤖 Agent handles autonomously (agent_node)
             - Asks follow-up questions
             - Confirms before acting
             - Explains what it did
  MEDIUM → 👤 Human reviews via HITL
  HIGH   → 🚨 Immediate escalation (no AI, no HITL)

Full flow:
  language_detector → intent_classifier → risk_evaluator
       ↓                    ↓                   ↓
      LOW                MEDIUM               HIGH
       ↓                    ↓                   ↓
   db_lookup           need_info_node      escalation_node
  ↓        ↓
FOUND    NOT FOUND
  ↓          ↓
response   new_patient
_drafter    _node
  ↓          ↓
agent_node ←─┘   ← handles autonomously
"""

import uuid
from datetime import datetime
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

from medic_aid.state import AppointmentState
from medic_aid.nodes.language_detector  import language_detector
from medic_aid.nodes.intent_classifier  import intent_classifier
from medic_aid.nodes.risk_evaluator     import risk_evaluator
from medic_aid.nodes.db_lookup          import db_lookup
from medic_aid.nodes.new_patient_node   import new_patient_node
from medic_aid.nodes.response_drafter   import response_drafter
from medic_aid.nodes.agent_node         import agent_node
from medic_aid.nodes.hitl_node          import hitl_node
from medic_aid.nodes.escalation_node    import escalation_node
from medic_aid.nodes.need_info_node     import need_info_node
from medic_aid.middleware.middleware    import call_tracker

load_dotenv()


def route_after_risk(state: dict) -> str:
    """
    Main routing decision after risk evaluation.
      HIGH        → immediate escalation
      MEDIUM      → human review (HITL)
      LOW + new   → new_patient_node directly (no DB lookup needed)
      LOW         → db_lookup for existing patients
    """
    risk   = state.get("risk_level", "LOW")
    intent = state.get("intent", "")

    if risk == "HIGH":
        return "escalation_node"
    elif risk == "MEDIUM":
        return "need_info_node"
    elif intent == "new_patient":
        return "new_patient_node"   # Skip DB lookup — they are new
    else:
        return "db_lookup"


def route_after_db(state: dict) -> str:
    """Routes based on whether appointment was found."""
    if state.get("appointment_found", False):
        return "response_drafter"
    else:
        return "new_patient_node"


def build_graph(include_hitl: bool = True) -> StateGraph:
    """Builds and compiles the LangGraph workflow."""

    graph = StateGraph(AppointmentState)

    # ── Add all nodes ──────────────────────────────────────────────
    graph.add_node("language_detector",  language_detector)
    graph.add_node("intent_classifier",  intent_classifier)
    graph.add_node("risk_evaluator",     risk_evaluator)
    graph.add_node("db_lookup",          db_lookup)
    graph.add_node("new_patient_node",   new_patient_node)
    graph.add_node("response_drafter",   response_drafter)
    graph.add_node("agent_node",         agent_node)    # LOW risk autonomous handler
    graph.add_node("escalation_node",    escalation_node)
    graph.add_node("need_info_node",     need_info_node)

    if include_hitl:
        graph.add_node("hitl_node", hitl_node)

    # ── Edges ──────────────────────────────────────────────────────
    graph.set_entry_point("language_detector")
    graph.add_edge("language_detector", "intent_classifier")
    graph.add_edge("intent_classifier", "risk_evaluator")

    # Risk-based fork
    graph.add_conditional_edges(
        "risk_evaluator",
        route_after_risk,
        {
            "escalation_node": "escalation_node",
            "need_info_node":  "need_info_node",
            "new_patient_node":"new_patient_node",
            "db_lookup":       "db_lookup",
        }
    )

    # DB lookup fork
    graph.add_conditional_edges(
        "db_lookup",
        route_after_db,
        {
            "response_drafter": "response_drafter",
            "new_patient_node": "new_patient_node",
        }
    )

    # LOW risk → agent handles autonomously (no HITL)
    graph.add_edge("response_drafter",  "agent_node")
    graph.add_edge("new_patient_node",  "agent_node")
    graph.add_edge("agent_node",        END)

    # MEDIUM risk → HITL (CLI only) or END (Streamlit handles it)
    if include_hitl:
        graph.add_edge("need_info_node", "hitl_node")
        graph.add_edge("hitl_node",      END)
    else:
        graph.add_edge("need_info_node", END)

    graph.add_edge("escalation_node", END)

    return graph.compile()


def run_workflow(
    patient_id:          str,
    patient_name:        str,
    raw_message:         str,
    department:          str,
    include_hitl:        bool = True,
    agent_patient_reply: str  = "",
    agent_conv_stage:    str  = "ask",
) -> dict:
    """
    Main entry point to run the Medic-Aid workflow.

    For agent follow-up conversations (LOW risk):
      - First call:  agent_patient_reply="" , agent_conv_stage="ask"
      - Second call: agent_patient_reply="March 20 at 2pm", agent_conv_stage="confirm"
    """
    call_tracker.call_count = 0

    run_id = f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

    initial_state: AppointmentState = {
        "patient_id":          patient_id,
        "patient_name":        patient_name,
        "raw_message":         raw_message,
        "language":            "en",
        "department":          department,
        "intent":              "",
        "risk_level":          "",
        "terminal_status":     "",
        "appointment_found":   False,
        "appointment_details": {},
        "draft_response":      "",
        "final_response":      "",
        "agent_conv_stage":    agent_conv_stage,
        "agent_patient_reply": agent_patient_reply,
        "run_id":              run_id,
        "nodes_visited":       [],
        "masked_log":          "",
        "human_approved":      False,
        "human_edited":        False,
    }

    print(f"\n🏥 Medic-Aid — Run ID: {run_id}")
    print(f"📨 Patient: {patient_id} | Message: {raw_message[:60]}...")
    print("-" * 60)

    graph  = build_graph(include_hitl=include_hitl)
    result = graph.invoke(initial_state)
    return result