"""
nodes/intent_classifier.py — Figures out what the patient wants.

Uses GPT-4o-mini to classify the patient's message into one of:
  - reschedule  → They want to move their appointment
  - cancel      → They want to cancel
  - prep        → They want preparation instructions
  - new_patient → They want to book for the first time / register
  - emergency   → Something urgent/dangerous was mentioned
  - unknown     → Can't determine intent
"""

import os
import json
from openai import OpenAI
from medic_aid.middleware.middleware import call_tracker

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def intent_classifier(state: dict) -> dict:
    """Classifies patient intent using GPT-4o-mini."""

    call_tracker.check_and_increment("intent_classifier")

    message  = state.get("raw_message", "")
    language = state.get("language", "en")

    system_prompt = """You are a medical appointment assistant classifier.
Classify the patient's message into exactly one of these intents:
- reschedule
- cancel
- prep
- new_patient
- emergency
- unknown

Rules:
- 'emergency' if they mention chest pain, difficulty breathing, severe pain, heart attack, stroke, or any life-threatening symptom
- 'prep' if they ask about how to prepare for an appointment or what to bring
- 'reschedule' if they want to move/change their appointment date or time
- 'cancel' if they want to cancel or remove their appointment
- 'new_patient' if they want to book a new appointment, register, sign up, or are a first-time patient. Also use this if they say things like "I would like to make an appointment", "I want to book", "I am a new patient", "I need an appointment", "I want to register", "je veux prendre un rendez-vous", "je suis nouveau patient", "je voudrais m'inscrire"
- 'unknown' for everything else that does not fit any of the above

Respond with ONLY a JSON object like: {"intent": "reschedule"}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": message},
        ],
        temperature=0,
        max_tokens=50,
    )

    raw = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw)
        intent = result.get("intent", "unknown")
    except Exception:
        intent = "unknown"

    print(f"Intent classified: {intent.upper()}")

    nodes_visited = state.get("nodes_visited", [])
    nodes_visited.append("intent_classifier")

    return {
        **state,
        "intent":        intent,
        "nodes_visited": nodes_visited,
    }