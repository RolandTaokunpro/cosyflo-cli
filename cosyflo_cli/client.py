"""HTTP client over the Cosyflo Laravel REST API.

One command = one REST call = one rendered result. Maps the Laravel envelope
{code, error|message, data} to typed output; non-200 -> UpstreamError (exit 4).
The Bearer token is never included in any exception text.
"""
import requests

from .errors import UpstreamError

API_TIMEOUT = 60


class CosyfloClient:
    def __init__(self, base_url, token, transport=None, timeout=API_TIMEOUT):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token
        self.transport = transport or requests.Session()
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def _url(self, path):
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _handle(resp):
        try:
            body = resp.json()
        except Exception:
            body = None
        status = getattr(resp, "status_code", 0)
        if status != 200:
            detail = ""
            if isinstance(body, dict):
                detail = str(body.get("error") or body.get("message") or "")
            raise UpstreamError(f"upstream error: HTTP {status} {detail}".rstrip(), code=status)
        if isinstance(body, dict):
            code = body.get("code")
            if code is not None and int(code) != 200:
                detail = str(body.get("error") or body.get("message") or "")
                raise UpstreamError(f"upstream error: {code} {detail}".rstrip(), code=int(code))
            return body.get("data")
        return body

    def get(self, path, params=None):
        resp = self.transport.get(
            self._url(path), params=params, headers=self.headers, timeout=self.timeout
        )
        return self._handle(resp)

    def post(self, path, data=None):
        resp = self.transport.post(
            self._url(path), data=data, headers=self.headers, timeout=self.timeout
        )
        return self._handle(resp)


def resolve_operator(client):
    """Operator identity from the authenticated service account (D8) — never a
    caller-supplied field. Falls back to 'unresolved' rather than blocking the
    mutation's audit trail."""
    try:
        data = client.get("common/get_user_info")
        user = (data or {}).get("user") or {}
        name = user.get("name") or " ".join(
            part for part in (user.get("firstname"), user.get("lastname")) if part
        )
        return name.strip() or "unresolved"
    except Exception:
        return "unresolved"