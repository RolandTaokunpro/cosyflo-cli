"""Gherkin: Feature List pending payments (3 scenarios)."""
import tempfile
import unittest

import fakes

MONTH_PAGE = {
    "code": 200,
    "data": {
        "data": [
            {
                "tenancy_id": "T-001",
                "monthly_rental": 825.00,
                "paid_amount": 70000,
                "current_month": "2026-10",
                "headTenant": {"first_name": "Alice", "last_name": "Smith"},
            },
            {
                "tenancy_id": "T-002",
                "monthly_rental": 1200.0,
                "paid_amount": 0,
                "current_month": "2026-10",
                "headTenant": {"first_name": "Bob", "last_name": "Jones"},
            },
        ],
        "total": 2,
        "current_page": 1,
    },
}


class ListPendingScenarios(fakes.ScenarioTest):
    def _run(self, tmp, month, transport=None):
        cfg = fakes.write_config(tmp)
        transport = transport or fakes.FakeTransport(
            default=fakes.FakeResponse(body=MONTH_PAGE)
        )
        code, out, err = self.run_cli(
            ["payment", "list-pending", "--month", month, "--config", cfg],
            transport=transport,
        )
        return cfg, transport, code, out, err

    def test_lists_arrears_for_a_month(self):
        # Scenario: lists arrears for a month
        # Given a valid session and a month YYYY-MM -> calls
        # GET get_all_tenancy?scenes=rentControl&arrears_value=YYYY-MM and prints one row
        # per tenancy with tenancy_id, masked surname, monthly_rental, amount, shortfall.
        with tempfile.TemporaryDirectory() as tmp:
            cfg, transport, code, out, err = self._run(tmp, "2026-10")
            self.assertEqual(code, 0, err)
            call = transport.calls_to("get_all_tenancy")
            self.assertEqual(len(call), 1)
            self.assertEqual(call[0]["params"]["scenes"], "rentControl")
            self.assertEqual(call[0]["params"]["arrears_value"], "2026-10")
            self.assertIn("T-001", out)
            self.assertIn("A. Smith", out)  # masked beyond the authenticated boundary
            self.assertIn("B. Jones", out)
            self.assertIn("£825.00", out)
            self.assertIn("£700.00", out)
            self.assertIn("£125.00", out)   # T-001 shortfall
            self.assertIn("£1200.00", out)
            self.assertIn("£0.00", out)
            self.assertIn("£1200.00", out)  # T-002 shortfall
            self.assertIn("2 tenancies in arrears", out)

    def test_rejects_a_malformed_month(self):
        # Scenario: rejects a malformed month
        # Given a --month value that is not YYYY-MM -> typed validation error, no REST call.
        with tempfile.TemporaryDirectory() as tmp:
            cfg, transport, code, out, err = self._run(tmp, "2026-13", fakes.FakeTransport())
            self.assertEqual(code, 1)
            self.assertIn("month", err)
            self.assertIn("YYYY-MM", err)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")

    def test_empty_result_is_explicit(self):
        # Scenario: empty result is explicit
        # Given a month with no arrears -> prints '0 tenancies in arrears', not a blank screen.
        with tempfile.TemporaryDirectory() as tmp:
            cfg, transport, code, out, err = self._run(
                tmp,
                "2026-10",
                fakes.FakeTransport(default=fakes.FakeResponse(
                    body={"code": 200, "data": {"data": [], "total": 0}}
                )),
            )
            self.assertEqual(code, 0, err)
            self.assertIn("0 tenancies in arrears", out)


if __name__ == "__main__":
    unittest.main()