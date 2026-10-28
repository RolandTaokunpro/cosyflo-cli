"""Approval gate for deletes + high-stakes writes (D4, SR3).

High-stakes = tenancy termination, rent-amount change. The gate is enforced
CLI-side, refuses BEFORE any network mutation, and has no ungated code path:
every command must call enforce() before its write. Fail-closed — an
unreachable/unconfigured approval channel blocks, never auto-approves.

Slice 1 ships no command that performs a gated action (spec §9); the registry
+ machinery exist so slice 2 inherits them, and are unit-tested here.
"""
from .errors import ApprovalBlockedError, ApprovalDeniedError

GATED_ACTIONS = {"tenancy_terminate", "rent_amount_change"}


def is_gated(action):
    return action in GATED_ACTIONS


def enforce(action, feishu, payload=None):
    """Gate check before a write. Returns (allowing) or raises:
    ApprovalDeniedError  — Feishu denied or timed out          (exit 3)
    ApprovalBlockedError — no usable approval channel          (exit 3)
    """
    if not is_gated(action):
        return
    decision = feishu.request_approval(action, payload or {})
    if decision == "approved":
        return
    if decision in ("denied", "timeout"):
        raise ApprovalDeniedError("approval denied")
    raise ApprovalBlockedError("blocked: awaiting_approval")