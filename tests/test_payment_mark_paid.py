"""Gherkin: Feature Mark a payment paid (6 scenarios) + money unit round-trips."""
import tempfile
import unittest
from decimal import Decimal

import fakes

SCHEDULE_OTHER_MONTH = {
    "code": 200,
    "data": [
        {"tenancy_id": "T-1", "month": "2026-09", "amount": 82500, "monthly_rental": 82500},
    ],
}


def make_transport(existing=None, post_body=None, post_status=200):
    return fakes.FakeTransport(
        responses={
            ("GET", "get_all_payments"): fakes.FakeResponse(
                body={"code": 200, "data": existing if existing is not None else SCHEDULE_OTHER_MONTH["data"]}
            ),
            ("GET", "get_user_info"): fakes.FakeResponse(
                body={"code": 200, "data": {"user": {"name": "Test Admin", "user_account_id": "ua-1"}}}
            ),
            ("POST", "create_payment"): fakes.FakeResponse(
                status_code=post_status,
                body=post_body if post_body is not None else {"code": 200, "data": []},
            ),
        }
    )


class MarkPaidScenarios(fakes.ScenarioTest):
    def _run(self, tmp, transport, *extra):
        cfg = fakes.write_config(tmp)
        argv = ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026-10",
                "--amount", "825.00", "--config", cfg, *extra]
        code, out, err = self.run_cli(argv, transport=transport)
        return cfg, code, out, err

    def test_records_a_payment(self):
        # Scenario: records a payment
        # Given valid tenancy_id, month, amount in pounds >= 0 with <= 2 dp -> POST
        # payment_rent/create_payment with amount in POUNDS, and prints the confirmation.
        # Also carries the §8 money-function contract (single Decimal-owned conversion).
        from cosyflo_cli.money import pounds_to_pence, pence_to_pounds
        self.assertEqual(pounds_to_pence("0"), 0)
        self.assertEqual(pence_to_pounds(1), Decimal("0.01"))
        self.assertEqual(pounds_to_pence("0.01"), 1)
        self.assertEqual(pounds_to_pence("825.00"), 82500)
        self.assertEqual(pence_to_pounds(82500), Decimal("825.00"))
        self.assertEqual(pounds_to_pence("999999.99"), 99999999)
        self.assertEqual(pence_to_pounds(99999999), Decimal("999999.99"))
        with tempfile.TemporaryDirectory() as tmp:
            transport = make_transport()
            cfg, code, out, err = self._run(tmp, transport)
            self.assertEqual(code, 0, err)
            posts = transport.calls_to("create_payment")
            self.assertEqual(len(posts), 1)
            self.assertEqual(
                posts[0]["data"],
                {"tenancy_id": "T-1", "month": "2026-10", "amount": "825.00"},
                "CLI must send pounds; the controller owns the x100"
            )
            self.assertIn("payment recorded", out)
            self.assertIn("T-1", out)
            self.assertIn("2026-10", out)
            self.assertIn("£825.00", out)

    def test_appends_an_audit_line(self):
        # Scenario: appends an audit line
        # Given a successful payment mark-paid -> audit line with command=payment_mark_paid,
        # tenancy_id, month, amount, operator, UTC timestamp.
        with tempfile.TemporaryDirectory() as tmp:
            transport = make_transport()
            cfg, code, out, err = self._run(tmp, transport)
            self.assertEqual(code, 0, err)
            audit = self.read_audit(cfg.replace("config.json", "audit.log"))
            self.assertEqual(len(audit), 1)
            line = audit[0]
            self.assertEqual(line["command"], "payment_mark_paid")
            self.assertEqual(line["params"]["tenancy_id"], "T-1")
            self.assertEqual(line["params"]["month"], "2026-10")
            self.assertEqual(line["params"]["amount"], "825.00")
            self.assertEqual(line["operator"], "Test Admin")
            self.assertTrue(line["ts"].endswith("Z"))

    def test_rejects_a_negative_amount(self):
        # Scenario: rejects a negative amount -> 'error: amount must be >= 0', no REST call.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport()
            code, out, err = self.run_cli(
                ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026-10",
                 "--amount", "-5.00", "--config", cfg],
                transport=transport,
            )
            self.assertEqual(code, 1)
            self.assertIn("amount must be >= 0", err)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")

    def test_rejects_more_than_two_decimal_places(self):
        # Scenario: rejects money with more than 2 decimal places
        # Given --amount 825.005 -> 'error: amount max 2 decimals', no REST call.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport()
            code, out, err = self.run_cli(
                ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026-10",
                 "--amount", "825.005", "--config", cfg],
                transport=transport,
            )
            self.assertEqual(code, 1)
            self.assertIn("amount max 2 decimals", err)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")

    def test_rejects_a_malformed_month(self):
        # Scenario: rejects a malformed month -> typed validation error, no REST call.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport()
            code, out, err = self.run_cli(
                ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026/10",
                 "--amount", "825.00", "--config", cfg],
                transport=transport,
            )
            self.assertEqual(code, 1)
            self.assertIn("month", err)
            self.assertIn("YYYY-MM", err)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")

    def test_overwrite_is_surfaced_not_silent(self):
        # Scenario: overwrite is surfaced, not silent
        # Given a month that already has a recorded amount -> warns
        # 'overwriting existing value <old> with <new>' before calling, still completes.
        with tempfile.TemporaryDirectory() as tmp:
            existing = [
                {"tenancy_id": "T-1", "month": "2026-10", "amount": 70000, "monthly_rental": 82500},
            ]
            transport = make_transport(existing=existing)
            cfg, code, out, err = self._run(tmp, transport)
            self.assertEqual(code, 0, err)
            self.assertIn("overwriting existing value £700.00 with £825.00", out + err)
            self.assertEqual(len(transport.calls_to("create_payment")), 1)


if __name__ == "__main__":
    unittest.main()