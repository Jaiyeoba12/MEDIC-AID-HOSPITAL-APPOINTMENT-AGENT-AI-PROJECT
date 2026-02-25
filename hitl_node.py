"""
nodes/hitl_node.py — Human-in-the-Loop (HITL) review node.

Middleware applied:
  - HumanInTheLoopMiddleware  → pauses workflow for staff approve/edit
  - ContextEditingMiddleware  → allows staff to modify the draft response
  - SummarizationMiddleware   → generates final masked audit log
  - PIIMiddleware             → patient info masked in log

In CLI mode: prompts the reviewer in the terminal.
In Streamlit mode: the UI handles HITL directly — this node is bypassed.
"""

from medic_aid.middleware.middleware import summarize_trace


def hitl_node(state: dict) -> dict:
    """
    CLI Human-in-the-Loop: pauses for staff to approve or edit the draft.

    HumanInTheLoopMiddleware: pauses execution and waits for human input.
    ContextEditingMiddleware: allows the reviewer to rewrite the draft before sending.
    """

    print("\n" + "="*60)
    print("👤 [HumanInTheLoopMiddleware] — Medic-Aid Staff Review Portal")
    print("="*60)
    print(f"\n  Patient ID   : {state.get('patient_id')}")
    print(f"  Department   : {state.get('department', '').upper()}")
    print(f"  Intent       : {state.get('intent', '').upper()}")
    print(f"  Risk Level   : {state.get('risk_level', '')}")
    print(f"\n📝 DRAFT RESPONSE:\n")
    print(f"  {state.get('draft_response', '')}")
    print("\n" + "-"*60)
    print("  [A] Approve and send as-is")
    print("  [E] Edit the response before sending  ← ContextEditingMiddleware")
    print("-"*60)

    choice = input("Your choice (A/E): ").strip().upper()
    human_edited = False

    if choice == "E":
        # ContextEditingMiddleware — reviewer rewrites the draft
        print("\n[ContextEditingMiddleware] Enter your edited response (blank line to finish):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        final_response = "\n".join(lines)
        human_edited   = True
        print("✅ [ContextEditingMiddleware] Edited response saved.")
    else:
        final_response = state.get("draft_response", "")
        print("✅ [HumanInTheLoopMiddleware] Response approved as-is.")

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("hitl_node")

    # SummarizationMiddleware + PIIMiddleware — final audit log
    masked_log = summarize_trace(
        nodes_visited=nodes_visited,
        intent=state.get("intent", "unknown"),
        risk_level=state.get("risk_level", "LOW"),
        status="READY",
        patient_id=state.get("patient_id", ""),
        patient_name=state.get("patient_name", ""),
    )

    return {
        **state,
        "final_response":  final_response,
        "terminal_status": "READY",
        "human_approved":  True,
        "human_edited":    human_edited,
        "masked_log":      masked_log,
        "nodes_visited":   nodes_visited,
    }