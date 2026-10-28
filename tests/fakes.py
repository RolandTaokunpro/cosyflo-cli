"""Shared fakes/fixtures for the cosyflo-cli scenario tests (no live API)."""
import io
import json
import os
import unittest

BASE_URL = "https://api.example.test/api/v1"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {"code": 200, "error": "", "data": []}

    def json(self):
        return self._body


class FakeTransport:
    """requests-compatible double: records every call, returns canned responses."""

    def __init__(self, responses=None, default=None):
        self.calls = []
        self.responses = responses or {}
        self.default = default or FakeResponse()

    def _match(self, method, url):
        for (m, frag), resp in self.responses.items():
            if m == method and frag in url:
                return resp
        return self.default

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
        return self._match("GET", url)

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        self.calls.append({"method": "POST", "url": url, "data": data, "json": json, "headers": headers})
        return self._match("POST", url)

    def calls_to(self, fragment):
        return [c for c in self.calls if fragment in c["url"]]

    def rest_calls(self):
        """Calls aimed at the Cosyflo API (as opposed to a Feishu webhook)."""
        return [c for c in self.calls if BASE_URL in c["url"]]


class FakeOpRunner:
    """Replaces `op read <ref>` at runtime."""

    def __init__(self, token=None, fail=False):
        self.token = token
        self.fail = fail
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        from cosyflo_cli.errors import AuthError
        if self.fail:
            raise AuthError("cannot fetch credential")
        if not self.token:
            raise AuthError("cannot fetch credential")
        return self.token


class FakeFeishu:
    """Double for the Feishu notify/approval channel."""

    def __init__(self, decision="unconfigured"):
        self.decision = decision
        self.approval_requests = []
        self.notifications = []

    def notify_mutation(self, entry):
        self.notifications.append(entry)
        return "ok"

    def request_approval(self, action, payload):
        self.approval_requests.append({"action": action, "payload": payload})
        return self.decision


DEFAULT_CONFIG = {
    "base_url": BASE_URL,
    "token": {"source": "env", "op_ref": "op://Test/cosyflo-service/api_token"},
    "audit": {"path": "audit.log"},  # overridden with tmpdir per test
    "feishu": {"webhook_url": None, "approval_poll_url": None, "approval_timeout_seconds": 2},
    "templates_dir": None,
}


def write_config(tmpdir, **overrides):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    cfg["audit"]["path"] = os.path.join(str(tmpdir), "audit.log")
    for key, value in overrides.items():
        cfg[key] = value
    path = os.path.join(str(tmpdir), "config.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    return path


def make_template(tmpdir, name="chase-standard", content=None):
    tdir = os.path.join(str(tmpdir), "templates")
    os.makedirs(tdir, exist_ok=True)
    content = content or (
        "Dear {tenant_name},\n"
        "Tenancy {tenancy_id} is £{amount_short} short for {month}.\n"
    )
    with open(os.path.join(tdir, name + ".txt"), "w") as f:
        f.write(content)
    return tdir


class ScenarioTest(unittest.TestCase):
    """Base: env token in/out, CLI runner with injected fakes, capture streams."""

    TOKEN = "tok-secret-xyz"

    def setUp(self):
        self._old = os.environ.get("COSYFLO_API_TOKEN")
        os.environ["COSYFLO_API_TOKEN"] = self.TOKEN

    def tearDown(self):
        if self._old is None:
            os.environ.pop("COSYFLO_API_TOKEN", None)
        else:
            os.environ["COSYFLO_API_TOKEN"] = self._old

    def run_cli(self, argv, transport=None, op_runner=None, feishu=None):
        from cosyflo_cli import cli
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            argv,
            transport=transport,
            op_runner=op_runner,
            feishu=feishu,
            stdout=out,
            stderr=err,
        )
        return code, out.getvalue(), err.getvalue()

    def read_audit(self, path):
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]