"""Feishu webhook channel (D3/D4): mutation notify + approval request/poll.

Configured via config only (webhook_url, approval_poll_url, timeout) — no
channel details in code. With no webhook configured:
  - notify_mutation  -> 'skipped' (recorded in the audit line)
  - request_approval -> 'unconfigured' (the gate then blocks: nothing can be
    auto-approved without a channel — fail-closed per D4).

The approve/deny loop mechanics are R4 (open): the CLI emits the request and
polls `approval_poll_url?request_id=` for {decision: approved|denied}.
"""
import time
import uuid

import requests


class Feishu:
    def __init__(self, webhook_url=None, approval_poll_url=None,
                 approval_timeout_seconds=300, poll_interval=2.0, transport=None):
        self.webhook_url = webhook_url
        self.approval_poll_url = approval_poll_url
        self.approval_timeout_seconds = approval_timeout_seconds
        self.poll_interval = poll_interval
        self.transport = transport or requests

    @classmethod
    def from_config(cls, cfg, transport=None):
        return cls(
            webhook_url=cfg.get("webhook_url"),
            approval_poll_url=cfg.get("approval_poll_url"),
            approval_timeout_seconds=cfg.get("approval_timeout_seconds", 300),
            transport=transport,
        )

    def notify_mutation(self, entry):
        """Fire the mutation notify (SR4). Returns 'ok' | 'skipped' | 'failed'."""
        if not self.webhook_url:
            return "skipped"
        payload = {"type": "mutation", "entry": entry}
        try:
            resp = self.transport.post(self.webhook_url, json=payload, timeout=10)
        except Exception:
            return "failed"
        return "ok" if getattr(resp, "status_code", 500) < 400 else "failed"

    def request_approval(self, action, payload):
        """Emit an approval request for a gated action, then wait for the
        decision. Returns 'approved' | 'denied' | 'timeout' | 'unconfigured' |
        'failed'. No path here returns 'approved' without a channel response."""
        if not self.webhook_url:
            return "unconfigured"
        request_id = str(uuid.uuid4())
        message = {
            "type": "approval_request",
            "action": action,
            "payload": payload,
            "request_id": request_id,
        }
        try:
            resp = self.transport.post(self.webhook_url, json=message, timeout=10)
            if getattr(resp, "status_code", 500) >= 400:
                return "failed"
        except Exception:
            return "failed"
        if not self.approval_poll_url:
            return "unconfigured"
        deadline = time.monotonic() + self.approval_timeout_seconds
        while time.monotonic() < deadline:
            try:
                resp = self.transport.get(
                    f"{self.approval_poll_url}?request_id={request_id}", timeout=10
                )
                decision = (resp.json() or {}).get("decision")
            except Exception:
                decision = None
            if decision in ("approved", "denied"):
                return decision
            time.sleep(self.poll_interval)
        return "timeout"