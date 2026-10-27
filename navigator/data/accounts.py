"""Local accounts (decision 0015): pure Python, no Qt, nothing leaves the computer.

- Passwords and recovery codes are stored only as scrypt hashes (n = 2^14, r = 8, p = 1, 16-byte salt).
- A recovery code, shown once at sign-up, is the only way to reset a forgotten password.
- After five wrong passwords an account is locked for 30 seconds (then 60, 120, …).
- "Keep me signed in" stores the user's id with an expiry date (30 days) in the same file.
- Each account has its own projects folder and preferences (language, theme, animations, tour seen).
- A guest works in a separate folder that is emptied when a new guest session starts.
- The first account created takes over projects made before accounts existed.

File: <data folder>/accounts.json, written atomically.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .projects import default_dir, now

TERMS_VERSION = "1.0"
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MIN_PASSWORD = 8
LOCK_AFTER = 5
LOCK_SECONDS = 30
SESSION_DAYS = 30
GUEST = "guest"


class AccountError(ValueError):
    """A problem the user can fix; `code` is a translation key suffix (e.g. 'auth.err.password')."""

    def __init__(self, code: str, **fmt):
        super().__init__(code)
        self.code, self.fmt = code, fmt


def _hash(secret: str, salt: bytes) -> str:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, **SCRYPT).hex()


def _new_hash(secret: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    return salt.hex(), _hash(secret, salt)


def _check(secret: str, salt_hex: str, digest: str) -> bool:
    return hmac.compare_digest(_hash(secret, bytes.fromhex(salt_hex)), digest)


def recovery_code() -> str:
    """12 characters in three groups, without look-alike letters (e.g. 7KQM-2XRW-9DPA)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(12))
    return "-".join(raw[i:i + 4] for i in (0, 4, 8))


def password_strength(pw: str) -> int:
    """0–4: length and variety (for the meter; the only hard rule is the minimum length)."""
    if len(pw) < MIN_PASSWORD:
        return 0
    kinds = sum(bool(re.search(p, pw)) for p in (r"[a-zα-ω]", r"[A-ZΑ-Ω]", r"\d", r"[^\w\s]"))
    score = 1 + (len(pw) >= 12) + (kinds >= 3) + (kinds == 4 and len(pw) >= 14)
    return min(score, 4)


@dataclass
class Account:
    id: str
    username: str
    display_name: str
    salt: str = ""
    hash: str = ""
    recovery_salt: str = ""
    recovery_hash: str = ""
    created: str = field(default_factory=now)
    last_login: str = ""
    terms_version: str = ""
    terms_accepted: str = ""
    prefs: dict = field(default_factory=dict)       # language, theme, animations, tour_done
    failed: int = 0
    locked_until: str = ""
    lock_level: int = 0

    @property
    def is_guest(self) -> bool:
        return self.id == GUEST

    @property
    def needs_terms(self) -> bool:
        return self.terms_version != TERMS_VERSION

    def public(self) -> dict:
        return {"id": self.id, "username": self.username, "display_name": self.display_name}


class AccountStore:
    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder else default_dir().parent
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "accounts.json"
        self.data = self._read()

    # ------------------------------------------------------------------ file
    def _read(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d.setdefault("format", 1)
        d.setdefault("accounts", [])
        d.setdefault("session", None)
        d.setdefault("setup_done", False)
        d.setdefault("guest", {})
        return d

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _accounts(self) -> list[Account]:
        return [Account(**a) for a in self.data["accounts"]]

    def _save(self, acc: Account) -> None:
        rows = [a for a in self.data["accounts"] if a["id"] != acc.id]
        rows.append(asdict(acc))
        self.data["accounts"] = rows
        self._write()

    # ------------------------------------------------------------------ queries
    @property
    def setup_done(self) -> bool:
        return bool(self.data.get("setup_done"))

    def mark_setup_done(self) -> None:
        self.data["setup_done"] = True
        self._write()

    def accounts(self) -> list[Account]:
        return sorted(self._accounts(), key=lambda a: a.last_login or a.created, reverse=True)

    def find(self, username: str) -> Account | None:
        u = username.strip().lower()
        return next((a for a in self._accounts() if a.username == u), None)

    def get(self, account_id: str) -> Account | None:
        if account_id == GUEST:
            return self.guest()
        return next((a for a in self._accounts() if a.id == account_id), None)

    def projects_dir(self, acc: Account) -> Path:
        d = self.folder / ("guest" if acc.is_guest else f"users/{acc.id}") / "projects"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ sign up / in
    def create(self, username: str, password: str, confirm: str, display_name: str = "",
               accept_terms: bool = False) -> tuple[Account, str]:
        """New account; returns it with its recovery code (shown to the user once)."""
        u = username.strip().lower()
        if not USERNAME.match(u):
            raise AccountError("auth.err.username")
        if self.find(u) is not None:
            raise AccountError("auth.err.taken")
        if len(password) < MIN_PASSWORD:
            raise AccountError("auth.err.short", n=MIN_PASSWORD)
        if password != confirm:
            raise AccountError("auth.err.mismatch")
        if not accept_terms:
            raise AccountError("auth.err.terms")
        first = not self._accounts()
        salt, digest = _new_hash(password)
        code = recovery_code()
        rsalt, rdigest = _new_hash(code)
        acc = Account(uuid.uuid4().hex[:12], u, display_name.strip() or u, salt, digest, rsalt, rdigest,
                      terms_version=TERMS_VERSION, terms_accepted=now(), last_login=now())
        self._save(acc)
        if first:
            self._adopt_legacy(acc)
        return acc, code

    def login(self, username: str, password: str, at: datetime | None = None) -> Account:
        at = at or datetime.now().astimezone()
        acc = self.find(username)
        if acc is None:
            raise AccountError("auth.err.unknown")
        if acc.locked_until and datetime.fromisoformat(acc.locked_until) > at:
            left = int((datetime.fromisoformat(acc.locked_until) - at).total_seconds()) + 1
            raise AccountError("auth.err.locked", s=left)
        if not _check(password, acc.salt, acc.hash):
            acc.failed += 1
            if acc.failed >= LOCK_AFTER:
                seconds = LOCK_SECONDS * 2 ** acc.lock_level
                acc.locked_until = (at + timedelta(seconds=seconds)).isoformat(timespec="seconds")
                acc.lock_level += 1
                acc.failed = 0
                self._save(acc)
                raise AccountError("auth.err.locked", s=seconds)
            self._save(acc)
            raise AccountError("auth.err.password", left=LOCK_AFTER - acc.failed)
        acc.failed, acc.lock_level, acc.locked_until = 0, 0, ""
        acc.last_login = now()
        self._save(acc)
        return acc

    def accept_terms(self, acc: Account) -> Account:
        acc.terms_version, acc.terms_accepted = TERMS_VERSION, now()
        if acc.is_guest:
            self.data["guest"]["terms_version"] = TERMS_VERSION
            self._write()
        else:
            self._save(acc)
        return acc

    def reset_password(self, username: str, code: str, password: str, confirm: str) -> tuple[Account, str]:
        """With the recovery code; a new recovery code replaces the used one."""
        acc = self.find(username)
        if acc is None:
            raise AccountError("auth.err.unknown")
        if not _check(code.strip().upper(), acc.recovery_salt, acc.recovery_hash):
            raise AccountError("auth.err.code")
        if len(password) < MIN_PASSWORD:
            raise AccountError("auth.err.short", n=MIN_PASSWORD)
        if password != confirm:
            raise AccountError("auth.err.mismatch")
        acc.salt, acc.hash = _new_hash(password)
        new_code = recovery_code()
        acc.recovery_salt, acc.recovery_hash = _new_hash(new_code)
        acc.failed, acc.lock_level, acc.locked_until = 0, 0, ""
        self._save(acc)
        return acc, new_code

    def change_password(self, acc: Account, old: str, password: str, confirm: str) -> None:
        if not _check(old, acc.salt, acc.hash):
            raise AccountError("auth.err.password", left=LOCK_AFTER)
        if len(password) < MIN_PASSWORD:
            raise AccountError("auth.err.short", n=MIN_PASSWORD)
        if password != confirm:
            raise AccountError("auth.err.mismatch")
        acc.salt, acc.hash = _new_hash(password)
        self._save(acc)

    def delete(self, acc: Account, password: str) -> None:
        if not _check(password, acc.salt, acc.hash):
            raise AccountError("auth.err.password", left=LOCK_AFTER)
        self.data["accounts"] = [a for a in self.data["accounts"] if a["id"] != acc.id]
        if (self.data.get("session") or {}).get("user") == acc.id:
            self.data["session"] = None
        self._write()
        shutil.rmtree(self.folder / f"users/{acc.id}", ignore_errors=True)

    # ------------------------------------------------------------------ guest
    def guest(self) -> Account:
        g = self.data.get("guest", {})
        return Account(GUEST, GUEST, "", terms_version=g.get("terms_version", ""), prefs=dict(g.get("prefs", {})))

    def start_guest(self, accept_terms: bool) -> Account:
        if not accept_terms:
            raise AccountError("auth.err.terms")
        shutil.rmtree(self.folder / "guest", ignore_errors=True)       # every guest session starts empty
        self.data["guest"] = {**self.data.get("guest", {}), "terms_version": TERMS_VERSION}
        self._write()
        return self.guest()

    # ------------------------------------------------------------------ preferences and session
    def set_prefs(self, acc: Account, **prefs) -> Account:
        acc.prefs.update(prefs)
        if acc.is_guest:
            self.data["guest"]["prefs"] = acc.prefs
            self._write()
        else:
            self._save(acc)
        return acc

    def remember(self, acc: Account | None, at: datetime | None = None) -> None:
        if acc is None or acc.is_guest:
            self.data["session"] = None
        else:
            at = at or datetime.now().astimezone()
            self.data["session"] = {"user": acc.id, "until": (at + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")}
        self._write()

    def remembered(self, at: datetime | None = None) -> Account | None:
        s = self.data.get("session")
        if not s:
            return None
        at = at or datetime.now().astimezone()
        if datetime.fromisoformat(s["until"]) < at:
            self.data["session"] = None
            self._write()
            return None
        return self.get(s["user"])

    # ------------------------------------------------------------------ before accounts existed
    def _adopt_legacy(self, acc: Account) -> int:
        """Move projects saved before accounts existed into the first account's folder."""
        legacy = self.folder / "projects"
        if not legacy.is_dir() or legacy.resolve() == self.projects_dir(acc).resolve():
            return 0
        n = 0
        for f in legacy.glob("*.dnproj"):
            target = self.projects_dir(acc) / f.name
            if not target.exists():
                shutil.move(str(f), str(target))
                n += 1
        return n
