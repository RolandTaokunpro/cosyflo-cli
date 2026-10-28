"""Config loading: base URL + 1Password vault reference only — never secrets (spec §8)."""
import copy
import json
import os

from .errors import ValidationError

DEFAULTS = {
    "base_url": "https://cosyflo-api.onrender.com/api/v1",
    "token": {"source": "op", "op_ref": "op://Cosyflo/cosyflo-service-account/api_token"},
    "audit": {"path": "~/.cosyflo-cli/audit.log"},
    "feishu": {
        "webhook_url": None,
        "approval_poll_url": None,
        "approval_timeout_seconds": 300,
    },
    "templates_dir": None,
}

DEFAULT_PATH = "~/.cosyflo-cli/config.json"


def _deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load_config(path=None):
    """Load config from `path` (or the default location) over DEFAULTS.

    The default location being absent is not an error — built-in defaults apply.
    An explicitly-passed path that does not exist IS an error (typo guard).
    """
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        resolved = os.path.expanduser(path)
        if not os.path.exists(resolved):
            raise ValidationError(f"config file not found: {path}")
    else:
        resolved = os.path.expanduser(os.environ.get("COSYFLO_CONFIG", DEFAULT_PATH))
        if not os.path.exists(resolved):
            return cfg
    with open(resolved) as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValidationError("config file must be a JSON object")
    _deep_merge(cfg, loaded)
    if cfg["token"].get("source") not in ("op", "env"):
        raise ValidationError(f"unknown token source '{cfg['token'].get('source')}'")
    return cfg