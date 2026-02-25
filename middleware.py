"""
middleware/middleware.py — All middleware components used in Medic-Aid.

Middleware components implemented:
  1. PIIMiddleware             — masks patient name/ID in all logs
  2. OpenAIModerationMiddleware — checks for harmful content via OpenAI API
  3. ModelRetryMiddleware      — retries LLM calls on failure (up to 3 times)
  4. ModelCallLimitMiddleware  — caps total LLM calls per run (cost control)
  5. SummarizationMiddleware   — generates readable audit log after each run
  6. ContextEditingMiddleware  — allows human reviewer to edit draft (in hitl_node)
  7. HumanInTheLoopMiddleware  — pauses workflow for staff review (in hitl_node)

Each middleware integrates with LangGraph state by reading from and writing
back to the shared AppointmentState dictionary passed between nodes.
"""

import re
import time
import functools
from openai import OpenAI
import os


# ─────────────────────────────────────────────────────────────────
# 1. PII MIDDLEWARE
# Masks sensitive patient info in logs so we never expose real data
# Integrates with state: reads patient_name, patient_id; writes masked_log
# ─────────────────────────────────────────────────────────────────
def mask_pii(text: str, patient_name: str = "", patient_id: str = "") -> str:
    """Replace real name and ID with masked versions for safe logging."""
    masked = text
    if patient_name:
        masked = masked.replace(patient_name, "[PATIENT_NAME]")
    if patient_id:
        masked = masked.replace(patient_id, "[PATIENT_ID]")
    return masked


def pii_middleware(node_fn):
    """
    Decorator: automatically masks PII in the state's masked_log after a node runs.
    Integrates with LangGraph state by post-processing the returned state dict.
    """
    @functools.wraps(node_fn)
    def wrapper(state: dict) -> dict:
        result = node_fn(state)
        name = result.get("patient_name", state.get("patient_name", ""))
        pid  = result.get("patient_id",   state.get("patient_id", ""))
        log  = result.get("masked_log", "")
        if log:
            result["masked_log"] = mask_pii(log, name, pid)
        return result
    return wrapper


# ─────────────────────────────────────────────────────────────────
# 2. OPENAI MODERATION MIDDLEWARE
# Calls OpenAI's moderation API to flag harmful/dangerous content
# Integrates with state: called inside risk_evaluator node
# ─────────────────────────────────────────────────────────────────
def check_moderation(text: str) -> dict:
    """
    Returns {"flagged": bool, "categories": list}
    Uses OpenAI's free moderation endpoint — does not consume chat tokens.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.moderations.create(input=text)
        result = response.results[0]
        flagged_cats = [
            cat for cat, val in result.categories.__dict__.items() if val
        ]
        return {"flagged": result.flagged, "categories": flagged_cats}
    except Exception:
        # If moderation API fails, fail safe — do not block the request
        return {"flagged": False, "categories": []}


# ─────────────────────────────────────────────────────────────────
# 3. MODEL RETRY MIDDLEWARE
# Retries a function on exception — applied to LLM call functions
# Integrates with state: wraps _call_llm functions in nodes
# Usage: @retry_middleware (as decorator) or retry_middleware(fn)
# ─────────────────────────────────────────────────────────────────
def retry_middleware(fn=None, max_retries: int = 3, delay: float = 1.0):
    """
    Decorator factory: retries the wrapped function on exception.
    Can be used as @retry_middleware or @retry_middleware(max_retries=5)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    print(f"⚠️  [RetryMiddleware] Attempt {attempt}/{max_retries} "
                          f"for '{func.__name__}': {e}")
                    time.sleep(delay)
            raise RuntimeError(
                f"[RetryMiddleware] '{func.__name__}' failed after "
                f"{max_retries} retries. Last error: {last_error}"
            )
        return wrapper

    # Support both @retry_middleware and @retry_middleware()
    if fn is not None:
        return decorator(fn)
    return decorator


# ─────────────────────────────────────────────────────────────────
# 4. MODEL CALL LIMIT MIDDLEWARE
# Prevents runaway LLM API calls (cost control)
# Integrates with state: call_tracker is reset at the start of each run in graph.py
# ─────────────────────────────────────────────────────────────────
class CallLimitTracker:
    """
    Tracks how many LLM calls have been made in the current run.
    Raises an error if the limit is exceeded.
    Integrates with LangGraph: reset via call_tracker.call_count = 0 in run_workflow().
    """
    def __init__(self, max_calls: int = 10):
        self.max_calls  = max_calls
        self.call_count = 0

    def check_and_increment(self, node_name: str):
        self.call_count += 1
        if self.call_count > self.max_calls:
            raise RuntimeError(
                f"[CallLimitMiddleware] Model call limit ({self.max_calls}) "
                f"exceeded at node '{node_name}'. Run aborted to prevent runaway costs."
            )
        print(f"📊 [CallLimitMiddleware] Call {self.call_count}/{self.max_calls} "
              f"at node '{node_name}'")


# Global tracker instance — shared across all nodes in a run
call_tracker = CallLimitTracker(max_calls=10)


# ─────────────────────────────────────────────────────────────────
# 5. SUMMARIZATION MIDDLEWARE
# Generates a concise, readable audit summary of the workflow trace
# Integrates with state: writes to masked_log field in AppointmentState
# ─────────────────────────────────────────────────────────────────
def summarize_trace(
    nodes_visited: list,
    intent:        str,
    risk_level:    str,
    status:        str,
    patient_id:    str = "",
    patient_name:  str = "",
) -> str:
    """
    Creates a PII-safe one-line summary of what happened during a run.
    This is the value stored in state['masked_log'] for the audit trail.
    """
    path = " → ".join(nodes_visited)
    summary = (
        f"[SummarizationMiddleware] "
        f"Intent: {intent.upper()} | Risk: {risk_level} | "
        f"Status: {status} | Patient: [PATIENT_ID] | "
        f"Path: {path}"
    )
    # Apply PII masking on top
    return mask_pii(summary, patient_name, patient_id)