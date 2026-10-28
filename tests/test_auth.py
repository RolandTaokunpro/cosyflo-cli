"""Gherkin: Feature Auth — service-account token (3 scenarios)."""
import os
import tempfile
import unittest

import fakes


class AuthScenarios(fakes.ScenarioTest):
    def test_fetches_token_at_runtime_and_sends_bearer(self):
        # Scenario: fetches the token at runtime
        # Given `op read "op://<vault>/<item>/api_token"` returns a non-empty token
        # When any command runs -> Authorization: Bearer + Accept: application/json
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(
                tmp,
                token={"source": "op", "op_ref": "op://Test/cosyflo-service/api_token"},
            )
            transport = fakes.FakeTransport(
                default=fakes.FakeResponse(body={"code": 200, "data": {"data": [], "total": 0}})
            )
            op = fakes.FakeOpRunner(token="tok-op-abc123")
            code, out, err = self.run_cli(
                ["payment", "list-pending", "--month", "2026-10", "--config", cfg],
                transport=transport,
                op_runner=op,
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(op.calls, [["op", "read", "op://Test/cosyflo-service/api_token"]])
            call = transport.calls[0]
            self.assertEqual(
                call["headers"],
                {"Authorization": "Bearer tok-op-abc123", "Accept": "application/json"},
            )
            # Regression guard: global flags must also work BEFORE the subcommand
            # (subparser defaults must not clobber top-level-parsed values).
            transport2 = fakes.FakeTransport(
                default=fakes.FakeResponse(body={"code": 200, "data": {"data": [], "total": 0}})
            )
            code2, out2, err2 = self.run_cli(
                ["--config", cfg, "payment", "list-pending", "--month", "2026-10"],
                transport=transport2,
                op_runner=fakes.FakeOpRunner(token="tok-op-abc123"),
            )
            self.assertEqual(code2, 0, err2)
            self.assertEqual(transport2.calls[0]["headers"]["Authorization"],
                             "Bearer tok-op-abc123")

    def test_refuses_to_run_when_op_read_fails(self):
        # Scenario: refuses to run when op read fails
        # Given op read errors or the secret is absent -> 'error: cannot fetch credential',
        # exit non-zero, no token material printed.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(
                tmp,
                token={"source": "op", "op_ref": "op://Test/cosyflo-service/api_token"},
            )
            transport = fakes.FakeTransport()
            op = fakes.FakeOpRunner(fail=True)
            code, out, err = self.run_cli(
                ["payment", "list-pending", "--month", "2026-10", "--config", cfg],
                transport=transport,
                op_runner=op,
            )
            self.assertEqual(code, 2)
            self.assertIn("cannot fetch credential", err)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")
            self.assertNotIn("op://Test/cosyflo-service/api_token", out + err)

    def test_never_echoes_the_token(self):
        # Scenario: never echoes the token
        # Given a successful token fetch or any downstream error, success or failure:
        # the token string never appears in stdout, stderr, or the audit log.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = fakes.write_config(tmp)
            good = fakes.FakeTransport(
                responses={
                    ("GET", "get_all_payments"): fakes.FakeResponse(
                        body={"code": 200, "data": []}
                    ),
                    ("GET", "get_user_info"): fakes.FakeResponse(
                        body={"code": 200, "data": {"user": {"name": "Test Admin", "user_account_id": "ua-1"}}}
                    ),
                    ("POST", "create_payment"): fakes.FakeResponse(body={"code": 200, "data": []}),
                }
            )
            code, out, err = self.run_cli(
                ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026-10",
                 "--amount", "825.00", "--config", cfg],
                transport=good,
            )
            self.assertEqual(code, 0, err)
            bad = fakes.FakeTransport(
                responses={
                    ("GET", "get_all_payments"): fakes.FakeResponse(
                        body={"code": 200, "data": []}
                    ),
                    ("POST", "create_payment"): fakes.FakeResponse(
                        status_code=400, body={"code": 400, "error": "boom"}
                    ),
                }
            )
            code2, out2, err2 = self.run_cli(
                ["payment", "mark-paid", "--tenancy-id", "T-1", "--month", "2026-09",
                 "--amount", "825.00", "--config", cfg],
                transport=bad,
            )
            self.assertEqual(code2, 4)
            audit_path = cfg.replace("config.json", "audit.log")
            audit_text = ""
            if os.path.exists(audit_path):
                with open(audit_path) as f:
                    audit_text = f.read()
            for stream in (out + err + out2 + err2 + audit_text):
                self.assertNotIn(self.TOKEN, stream, "token material leaked")


if __name__ == "__main__":
    unittest.main()