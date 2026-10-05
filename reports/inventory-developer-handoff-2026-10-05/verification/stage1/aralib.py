"""Shared verifier plumbing: loopback-only HTTP sessions, evidence log, sentinel scan.

Stdlib only. Nothing here talks to a non-loopback host: `Target` refuses it.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

VERIFY = Path(__file__).resolve().parent.parent
WORKSPACE = VERIFY.parents[2]
FIXTURES = VERIFY / "fixtures" / "out"
CONTRACT_MAP = VERIFY / "contract_map.json"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
SENTINEL_RE = re.compile(r"sntl-[a-z]+-[a-z0-9]+-[0-9a-f]{6}", re.I)
UNSAFE_ENV = ("DATABASE_URL", "ARA_MAP_DATABASE_URL", "ARA_MAP_TEST_DATABASE_URL")
PUBLIC_TERRAIN_KEYS = frozenset((
    "id", "revision_id", "terreno", "estado", "municipio", "direccion", "superficie_m2",
    "superficie_ha", "afectaciones_pct", "afectaciones_m2", "lat", "lon", "asking_price",
    "asking_m2", "moneda", "price_on_request", "availability", "public_description", "published_at",
))
LIST_ENVELOPE = frozenset(("terrenos", "total", "next_cursor", "facets"))


def require_loopback(url: str) -> str:
    host = urlsplit(url).hostname or ""
    if host not in LOOPBACK:
        raise SystemExit(f"REFUSING non-loopback target {url!r}")
    print(f"[target] {url}", flush=True)
    return url.rstrip("/")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def contract_map() -> dict:
    return load_json(CONTRACT_MAP)


# --------------------------------------------------------------------------- evidence

class Evidence:
    """Append-only JSONL of every request/response, with secrets redacted."""

    def __init__(self, path: Path, secrets: list[str]) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._secrets = [s for s in secrets if s]
        self.results: list[dict] = []
        self._lock = threading.Lock()

    def redact(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "«redacted»")
        return text  # cookie values are never logged; see Session.request

    def log(self, entry: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(self.redact(json.dumps(entry, ensure_ascii=False, default=str)) + "\n")

    def result(self, case: str, check: str, status: str, detail: Any = None) -> None:
        """status: PASS | FAIL | SKIP | INFO."""
        row = {"case": case, "check": check, "status": status, "detail": detail}
        self.results.append(row)
        self.log({"result": row})
        print(f"  [{status}] {case} :: {check}" + (f" -- {detail}" if status != "PASS" and detail else ""),
              flush=True)


# --------------------------------------------------------------------------- HTTP

@dataclass
class Resp:
    status: int
    headers: dict[str, str]
    set_cookies: list[str]
    body: bytes
    ms: float

    @property
    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def text_for_scan(self) -> str:
        """Body (incl. unzipped xlsx parts), headers and cookies, for sentinel scans."""
        parts = [self.body.decode("utf-8", "replace"), json.dumps(self.headers), *self.set_cookies]
        if self.body[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(self.body)) as z:
                    parts += [z.read(n).decode("utf-8", "replace") for n in z.namelist()]
            except zipfile.BadZipFile:
                pass
        return "\n".join(parts)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
        return None


@dataclass
class Session:
    """One browser-like identity: its own cookie jar, same-origin headers by default."""

    base: str
    name: str
    evidence: Evidence
    cookies: dict[str, str] = field(default_factory=dict)

    def origin(self) -> str:
        parts = urlsplit(self.base)
        return f"{parts.scheme}://{parts.netloc}"

    def request(self, method: str, path: str, body: Any = None, headers: dict | None = None,
                raw: bytes | None = None, cookies: bool = True, origin: str | None = "same") -> Resp:
        url = self.base + path
        require_host = urlsplit(url).hostname
        if require_host not in LOOPBACK:
            raise SystemExit(f"REFUSING {url}")
        h = {"Accept": "application/json"}
        if origin == "same" and method not in ("GET", "HEAD"):
            h["Origin"] = self.origin()
        elif origin not in (None, "same"):
            h["Origin"] = origin
        data = raw
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            h["Content-Type"] = "application/json"
        if cookies and self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        opener = urllib.request.build_opener(_NoRedirect)
        t0 = time.perf_counter()
        try:
            with opener.open(req, timeout=30) as r:
                status, hdrs, payload = r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            status, hdrs, payload = e.code, e.headers, e.read()
        ms = (time.perf_counter() - t0) * 1000
        set_cookies = hdrs.get_all("Set-Cookie") or []
        resp = Resp(status, {k: v for k, v in hdrs.items() if k.lower() != "set-cookie"},
                    set_cookies, payload, ms)
        if cookies:
            self._absorb(set_cookies)
        self.evidence.log({"session": self.name, "method": method, "path": path,
                           "req_headers": {k: v for k, v in h.items() if k != "Cookie"},
                           "had_cookie": "Cookie" in h, "req_body": body if raw is None else f"<{len(raw)} bytes>",
                           "status": status, "ms": round(ms, 1), "resp_headers": resp.headers,
                           "set_cookie_attrs": [c.split(";", 1)[1] if ";" in c else "" for c in set_cookies],
                           "resp_body": payload[:4000].decode("utf-8", "replace")})
        return resp

    def _absorb(self, set_cookies: list[str]) -> None:
        for c in set_cookies:
            first = c.split(";", 1)[0]
            name, _, value = first.partition("=")
            attrs = c.lower()
            if not value or "max-age=0" in attrs or "expires=thu, 01 jan 1970" in attrs:
                self.cookies.pop(name.strip(), None)
            else:
                self.cookies[name.strip()] = value.strip()

    # convenience
    def get(self, path: str, **k: Any) -> Resp:
        return self.request("GET", path, **k)

    def post(self, path: str, body: Any = None, **k: Any) -> Resp:
        return self.request("POST", path, body=body, **k)

    def patch(self, path: str, body: Any = None, **k: Any) -> Resp:
        return self.request("PATCH", path, body=body, **k)

    def login(self, username: str, password: str) -> Resp:
        return self.post("/api/login", {"username": username, "password": password})


# --------------------------------------------------------------------------- sentinels

class Scanner:
    def __init__(self, extra_secrets: list[str] = ()) -> None:
        self.known = set((FIXTURES / "sentinels.txt").read_text().split())
        for legacy in VERIFY.glob("runs/**/*.db.manifest.json"):
            self.known.update(load_json(legacy).get("sentinels", []))
        self.secrets = [s for s in extra_secrets if s]
        self.known_lower = {s.lower() for s in self.known}

    def hits(self, text: str) -> list[str]:
        low = text.lower()
        found = {m.group(0) for m in SENTINEL_RE.finditer(text)}
        found |= {s for s in self.secrets if s.lower() in low}
        return sorted(found)


# --------------------------------------------------------------------------- fixtures

def users() -> list[dict]:
    return load_json(FIXTURES / "users.json")


def records(name: str = "master_120.json") -> dict[str, dict]:
    return {r["key"]: r for r in load_json(FIXTURES / name)}


def to_payload(draft: dict) -> dict:
    """Logical fixture draft -> backend field names (contract_map.json)."""
    names = contract_map()["private_field_names"]
    out = {}
    for k, v in draft.items():
        if k in names:
            if names[k] is None:
                continue
            out[names[k]] = v
        else:
            out[k] = v
    return out


def from_payload(draft: dict) -> dict:
    names = {v: k for k, v in contract_map()["private_field_names"].items() if v}
    return {names.get(k, k): v for k, v in draft.items()}


# --------------------------------------------------------------------------- server lifecycle

def safe_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in UNSAFE_ENV}
    env.pop("ARA_MAP_PUBLIC_EDIT", None)
    env.update(extra or {})
    return env


def assert_disposable_path(p: Path) -> Path:
    p = p.resolve()
    for forbidden in (WORKSPACE / "datos", WORKSPACE / "api" / "data"):
        if p.is_relative_to(forbidden.resolve()):
            raise SystemExit(f"REFUSING workspace data path {p}")
    tmp_roots = [Path(tempfile.gettempdir()).resolve(), Path("/private/tmp"), Path("/private/var/folders"),
                 (VERIFY / "runs").resolve()]
    if not any(p.is_relative_to(r) for r in tmp_roots):
        raise SystemExit(f"REFUSING non-temporary database path {p}")
    return p


class Server:
    """Starts serve_target.py as a child process; restartable."""

    def __init__(self, mode: str, port: int, db: Path | None, log: Path,
                 extra_env: dict | None = None, app_root: Path = WORKSPACE, public_edit_env: bool = False) -> None:
        self.mode, self.port, self.db, self.log_path = mode, port, db, log
        self.extra_env, self.app_root, self.public_edit_env = extra_env or {}, app_root, public_edit_env
        self.proc: subprocess.Popen | None = None
        self.fault_marker: str | None = None
        self.url = require_loopback(f"http://127.0.0.1:{port}")

    def start(self) -> None:
        cmd = [sys.executable, str(VERIFY / "stage1" / "serve_target.py"), "--mode", self.mode,
               "--port", str(self.port), "--app-root", str(self.app_root)]
        if self.db:
            cmd += ["--db", str(assert_disposable_path(self.db))]
        if self.fault_marker:
            cmd += ["--fault-marker", self.fault_marker]
        env = safe_env(self.extra_env)
        if self.public_edit_env:  # proves the old bypass variable no longer opens anything
            cmd.append("--allow-public-edit-env")
            env["ARA_MAP_PUBLIC_EDIT"] = "1"
        if self.mode == "cloud":
            env["ARA_MAP_TEST_DATABASE_URL"] = os.environ["ARA_MAP_TEST_DATABASE_URL"]
        self._fh = self.log_path.open("a")
        self.proc = subprocess.Popen(cmd, env=env, stdout=self._fh, stderr=subprocess.STDOUT)
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit(f"server exited early; see {self.log_path}")
            try:
                urllib.request.urlopen(self.url + "/api/session", timeout=1)
                return
            except urllib.error.HTTPError:
                return
            except OSError:
                time.sleep(0.2)
        raise SystemExit("server did not start")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        self.proc = None

    def restart(self) -> None:
        self.stop()
        self.start()


def run_ops(template: list[str], db: Path | None, log: Path, stdin: str = "", **subst: str) -> None:
    """Run a backend operations command against the disposable target only.

    SQLite: {db} is a disposable path. Postgres: the URL travels in ARA_VERIFY_PG_URL
    (named via --url-env), never ARA_MAP_DATABASE_URL / DATABASE_URL.
    """
    values = {"python": sys.executable, "db": str(db or ""), **subst}
    cmd = [part.format(**values) for part in template]
    extra = {}
    if db:
        assert_disposable_path(db)
    else:
        url = os.environ["ARA_MAP_TEST_DATABASE_URL"]
        if urlsplit(url).hostname not in ("127.0.0.1", "localhost") or urlsplit(url).port != 55433:
            raise SystemExit("REFUSING ops command: not the verifier cluster")
        extra["ARA_VERIFY_PG_URL"] = url
    with log.open("a") as fh:
        fh.write(f"$ {' '.join(cmd)}\n")
        fh.flush()
        r = subprocess.run(cmd, input=stdin, text=True, cwd=WORKSPACE, env=safe_env(extra),
                           stdout=fh, stderr=subprocess.STDOUT, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"ops command failed ({r.returncode}): {cmd[1:4]}; see {log}")


def provision(user: dict, db: Path | None, log: Path) -> None:
    """Create one team account through scripts/cuentas.py; password via stdin only."""
    cm = contract_map()
    template = (cm.get("provision_cmd") or {}).get("local" if db else "cloud")
    if not template:
        raise SystemExit("contract_map.json provision_cmd is not set")
    stdin = (user["password"] + "\n") * int(cm.get("provision_password_repeats", 1))
    run_ops(template, db, log, stdin, username=user["username"], display_name=user["display_name"])
