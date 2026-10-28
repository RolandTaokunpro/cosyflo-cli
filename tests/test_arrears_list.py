"""Gherkin: Feature List arrears — per-tenancy schedule (3 scenarios)."""
import tempfile
import unittest

import fakes

SCHEDULE = {
    "code": 200,
    "data": [
        {"tenancy_id": "T-7", "month": "2026-09", "amount": 82500, "monthly_rental": 82500},
        {"tenancy_id": "T-7", "month": "2026-10", "amount": 70000, "monthly_rental": 82500},
    ],
}


class ArrearsListScenarios(fakes.ScenarioTest):
    def test_lists_the_schedule(self):
        # Scenario: lists the schedule
        # Given a valid tenancy_id -> GET payment_rent/get_all_payments?tenancy_id=<id>,
        # prints month, amount, monthly_rental, shortfall per row, marking short months ARREARS.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport(default=fakes.FakeResponse(body=SCHEDULE))
            code, out, err = self.run_cli(
                ["arrears", "list", "--tenancy-id", "T-7", "--config", cfg],
                transport=transport,
            )
            self.assertEqual(code, 0, err)
            call = transport.calls_to("get_all_payments")
            self.assertEqual(len(call), 1)
            self.assertEqual(call[0]["params"], {"tenancy_id": "T-7"})
            self.assertIn("2026-09", out)
            self.assertIn("2026-10", out)
            self.assertIn("£825.00", out)
            self.assertIn("£700.00", out)
            self.assertIn("£125.00", out)
            self.assertIn("ARREARS", out)

    def test_rejects_a_missing_tenancy_id(self):
        # Scenario: rejects a missing tenancy id -> 'error: --tenancy-id required', no REST call.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport()
            code, out, err = self.run_cli(
                ["arrears", "list", "--config", cfg],
                transport=transport,
            )
            self.assertEqual(code, 1)
            self.assertIn("error: --tenancy-id required", err)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")

    def test_empty_schedule_is_explicit(self):
        # Scenario: empty schedule is explicit -> prints 'no payment schedule for <id>'.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport(
                default=fakes.FakeResponse(body={"code": 200, "data": []})
            )
            code, out, err = self.run_cli(
                ["arrears", "list", "--tenancy-id", "T-404", "--config", cfg],
                transport=transport,
            )
            self.assertEqual(code, 0, err)
            self.assertIn("no payment schedule for T-404", out)


if __name__ == "__main__":
    unittest.main()