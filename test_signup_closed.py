"""Public school signup is closed, and closed means no row is written.

WHY THIS FILE EXISTS
--------------------
The public landing page was advertising "Get Early Access" at an OPEN signup
form while five write routes take a student_id from the URL and never check
the student belongs to the signed-in teacher:

    POST /teacher/students/{id}/payment              no ownership check at all
    POST /teacher/students/{id}/charge               checks the student exists
    POST /teacher/students/{id}/attendance           checks the student exists
    POST /api/mobile/teacher/students/{id}/charge    checks the student exists
    POST /api/mobile/teacher/students/{id}/payment   checks the student exists

Any teacher account can move money on any student at any other school, and
the ledger row lands under the attacker's school_id, so it corrupts both
schools' books. Reads are correctly scoped throughout; it is the writes that
leak. Closing signup is the stopgap, exactly as 81d96ecc was for LessonBase.

WHAT IS PINNED
A redirect or a 403 is not the same as "nothing happened". The assertion that
matters is that the schools file has no new row after a full, valid POST —
the earlier stopgap in the other repo was verified that way for the same
reason.

This is the first test file in this repo. It patches /data the way the other
repo's suites do, since main.py writes there at import time.
"""
import builtins
import csv
import importlib
import os
import sys
import tempfile

import pytest

# main.py creates its CSVs under /data at import time, which cannot exist on
# macOS. Redirect before importing, and leave the patches in place — the
# module reads those paths again on every request.
_DATA = tempfile.mkdtemp()
_o, _e, _m = builtins.open, os.path.exists, os.makedirs


def _redir(p):
    return _DATA + str(p)[5:] if isinstance(p, (str, bytes)) and str(p).startswith("/data") else p


builtins.open = lambda f, *a, **k: _o(_redir(f), *a, **k)
os.path.exists = lambda p: _e(_redir(p))
os.makedirs = lambda p, *a, **k: _m(_redir(p), *a, **k)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret-for-signup-closed")
import main  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="https://testserver")

def _valid(tag):
    """A fresh email per test.

    Sharing one made the tests order-dependent: the first POST created the
    school, so a later POST hit "email already registered" and produced no
    cookie for reasons that had nothing to do with signup being closed. It
    passed while proving nothing.
    """
    return {"school_name": "Test School", "owner_name": "Test Owner",
            "email": f"stranger-{tag}@example.test",
            "password": "a-long-enough-password"}


def _schools():
    path = _redir(main.SCHOOLS_FILE)
    if not _e(path):
        return []
    with _o(path, "r") as f:
        return list(csv.DictReader(f))


def test_the_flag_is_off():
    """Named so that turning it on without reading the module comment fails
    something visible."""
    assert main.SIGNUP_OPEN is False, (
        "signup was reopened — the unscoped write routes must be fixed and "
        "covered by a cross-school regression test first")


def test_the_signup_page_does_not_serve_a_form():
    r = client.get("/school/signup")
    assert r.status_code == 403
    assert "<form" not in r.text.lower(), "the signup form is still being served"
    assert "Not open yet" in r.text


def test_posting_a_valid_signup_creates_no_school():
    """The assertion that matters, and it is checked FIRST.

    It originally sat behind an assert on the status code, so a build that
    answered 403 and still wrote the row would have failed on the status line
    and never reached the row count — the real check would not have run. The
    status is asserted afterwards.
    """
    data   = _valid("row")
    before = len(_schools())
    r      = client.post("/school/signup", data=data, follow_redirects=False)

    after = _schools()
    assert len(after) == before, "a school account was created while signup was closed"
    assert not any(s.get("owner_email") == data["email"] for s in after)
    assert r.status_code == 403


def test_no_session_cookie_is_handed_out():
    r = client.post("/school/signup", data=_valid("cookie"), follow_redirects=False)
    assert "school_id" not in r.cookies, (
        "a session cookie was issued for an account that was never created")


def test_the_login_page_no_longer_offers_to_create_a_school():
    """A link to a 403 is its own small bug."""
    r = client.get("/school/login")
    assert r.status_code == 200
    assert "/school/signup" not in r.text, "login still links to the closed signup"


def test_existing_schools_can_still_reach_the_login_page():
    """Closing the door must not lock out the people already inside."""
    assert client.get("/school/login").status_code == 200
    assert client.get("/teacher/login").status_code == 200
