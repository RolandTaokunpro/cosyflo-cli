"""Gherkin: Feature Draft a chase message (3 scenarios)."""
import os
import tempfile
import unittest

import fakes


class MessageDraftScenarios(fakes.ScenarioTest):
    def _run(self, tmp, tdir, *extra):
        cfg = fakes.write_config(tmp, templates_dir=tdir)
        argv = ["message", "draft", "--template", "chase-standard",
                "--tenancy-id", "T-5", "--month", "2026-10",
                "--tenant-name", "Alice", "--amount-short", "125.00",
                "--config", cfg, *extra]
        return cfg, argv

    def test_renders_a_draft_from_a_template(self):
        # Scenario: renders a draft from a template
        # Given a template file and a tenancy's arrears values -> reads the template,
        # substitutes the values, writes to --output; NO REST call, no send.
        with tempfile.TemporaryDirectory() as tmp:
            tdir = fakes.make_template(tmp)
            cfg, argv = self._run(tmp, tdir)
            outpath = os.path.join(tmp, "draft.txt")
            transport = fakes.FakeTransport()
            op = fakes.FakeOpRunner(token="should-not-be-fetched")
            code, out, err = self.run_cli(
                [*argv, "--output", outpath], transport=transport, op_runner=op
            )
            self.assertEqual(code, 0, err)
            rendered = open(outpath).read()
            self.assertIn("Dear Alice,", rendered)
            self.assertIn("Tenancy T-5", rendered)
            self.assertIn("£125.00", rendered)
            self.assertIn("2026-10", rendered)
            self.assertEqual(transport.calls, [], "no REST call may leave the CLI")
            self.assertEqual(op.calls, [], "drafting needs no credential")

    def test_refuses_an_unknown_template(self):
        # Scenario: refuses an unknown template -> 'error: unknown template <name>', non-zero.
        with tempfile.TemporaryDirectory() as tmp:
            tdir = fakes.make_template(tmp)
            cfg = fakes.write_config(tmp, templates_dir=tdir)
            code, out, err = self.run_cli(
                ["message", "draft", "--template", "nope", "--tenancy-id", "T-5",
                 "--month", "2026-10", "--config", cfg],
                transport=fakes.FakeTransport(),
            )
            self.assertEqual(code, 1)
            self.assertIn("error: unknown template nope", err)

    def test_never_sends(self):
        # Scenario: never sends
        # Given any message draft invocation -> no send_mail/notification call, no external
        # message emitted (SR7).
        with tempfile.TemporaryDirectory() as tmp:
            tdir = fakes.make_template(tmp)
            cfg, argv = self._run(tmp, tdir)
            transport = fakes.FakeTransport()
            feishu = fakes.FakeFeishu()
            code, out, err = self.run_cli(argv, transport=transport, feishu=feishu)
            self.assertEqual(code, 0, err)
            self.assertEqual(transport.calls, [], "no REST call (incl. send_mail) may leave the CLI")
            self.assertEqual(feishu.notifications, [], "no Feishu notify may fire")
            self.assertIn("Dear Alice", out)


if __name__ == "__main__":
    unittest.main()