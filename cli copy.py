"""
cli.py — Command-line interface for Medic-Aid.

Run with:
    python cli.py

Or with arguments:
    python cli.py --patient-id P001 --name "Alice Martin" --dept cardiology --message "I want to reschedule"

This is the required CLI entry point for the course submission.
"""

import argparse
import sys
from dotenv import load_dotenv
from medic_aid.database.setup import setup_database, seed_database
from medic_aid.graph import run_workflow

load_dotenv()

DEPARTMENTS = ["cardiology", "radiology", "dental", "general", "orthopedics"]


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏥  M E D I C - A I D                  ║
║     Intelligent Appointment Assistant            ║
║        MBAN 5510 — Agentic AI Project           ║
╚══════════════════════════════════════════════════╝
""")


def print_result(result: dict):
    print("\n" + "="*60)
    print("📊 FINAL RUN SUMMARY")
    print("="*60)
    print(f"  Run ID         : {result.get('run_id')}")
    print(f"  Terminal Status: {result.get('terminal_status')}")
    print(f"  Intent         : {result.get('intent', '').upper()}")
    print(f"  Risk Level     : {result.get('risk_level', '')}")
    print(f"  Language       : {'French' if result.get('language') == 'fr' else 'English'}")
    print(f"  Human Approved : {result.get('human_approved')}")
    print(f"  Human Edited   : {result.get('human_edited')}")
    print(f"  Path Taken     : {' → '.join(result.get('nodes_visited', []))}")
    print(f"\n  📋 Masked Log  : {result.get('masked_log', 'N/A')}")
    print(f"\n📨 FINAL RESPONSE TO PATIENT:\n")
    print(f"  {result.get('final_response', result.get('draft_response', 'No response generated.'))}")
    print("="*60)


def interactive_mode():
    """Runs the CLI in interactive prompt mode."""
    print_banner()

    # Ensure DB is ready
    setup_database()
    seed_database()

    print("Please provide patient details:\n")

    patient_id   = input("Patient ID (e.g. P001): ").strip()
    patient_name = input("Patient Name          : ").strip()

    print(f"\nDepartments: {', '.join(DEPARTMENTS)}")
    department   = input("Department            : ").strip().lower()

    if department not in DEPARTMENTS:
        print(f"⚠️  Unknown department. Defaulting to 'general'.")
        department = "general"

    print("\nType your message (what do you need help with?):")
    message = input("> ").strip()

    print("\n")
    result = run_workflow(
        patient_id=patient_id,
        patient_name=patient_name,
        raw_message=message,
        department=department,
        include_hitl=True,
    )

    print_result(result)


def argument_mode(args):
    """Runs the CLI with command-line arguments (non-interactive)."""
    print_banner()
    setup_database()
    seed_database()

    result = run_workflow(
        patient_id=args.patient_id,
        patient_name=args.name,
        raw_message=args.message,
        department=args.dept,
        include_hitl=not args.no_hitl,
    )
    print_result(result)


def main():
    parser = argparse.ArgumentParser(
        description="Medic-Aid — Intelligent Hospital Appointment Assistant"
    )
    parser.add_argument("--patient-id", help="Patient ID (e.g. P001)")
    parser.add_argument("--name",       help="Patient full name")
    parser.add_argument("--dept",       help="Department", choices=DEPARTMENTS)
    parser.add_argument("--message",    help="Patient request message")
    parser.add_argument("--no-hitl",    action="store_true",
                        help="Skip human review step (for testing)")

    args = parser.parse_args()

    # If all required args provided, run in argument mode
    if all([args.patient_id, args.name, args.dept, args.message]):
        argument_mode(args)
    else:
        # Otherwise, run interactively
        interactive_mode()


if __name__ == "__main__":
    main()
