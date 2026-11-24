import json
import os
from pathlib import Path

import httpx

BASE = "https://www.instapaper.com/api/2"
STATE = Path(os.environ.get("INSTAPAPER_CONFIG", Path.home() / ".config" / "instapaper" / "auth.json"))


class NeedsLogin(Exception):
    pass


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {}


def save(state: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.touch(mode=0o600)
    STATE.write_text(json.dumps(state, indent=2))


def token() -> str:
    t = os.environ.get("INSTAPAPER_TOKEN") or load().get("token")
    if not t:
        raise NeedsLogin("no token")
    return t


def request(method: str, path: str, params=None, body=None, bearer=None):
    r = httpx.request(
        method,
        BASE + path,
        params={k: v for k, v in (params or {}).items() if v is not None},
        json=body,
        headers={"Authorization": f"Bearer {bearer or token()}"},
        timeout=90,
    )
    if r.status_code == 401:
        raise NeedsLogin("token rejected")
    if r.status_code >= 400:
        try:
            err = r.json()["error"]
        except (ValueError, KeyError, TypeError):
            err = {"code": r.status_code, "message": r.text[:200]}
        raise ApiError(err.get("code", r.status_code), err.get("message"))
    return r.json() if r.content else None
