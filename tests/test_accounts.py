"""Local accounts: hashing, sign-in, lockout, recovery, sessions, guest, preferences."""
from datetime import datetime, timedelta

import pytest

from navigator.data import accounts as A
from navigator.data.projects import Project, ProjectStore


@pytest.fixture
def store(tmp_path):
    return A.AccountStore(tmp_path)


def make(store, name="maria", pw="Sea-route-2027"):
    return store.create(name, pw, pw, "Maria P.", accept_terms=True)


def test_create_and_login_never_store_the_password(store):
    acc, code = make(store)
    raw = store.path.read_text(encoding="utf-8")
    assert "Sea-route-2027" not in raw and code not in raw
    assert len(code) == 14 and code.count("-") == 2
    assert store.login("MARIA ", "Sea-route-2027").id == acc.id
    assert store.find("maria").display_name == "Maria P." and not acc.needs_terms


@pytest.mark.parametrize("name,pw,confirm,terms,code", [
    ("ab", "longenough", "longenough", True, "auth.err.username"),
    ("Μαρία", "longenough", "longenough", True, "auth.err.username"),
    ("nikos", "short", "short", True, "auth.err.short"),
    ("nikos", "longenough", "different1", True, "auth.err.mismatch"),
    ("nikos", "longenough", "longenough", False, "auth.err.terms"),
])
def test_create_validation(store, name, pw, confirm, terms, code):
    with pytest.raises(A.AccountError) as e:
        store.create(name, pw, confirm, accept_terms=terms)
    assert e.value.code == code


def test_username_taken_and_unknown(store):
    make(store)
    with pytest.raises(A.AccountError, match="auth.err.taken"):
        make(store)
    with pytest.raises(A.AccountError, match="auth.err.unknown"):
        store.login("nobody", "x")


def test_lockout_doubles_and_clears(store):
    make(store)
    t = datetime(2026, 10, 27, 12, 0).astimezone()
    for k in range(A.LOCK_AFTER - 1):
        with pytest.raises(A.AccountError) as e:
            store.login("maria", "wrong", at=t)
        assert e.value.code == "auth.err.password" and e.value.fmt["left"] == A.LOCK_AFTER - 1 - k
    with pytest.raises(A.AccountError) as e:
        store.login("maria", "wrong", at=t)
    assert e.value.code == "auth.err.locked" and e.value.fmt["s"] == 30
    with pytest.raises(A.AccountError, match="auth.err.locked"):        # even the right password waits
        store.login("maria", "Sea-route-2027", at=t + timedelta(seconds=10))
    assert store.login("maria", "Sea-route-2027", at=t + timedelta(seconds=31))
    assert store.find("maria").lock_level == 0


def test_recovery_code_resets_and_is_replaced(store):
    _acc, code = make(store)
    with pytest.raises(A.AccountError, match="auth.err.code"):
        store.reset_password("maria", "AAAA-BBBB-CCCC", "new-password-1", "new-password-1")
    _acc, new_code = store.reset_password("maria", code.lower(), "new-password-1", "new-password-1")
    assert new_code != code
    assert store.login("maria", "new-password-1")
    with pytest.raises(A.AccountError, match="auth.err.code"):          # a code works once
        store.reset_password("maria", code, "another-pass-2", "another-pass-2")


def test_session_expires(store):
    acc, _ = make(store)
    t = datetime(2026, 10, 27).astimezone()
    store.remember(acc, at=t)
    assert A.AccountStore(store.folder).remembered(at=t + timedelta(days=29)).id == acc.id
    assert A.AccountStore(store.folder).remembered(at=t + timedelta(days=31)) is None
    store.remember(None)
    assert store.remembered() is None


def test_guest_starts_empty_and_prefs_persist(store):
    with pytest.raises(A.AccountError, match="auth.err.terms"):
        store.start_guest(False)
    g = store.start_guest(True)
    ProjectStore(store.projects_dir(g)).save(Project(name="draft"))
    store.set_prefs(g, language="en", theme="dark")
    g2 = store.start_guest(True)
    assert ProjectStore(store.projects_dir(g2)).list() == []
    assert g2.prefs == {"language": "en", "theme": "dark"}


def test_first_account_takes_over_earlier_projects(tmp_path):
    legacy = ProjectStore(tmp_path / "projects")
    legacy.save(Project(name="before accounts"))
    store = A.AccountStore(tmp_path)
    acc, _ = make(store)
    mine = ProjectStore(store.projects_dir(acc)).list()
    assert [p.name for p in mine] == ["before accounts"] and legacy.list() == []
    other, _ = make(store, "nikos")
    assert ProjectStore(store.projects_dir(other)).list() == []


def test_delete_and_change_password(store):
    acc, _ = make(store)
    store.change_password(acc, "Sea-route-2027", "changed-pass-9", "changed-pass-9")
    assert store.login("maria", "changed-pass-9")
    with pytest.raises(A.AccountError):
        store.delete(acc, "wrong")
    store.delete(store.find("maria"), "changed-pass-9")
    assert store.find("maria") is None


def test_strength_meter():
    assert A.password_strength("short") == 0
    assert A.password_strength("abcdefgh") == 1
    assert A.password_strength("Abcdefgh1234") >= 3
    assert A.password_strength("Abcdefgh1234!xyz") == 4
