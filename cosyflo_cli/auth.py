"""Runtime credential fetch (SR1): token via `op read` (default) or env (dev/staging).

The token never reaches stdout, stderr, the audit log, or any error message.
Failure is reported as the generic 'cannot fetch credential' — no token material,
no vault content.
"""
import os
import subprocess

from .errors import AuthError

ENV_TOKEN_VAR = "COSYFLO_API_TOKEN"
CREDENTIAL_ERROR = "cannot fetch credential"


def _run_op(argv):
    """Real `op read` — runs the 1Password CLI. Can block on biometric unlock."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=90, check=False)
    except (subprocess.TimeoutExpired, OSError):
        raise AuthError(CREDENTIAL_ERROR)
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token:
        raise AuthError(CREDENTIAL_ERROR)
    return token


def fetch_token(config, op_runner=None):
    """Resolve the service-account api_token per config['token'].

    source 'op'  : `op read <op_ref>` at runtime (production path, spec D2).
    source 'env' : COSYFLO_API_TOKEN env var — dev/staging convenience only
                   (documented deviation: lets the smoke demo run where `op`
                   cannot approve biometric unlock headlessly).
    """
    spec = config.get("token") or {}
    source = spec.get("source", "op")
    if source == "op":
        ref = spec.get("op_ref")
        if not ref:
            raise AuthError(CREDENTIAL_ERROR)
        runner = op_runner or _run_op
        return runner(["op", "read", ref])
    if source == "env":
        token = os.environ.get(ENV_TOKEN_VAR, "").strip()
        if not token:
            raise AuthError(CREDENTIAL_ERROR)
        return token
    raise AuthError(CREDENTIAL_ERROR)