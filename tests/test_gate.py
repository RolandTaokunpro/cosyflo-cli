"""Gherkin: Feature Approval gate (cross-cutting) (3 scenarios).

Slice 1 ships no command that performs a gated action (tenancy termination /
rent-amount change) — per spec §9 the gate is exercised by unit tests, not a
live path. These tests drive the gate machinery directly.
"""
import tempfile
import unittest

import fakes


def make_feishu(tmp, poll_url=None, poll_body=None, timeout=2.0):
    from cosyflo_cli.feishu import Feishu
    transport = fakes.FakeTransport(
        responses={
            ("POST", "feishu.example"): fakes.FakeResponse(body={"code": 0}),
            ("GET", "poll"): fakes.FakeResponse(
                body=poll_body if poll_body is not None else {"decision": "pending"}
            ),
        }
    )
    feishu = Feishu(
        webhook_url="https://feishu.example/hook",
        approval_poll_url=poll_url,
        approval_timeout_seconds=timeout,
        poll_interval=0.05,
        transport=transport,
    )
    return feishu, transport


class GateScenarios(fakes.ScenarioTest):
    def test_gated_action_refuses_before_network(self):
        # Scenario: gated action refuses before network
        # Given a gated action without prior approval -> no REST call leaves the CLI; a Feishu
        # approval request is emitted containing the proposed mutation; result is
        # 'blocked: awaiting_approval'.
        from cosyflo_cli import gate
        from cosyflo_cli.errors import ApprovalBlockedError
        feishu, transport = make_feishu(tmp := tempfile.mkdtemp())
        with self.assertRaises(ApprovalBlockedError) as ctx:
            gate.enforce("tenancy_terminate", feishu, {"tenancy_id": "T-9"})
        self.assertIn("awaiting_approval", str(ctx.exception))
        self.assertIn("blocked", str(ctx.exception))
        posts = transport.calls_to("feishu.example/hook")
        self.assertEqual(len(posts), 1, "approval request must be emitted")
        payload = posts[0]["json"]
        self.assertEqual(payload["action"], "tenancy_terminate")
        self.assertEqual(payload["payload"], {"tenancy_id": "T-9"})
        self.assertEqual(transport.rest_calls(), [], "no REST call may leave the CLI")

    def test_unapproved_gate_never_executes(self):
        # Scenario: unapproved gate never executes
        # Given the Feishu request is denied or times out -> the REST mutation is never
        # issued; the command exits non-zero with 'approval denied'.
        from cosyflo_cli import gate
        from cosyflo_cli.errors import ApprovalDeniedError
        # denied
        feishu, transport = make_feishu(
            tempfile.mkdtemp(),
            poll_url="https://feishu.example/poll",
            poll_body={"decision": "denied"},
        )
        with self.assertRaises(ApprovalDeniedError) as ctx:
            gate.enforce("tenancy_terminate", feishu, {"tenancy_id": "T-9"})
        self.assertEqual(str(ctx.exception), "approval denied")
        self.assertEqual(transport.rest_calls(), [], "no REST call may leave the CLI")
        # timeout (decision never arrives)
        feishu2, transport2 = make_feishu(
            tempfile.mkdtemp(),
            poll_url="https://feishu.example/poll",
            poll_body={"decision": "pending"},
            timeout=0.2,
        )
        with self.assertRaises(ApprovalDeniedError) as ctx2:
            gate.enforce("rent_amount_change", feishu2, {"tenancy_id": "T-9", "monthly_rental": "900.00"})
        self.assertEqual(str(ctx2.exception), "approval denied")
        self.assertEqual(transport2.rest_calls(), [], "no REST call may leave the CLI")

    def test_mark_paid_is_not_a_gated_action(self):
        # Scenario: mark-paid is not a gated action
        # Given a normal payment mark-paid (recording a payment, not changing the rent
        # amount) -> it is NOT blocked by the gate.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport(
                responses={
                    ("GET", "get_all_payments"): fakes.FakeResponse(body={"code": 200, "data": []}),
                    ("GET", "get_user_info"): fakes.FakeResponse(
                        body={"code": 200, "data": {"user": {"name": "Test Admin", "user_account_id": "ua-1"}}}
                    ),
                    ("POST", "create_payment"): fakes.FakeResponse(body={"code": 200, "data": []}),
                }
            )
            feishu = fakes.FakeFeishu()
            code, out, err = self.run_cli(
                ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026-10",
                 "--amount", "825.00", "--config", cfg],
                transport=transport,
                feishu=feishu,
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(feishu.approval_requests, [], "routine mark-paid must not request approval")
            self.assertEqual(len(transport.calls_to("create_payment")), 1, "mutation proceeds")


if __name__ == "__main__":
    unittest.main()