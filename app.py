"""
app.py — Streamlit Web UI for Medic-Aid.

Two portals:
  - 👤 Patient Portal  : patients submit appointment requests
  - 🔐 Staff Portal    : staff login (password: admin123) to review HITL,
                         view pending appointments, and approve new patients
"""

import streamlit as st
import json
import os
import sqlite3
from dotenv import load_dotenv
from medic_aid.database.setup import setup_database, seed_database, get_connection
from medic_aid.graph import run_workflow
from medic_aid.middleware.middleware import summarize_trace

load_dotenv()

# ── Load hospital directory ────────────────────────────────────────
DIRECTORY_PATH = os.path.join(os.path.dirname(__file__), "medic_aid/i18n/directory.json")
with open(DIRECTORY_PATH, "r") as f:
    HOSPITAL_DIRECTORY = json.load(f)

STAFF_PASSWORD = "admin123"

# ── Page config ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Medic-Aid | Hospital Assistant",
    page_icon="🏥",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;600;700&family=DM+Mono&display=swap');
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
  .main { background-color: #f0f4f8; }

  .medic-header {
    background: linear-gradient(135deg, #1a3a5c 0%, #2563eb 100%);
    color: white; padding: 2rem 2.5rem; border-radius: 16px; margin-bottom: 1.5rem;
  }
  .medic-header h1 { font-size: 2.2rem; font-weight: 700; margin: 0; }
  .medic-header p  { opacity: 0.85; margin: 0.3rem 0 0; font-size: 1rem; }

  .staff-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #1d4ed8 50%, #7c3aed 100%);
    color: white; padding: 2rem 2.5rem; border-radius: 16px; margin-bottom: 1.5rem;
  }
  .staff-header h1 { font-size: 2.2rem; font-weight: 700; margin: 0; }
  .staff-header p  { opacity: 0.85; margin: 0.3rem 0 0; font-size: 1rem; }

  .status-badge {
    display: inline-block; padding: 0.4rem 1rem; border-radius: 999px;
    font-weight: 700; font-size: 1rem; letter-spacing: 0.05em;
  }
  .status-READY     { background: #d1fae5; color: #065f46; }
  .status-NEED_INFO { background: #fef3c7; color: #92400e; }
  .status-ESCALATE  { background: #fee2e2; color: #991b1b; }

  .node-pill {
    display: inline-block; background: #eff6ff; color: #1d4ed8;
    border: 1px solid #bfdbfe; padding: 0.2rem 0.7rem; border-radius: 999px;
    font-size: 0.78rem; font-family: 'DM Mono', monospace; margin: 2px;
  }
  .dept-badge {
    background: #ede9fe; color: #5b21b6; padding: 0.15rem 0.6rem;
    border-radius: 6px; font-size: 0.85rem; font-weight: 600;
  }
  .run-id { font-family: 'DM Mono', monospace; font-size: 0.82rem; color: #64748b; }

  .patient-card {
    background: white; border-radius: 12px; padding: 1rem 1.2rem;
    margin-bottom: 0.8rem; border-left: 4px solid #2563eb;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  }
  .new-badge {
    background: #fef9c3; color: #854d0e; padding: 0.15rem 0.6rem;
    border-radius: 6px; font-size: 0.8rem; font-weight: 700;
  }
</style>
""", unsafe_allow_html=True)

# ── Initialize DB ──────────────────────────────────────────────────
setup_database()
seed_database()


# ── Helper: Hospital Directory Card ───────────────────────────────
def show_directory_card(department: str, language: str):
    info = HOSPITAL_DIRECTORY.get(department, {}).get(language, {})
    if not info:
        return
    st.markdown("---")
    st.markdown("### 🗺️ Hospital Directory & Navigation")
    st.markdown(
        f"<div style='background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;"
        f"padding:1.2rem;margin-bottom:0.5rem;'>"
        f"<h4 style='margin:0 0 0.5rem;color:#0369a1;'>📍 {info.get('floor')} &nbsp;·&nbsp; {info.get('room')}</h4>"
        f"<p style='margin:0;color:#0c4a6e;'>🚪 <b>Entrance:</b> {info.get('entrance')}</p>"
        f"</div>",
        unsafe_allow_html=True
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**{info.get('parking')}**")
        st.markdown(f"**🛗 Directions:** {info.get('elevator')}")
    with col2:
        st.markdown(f"**{info.get('accessibility')}**")
        st.markdown(f"**{info.get('arrival_tip')}**")
    st.info(info.get('contact'))


# ── Helper: Get all pending appointments from DB ───────────────────
def get_pending_appointments() -> list:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM appointments WHERE status IN ('pending', 'confirmed', 'rescheduled', 'cancelled') ORDER BY date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_new_patients() -> list:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM appointments WHERE status = 'pending' ORDER BY date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def confirm_patient(patient_id: str):
    conn = get_connection()
    conn.execute("UPDATE appointments SET status = 'confirmed' WHERE patient_id = ?", (patient_id,))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════
# MAIN APP — Portal Selection
# ══════════════════════════════════════════════════════════════════

# Header
st.markdown("""
<div class="medic-header">
  <h1>🏥 Medic-Aid</h1>
  <p>Intelligent Hospital Appointment Assistant &nbsp;·&nbsp; Powered by LangGraph + GPT-4o-mini</p>
</div>
""", unsafe_allow_html=True)

# Portal tabs
portal = st.tabs(["👤 Patient Portal", "🔐 Staff Portal"])


# ══════════════════════════════════════════════════════════════════
# TAB 1 — PATIENT PORTAL
# ══════════════════════════════════════════════════════════════════
with portal[0]:
    col_left, col_right = st.columns([1, 1.4], gap="large")

    with col_left:
        st.markdown("### 📋 Submit Your Request")

        lang    = st.radio("🌍 Language", ["English 🇨🇦", "Français 🇫🇷"], horizontal=True)
        ui_lang = "fr" if "Français" in lang else "en"

        st.markdown("---")

        patient_id   = st.text_input(
            "Patient ID" if ui_lang == "en" else "ID Patient",
            placeholder=(
                "e.g. P001 (new patients: use a new ID like P011)"
                if ui_lang == "en" else
                "ex: P001 (nouveau patient: utilisez un nouvel ID comme P011)"
            ),
            help=(
                "Use P001–P010 for existing demo patients. Use a new ID like P011 to register as a new patient."
                if ui_lang == "en" else
                "Utilisez P001–P010 pour les patients existants. Utilisez un nouvel ID comme P011 pour vous inscrire."
            ),
        )
        patient_name = st.text_input(
            "Full Name" if ui_lang == "en" else "Nom complet",
            placeholder="e.g. Alice Martin"
        )

        dept_options = {
            "en": {"cardiology": "❤️ Cardiology", "radiology": "🔬 Imaging & Radiology",
                   "dental": "🦷 Dental", "general": "🩺 General Practice", "orthopedics": "🦴 Orthopedics"},
            "fr": {"cardiology": "❤️ Cardiologie", "radiology": "🔬 Imagerie & Radiologie",
                   "dental": "🦷 Dentisterie", "general": "🩺 Médecine Générale", "orthopedics": "🦴 Orthopédie"}
        }
        dept_display        = list(dept_options[ui_lang].values())
        dept_keys           = list(dept_options[ui_lang].keys())
        selected_dept_label = st.selectbox("Department" if ui_lang == "en" else "Département", dept_display)
        department          = dept_keys[dept_display.index(selected_dept_label)]

        message = st.text_area(
            "Your message" if ui_lang == "en" else "Votre message",
            placeholder=(
                "e.g. I need to reschedule / How do I prepare? / I have chest pains"
                if ui_lang == "en" else
                "ex: Je veux reprogrammer / Comment me préparer? / J'ai des douleurs thoraciques"
            ),
            height=120
        )

        st.info(
            "💡 **Existing patients:** Use IDs P001–P010\n\n"
            "💡 **New patient?** Use a new ID (e.g. P011) and your name\n\n"
            "🚨 **Emergency test:** Type *'I have severe chest pain'*"
            if ui_lang == "en" else
            "💡 **Patients existants:** IDs P001–P010\n\n"
            "💡 **Nouveau patient?** Utilisez un nouvel ID (ex: P011)\n\n"
            "🚨 **Test urgence:** Tapez *'J'ai des douleurs thoraciques sévères'*"
        )

        submit_btn = st.button(
            "🚀 Submit Request" if ui_lang == "en" else "🚀 Soumettre",
            type="primary", use_container_width=True,
            disabled=not (patient_id and patient_name and message),
        )

    with col_right:
        st.markdown("### 🔄 Workflow & Results")

        if submit_btn:
            with st.spinner("Processing through Medic-Aid workflow..."):
                result = run_workflow(
                    patient_id=patient_id,
                    patient_name=patient_name,
                    raw_message=message,
                    department=department,
                    include_hitl=False,
                    agent_conv_stage="ask",
                    agent_patient_reply="",
                )
                st.session_state["p_result"]     = result
                st.session_state["p_department"] = department
                st.session_state["p_ui_lang"]    = ui_lang
                st.session_state["p_patient_id"]   = patient_id
                st.session_state["p_patient_name"] = patient_name

                risk  = result.get("risk_level", "")
                stage = result.get("agent_conv_stage", "done")

                if risk == "LOW" and stage == "confirm":
                    st.session_state["p_stage"] = "agent_followup"
                elif risk == "MEDIUM":
                    st.session_state["p_stage"] = "staff_review"
                else:
                    st.session_state["p_stage"] = "done"

        if "p_result" in st.session_state:
            result     = st.session_state["p_result"]
            stage      = st.session_state.get("p_stage", "done")
            ui_lang    = st.session_state.get("p_ui_lang", "en")
            department = st.session_state.get("p_department", "general")

            # Workflow trace
            st.markdown("**📍 Workflow Path**")
            nodes = result.get("nodes_visited", [])
            pills = " <span style='color:#94a3b8'>→</span> ".join(
                f"<span class='node-pill'>{n}</span>" for n in nodes
            )
            st.markdown(f"<div style='margin-bottom:1rem'>{pills}</div>", unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Status",     result.get("terminal_status", ""))
            with c2: st.metric("Risk Level", result.get("risk_level", "—"))
            with c3: st.metric("Intent",     result.get("intent", "—").upper())

            st.markdown(f"<span class='run-id'>Run ID: {result.get('run_id')}</span>", unsafe_allow_html=True)
            st.markdown("---")

            # ── Agent Follow-up (LOW risk) ──────────────────────────
            if stage == "agent_followup":
                st.markdown("### 🤖 Agent Follow-up Question")
                st.info(result.get("draft_response", ""))

                followup_reply = st.text_input(
                    "Your reply" if ui_lang == "en" else "Votre réponse",
                    placeholder=(
                        "e.g. March 20 at 2pm / YES"
                        if ui_lang == "en" else
                        "ex: 20 mars à 14h / OUI"
                    ),
                    key="agent_reply_input"
                )

                if st.button(
                    "📨 Send Reply" if ui_lang == "en" else "📨 Envoyer",
                    type="primary", use_container_width=True,
                    disabled=not followup_reply
                ):
                    with st.spinner("Agent processing your reply..."):
                        result2 = run_workflow(
                            patient_id=st.session_state.get("p_patient_id",""),
                            patient_name=st.session_state.get("p_patient_name",""),
                            raw_message=result.get("raw_message",""),
                            department=st.session_state.get("p_department","general"),
                            include_hitl=False,
                            agent_conv_stage="confirm",
                            agent_patient_reply=followup_reply,
                        )
                        st.session_state["p_result"] = result2
                        st.session_state["p_stage"]  = "done"
                        st.rerun()

            # ── Staff Review Notice (MEDIUM risk) ──────────────────
            elif stage == "staff_review":
                st.markdown("### ⏳ Request Sent for Staff Review")
                st.warning(
                    "Your request requires staff attention and has been forwarded "
                    "to our team. You will be contacted shortly."
                    if ui_lang == "en" else
                    "Votre demande nécessite l'attention du personnel et a été transmise "
                    "à notre équipe. Vous serez contacté sous peu."
                )
                st.caption(f"📋 Reference: {result.get('run_id')}")
                if "staff_queue" not in st.session_state:
                    st.session_state["staff_queue"] = []
                st.session_state["staff_queue"].append(result)
                st.session_state["p_stage"] = "done"

            elif stage == "done":
                final_status   = result.get("terminal_status", "")
                final_response = result.get("final_response") or result.get("draft_response", "")

                st.markdown(
                    f"**Status:** <span class='status-badge status-{final_status}'>{final_status}</span>",
                    unsafe_allow_html=True
                )
                st.markdown("<br>", unsafe_allow_html=True)

                if final_status == "ESCALATE":
                    st.error(final_response)
                elif final_status == "NEED_INFO":
                    st.warning(final_response)
                else:
                    st.success(final_response)

                # Appointment record
                if result.get("appointment_found") and result.get("appointment_details"):
                    appt       = result["appointment_details"]
                    is_new     = appt.get("status") == "pending"
                    intent_val = result.get("intent", "")
                    st.markdown("---")
                    if is_new or intent_val == "new_patient":
                        st.markdown("**🆕 New Patient Registration**")
                        st.info(
                            f"📋 **Reference:** {appt.get('reference', 'N/A')}  \n"
                            f"🏥 **Department:** {appt.get('department','').capitalize()}  \n"
                            f"⏳ **Status:** Pending staff confirmation  \n"
                            f"👤 **Patient ID:** {appt.get('patient_id', '')}"
                        )
                    else:
                        st.markdown("**📅 Appointment Record**")
                        a1, a2, a3 = st.columns(3)
                        with a1: st.markdown(f"**Dept:** <span class='dept-badge'>{appt.get('department','')}</span>", unsafe_allow_html=True)
                        with a2: st.markdown(f"**Date:** {appt.get('date','')}")
                        with a3: st.markdown(f"**Status:** {appt.get('status','')}")

                if final_status != "ESCALATE":
                    show_directory_card(department, ui_lang)

                with st.expander("🔒 Masked Audit Log (PII-Safe)"):
                    st.code(result.get("masked_log", "No log generated."), language="text")

        else:
            _lang = st.session_state.get("p_ui_lang", "en")
            _line1 = "Soumettez une demande pour voir le système en action." if _lang == "fr" else "Submit a request to see the workflow in action."
            _line2 = "Reprogrammer · Annuler · Instructions · Nouveau patient · Urgence" if _lang == "fr" else "Reschedule · Cancel · Prep Instructions · New Patient · Emergency"
            st.markdown(f"""
            <div style='text-align:center;padding:4rem 2rem;color:#94a3b8;'>
                <div style='font-size:3rem;'>🏥</div>
                <p style='font-size:1.1rem;margin-top:1rem;'>{_line1}</p>
                <p style='font-size:0.9rem;'>{_line2}</p>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# TAB 2 — STAFF PORTAL
# ══════════════════════════════════════════════════════════════════
with portal[1]:

    # ── Login ──────────────────────────────────────────────────────
    if not st.session_state.get("staff_logged_in", False):
        st.markdown("""
        <div class="staff-header">
          <h1>🔐 Staff Portal</h1>
          <p>Medic-Aid Internal Dashboard — Authorized Personnel Only</p>
        </div>
        """, unsafe_allow_html=True)

        col_login, _ = st.columns([1, 2])
        with col_login:
            st.markdown("### Login")
            password = st.text_input("Staff Password", type="password", placeholder="Enter password")
            if st.button("🔓 Login", type="primary", use_container_width=True):
                if password == STAFF_PASSWORD:
                    st.session_state["staff_logged_in"] = True
                    st.rerun()
                else:
                    st.error("❌ Incorrect password. Please try again.")
            st.caption("Demo password: `admin123`")

    # ── Staff Dashboard ────────────────────────────────────────────
    else:
        st.markdown("""
        <div class="staff-header">
          <h1>🔐 Staff Portal</h1>
          <p>Medic-Aid Internal Dashboard &nbsp;·&nbsp; Welcome back!</p>
        </div>
        """, unsafe_allow_html=True)

        # Logout button
        if st.button("🚪 Logout", use_container_width=False):
            st.session_state["staff_logged_in"] = False
            st.rerun()

        # Staff sub-tabs
        tab_hitl, tab_pending, tab_new = st.tabs([
            "👤 HITL Review Queue",
            "📅 All Appointments",
            "🆕 New Patient Registrations",
        ])

        # ── HITL Review Queue ──────────────────────────────────────
        with tab_hitl:
            st.markdown("### 👤 Human-in-the-Loop Review Queue")
            st.caption("Review AI-generated drafts and approve or edit before sending to patients.")

            queue = st.session_state.get("staff_queue", [])

            if not queue:
                st.info("✅ No pending reviews. All caught up!")
            else:
                st.markdown(f"**{len(queue)} request(s) awaiting review**")

                for i, item in enumerate(queue):
                    with st.expander(
                        f"📋 {item.get('run_id')} | {item.get('intent','').upper()} | "
                        f"Patient: {item.get('patient_id')} | Dept: {item.get('department','')}",
                        expanded=(i == 0)
                    ):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown(f"**Patient ID:** {item.get('patient_id')}")
                            st.markdown(f"**Name:** {item.get('patient_name')}")
                            st.markdown(f"**Department:** {item.get('department','').capitalize()}")
                        with col_b:
                            st.markdown(f"**Intent:** {item.get('intent','').upper()}")
                            st.markdown(f"**Risk:** {item.get('risk_level','')}")
                            st.markdown(f"**Language:** {'French 🇫🇷' if item.get('language') == 'fr' else 'English 🇨🇦'}")

                        st.markdown("---")
                        st.markdown("**📝 Patient Message:**")
                        st.code(item.get("raw_message", ""), language="text")

                        draft = item.get("draft_response", "")
                        edited = st.text_area(
                            "✏️ Draft Response (edit if needed)",
                            value=draft,
                            height=150,
                            key=f"edit_{i}"
                        )

                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if st.button("✅ Approve & Send", type="primary",
                                         use_container_width=True, key=f"approve_{i}"):
                                queue[i]["final_response"] = edited
                                queue[i]["human_approved"] = True
                                queue[i]["human_edited"]   = (edited != draft)
                                # Confirm new patient in DB if applicable
                                if item.get("intent") == "new_patient":
                                    confirm_patient(item.get("patient_id", ""))
                                st.session_state["staff_queue"] = [
                                    q for j, q in enumerate(queue) if j != i
                                ]
                                st.success(f"✅ Response approved and sent for {item.get('patient_id')}!")
                                st.rerun()
                        with btn_col2:
                            if st.button("❌ Reject", use_container_width=True, key=f"reject_{i}"):
                                st.session_state["staff_queue"] = [
                                    q for j, q in enumerate(queue) if j != i
                                ]
                                st.warning(f"Request from {item.get('patient_id')} rejected.")
                                st.rerun()

        # ── All Appointments ───────────────────────────────────────
        with tab_pending:
            st.markdown("### 📅 All Appointments")
            st.caption("Complete list of all patient appointments in the system.")

            col_ref1, col_ref2 = st.columns([1, 5])
            with col_ref1:
                if st.button("🔄 Refresh", key="refresh_pending"):
                    st.rerun()
            with col_ref2:
                st.caption("Click Refresh to see the latest registrations from the Patient Portal.")

            appointments = get_pending_appointments()

            if not appointments:
                st.info("No appointments found in the database.")
            else:
                # Status filter
                status_filter = st.selectbox(
                    "Filter by status",
                    ["All", "confirmed", "pending", "rescheduled", "cancelled"]
                )

                filtered = appointments if status_filter == "All" else [
                    a for a in appointments if a.get("status") == status_filter
                ]

                st.markdown(f"**Showing {len(filtered)} appointment(s)**")

                # Table header
                st.markdown("""
                <div style='display:grid;grid-template-columns:2fr 1.5fr 1.5fr 1fr 1fr;
                padding:0.6rem 1rem;background:#0f172a;border-radius:8px;
                margin-bottom:0.4rem;font-weight:700;font-size:0.78rem;
                color:#64748b;letter-spacing:0.06em;text-transform:uppercase;'>
                    <div>Patient Name</div><div>Department</div>
                    <div>Date & Time</div><div>Patient ID</div><div>Status</div>
                </div>""", unsafe_allow_html=True)

                for appt in filtered:
                    status    = appt.get("status", "")
                    color_map = {
                        "confirmed":   ("#d1fae5", "#065f46"),
                        "pending":     ("#fef9c3", "#854d0e"),
                        "rescheduled": ("#dbeafe", "#1e40af"),
                        "cancelled":   ("#fee2e2", "#991b1b"),
                    }
                    bg, text_color = color_map.get(status, ("#e2e8f0", "#1e293b"))

                    st.markdown(
                        f"<div style='display:grid;grid-template-columns:2fr 1.5fr 1.5fr 1fr 1fr;"
                        f"padding:0.75rem 1rem;background:#1e293b;border-radius:8px;"
                        f"margin-bottom:0.3rem;align-items:center;border-left:4px solid {bg};'>"
                        f"<div style='color:#f1f5f9;font-weight:600;font-size:0.92rem;'>{appt.get('patient_name')}</div>"
                        f"<div><span style='background:#ede9fe;color:#5b21b6;padding:0.2rem 0.6rem;"
                        f"border-radius:6px;font-size:0.8rem;font-weight:600;'>{appt.get('department','').capitalize()}</span></div>"
                        f"<div style='color:#cbd5e1;font-size:0.88rem;'>{appt.get('date')} &nbsp;|&nbsp; {appt.get('time')}</div>"
                        f"<div><code style='background:#0f172a;color:#7dd3fc;padding:0.2rem 0.5rem;"
                        f"border-radius:4px;font-size:0.85rem;'>{appt.get('patient_id')}</code></div>"
                        f"<div><span style='background:{bg};color:{text_color};padding:0.2rem 0.6rem;"
                        f"border-radius:6px;font-size:0.8rem;font-weight:700;text-transform:capitalize;'>{status}</span></div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

        # ── New Patient Registrations ──────────────────────────────
        with tab_new:
            st.markdown("### 🆕 New Patient Registrations")
            st.caption("Patients who registered through the Patient Portal and are awaiting staff confirmation.")

            col_ref3, col_ref4 = st.columns([1, 5])
            with col_ref3:
                if st.button("🔄 Refresh", key="refresh_new"):
                    st.rerun()
            with col_ref4:
                st.caption("Click Refresh after a new patient registers to see them here.")

            new_patients = get_new_patients()

            if not new_patients:
                st.success("✅ No pending new patient registrations.")
            else:
                st.warning(f"**{len(new_patients)} new patient(s) awaiting confirmation**")

                for patient in new_patients:
                    with st.expander(
                        f"NEW PATIENT — {patient.get('patient_name')} | "
                        f"ID: {patient.get('patient_id')} | "
                        f"Dept: {patient.get('department','').capitalize()} | "
                        f"Requested: {patient.get('date')} at {patient.get('time')}",
                        expanded=True
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**Patient ID:** `{patient.get('patient_id')}`")
                            st.markdown(f"**Name:** {patient.get('patient_name')}")
                            st.markdown(f"**Department:** {patient.get('department','').capitalize()}")
                        with c2:
                            st.markdown(f"**Requested Date:** {patient.get('date')}")
                            st.markdown(f"**Requested Time:** {patient.get('time')}")
                            st.markdown(f"**Status:** ⏳ Pending confirmation")

                        btn1, btn2 = st.columns(2)
                        with btn1:
                            if st.button(
                                "✅ Confirm Appointment",
                                type="primary",
                                use_container_width=True,
                                key=f"confirm_{patient.get('patient_id')}"
                            ):
                                confirm_patient(patient.get("patient_id", ""))
                                st.success(f"✅ {patient.get('patient_name')} confirmed!")
                                st.rerun()
                        with btn2:
                            if st.button(
                                "❌ Reject Registration",
                                use_container_width=True,
                                key=f"reject_new_{patient.get('patient_id')}"
                            ):
                                conn = get_connection()
                                conn.execute(
                                    "UPDATE appointments SET status = 'cancelled' WHERE patient_id = ?",
                                    (patient.get("patient_id"),)
                                )
                                conn.commit()
                                conn.close()
                                st.warning(f"Registration for {patient.get('patient_name')} rejected.")
                                st.rerun()

# ── Footer ─────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#94a3b8;font-size:0.8rem;'>"
    "Medic-Aid · MBAN 5510 Final Project · Saint Mary's University · "
    "Not a substitute for professional medical advice."
    "</p>",
    unsafe_allow_html=True
)