"""Gherkin: Feature Audit (cross-cutting) (3 scenarios)."""
import os
import tempfile
import unittest

import fakes


def make_transport(post_body=None, post_status=200):
    return fakes.FakeTransport(
        responses={
            ("GET", "get_all_payments"): fakes.FakeResponse(body={"code": 200, "data": []}),
            ("GET", "get_user_info"): fakes.FakeResponse(
                body={"code": 200, "data": {"user": {"name": "Test Admin", "user_account_id": "ua-1"}}}
            ),
            ("POST", "create_payment"): fakes.FakeResponse(
                status_code=post_status,
                body=post_body if post_body is not None else {"code": 200, "data": []},
            ),
        }
    )


def run_mark_paid(self, tmp, transport, month):
    cfg = fakes.write_config(tmp)
    code, out, err = self.run_cli(
        ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", month,
         "--amount", "825.00", "--config", cfg],
        transport=transport,
    )
    return cfg, code, out, err


class AuditScenarios(fakes.ScenarioTest):
    def test_every_mutation_appends_a_chained_line(self):
        # Scenario: every mutation appends a chained line
        # Given any write command completes -> audit line with command, target id, month,
        # operator, UTC timestamp, and prev_hash equal to the prior line's hash.
        with tempfile.TemporaryDirectory() as tmp:
            cfg, code, _, err = run_mark_paid(self, tmp, make_transport(), "2026-09")
            self.assertEqual(code, 0, err)
            cfg, code, _, err = run_mark_paid(self, tmp, make_transport(), "2026-10")
            self.assertEqual(code, 0, err)
            audit = self.read_audit(cfg.replace("config.json", "audit.log"))
            self.assertEqual(len(audit), 2)
            self.assertEqual(audit[0]["prev_hash"], "", "first line seeds the chain")
            self.assertEqual(audit[1]["prev_hash"], audit[0]["hash"],
                              "second line must chain to the first line's hash")
            self.assertNotEqual(audit[0]["hash"], audit[1]["hash"])
            for line in audit:
                self.assertIn("command", line)
                self.assertIn("operator", line)
                self.assertTrue(line["ts"].endswith("Z"))

    def test_read_commands_leave_no_audit_line(self):
        # Scenario: read commands leave no audit line
        # Given a read command (payment list-pending, arrears list) -> no audit line is
        # appended and no Feishu notify fires.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            transport = fakes.FakeTransport(
                default=fakes.FakeResponse(body={"code": 200, "data": {"data": [], "total": 0}})
            )
            feishu = fakes.FakeFeishu()
            code, out, err = self.run_cli(
                ["payment", "list-pending", "--month", "2026-10", "--config", cfg],
                transport=transport, feishu=feishu,
            )
            self.assertEqual(code, 0, err)
            transport2 = fakes.FakeTransport(
                default=fakes.FakeResponse(body={"code": 200, "data": []})
            )
            code, out, err = self.run_cli(
                ["arrears", "list", "--tenancy-id", "T-7", "--config", cfg],
                transport=transport2, feishu=feishu,
            )
            self.assertEqual(code, 0, err)
            audit_path = cfg.replace("config.json", "audit.log")
            self.assertFalse(os.path.exists(audit_path), "reads must not create the audit log")
            self.assertEqual(feishu.notifications, [], "reads must not fire Feishu notify")

    def test_failed_mutation_is_audit_logged_with_an_error_marker(self):
        # Scenario: failed mutation is audit-logged with an error marker
        # Given a write command whose REST call returns an error envelope -> audit line
        # records the attempt with status=error and the error code, never the credential.
        with tempfile.TemporaryDirectory() as tmp:
            transport = make_transport(post_body={"code": 400, "error": "validation failed"},
                                       post_status=400)
            cfg, code, out, err = run_mark_paid(self, tmp, transport, "2026-10")
            self.assertEqual(code, 4)
            audit = self.read_audit(cfg.replace("config.json", "audit.log"))
            self.assertEqual(len(audit), 1)
            line = audit[0]
            self.assertEqual(line["status"], "error")
            self.assertEqual(line["error_code"], 400)
            self.assertEqual(line["command"], "payment_mark_paid")
            audit_path = cfg.replace("config.json", "audit.log")
            raw = ""
            with open(audit_path) as f:
                raw = f.read()
            self.assertNotIn(self.TOKEN, raw, "credential must never reach the audit log")


if __name__ == "__main__":
    unittest.main()