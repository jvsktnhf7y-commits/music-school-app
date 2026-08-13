"""A teacher at one school must not be able to touch another school's student.

WHY THIS FILE EXISTS
--------------------
Eight write routes took a student_id from the caller and acted on it without
checking the student belonged to the signed-in teacher. Any teacher account
could add or remove money on any student at any other school, write lesson
notes into their record, and record attendance against them — and the ledger
row landed under the ACTING teacher's school_id, so a single request corrupted
both schools' books at once.

Reads were correctly scoped throughout, which is exactly what made it easy to
miss: the student detail, edit and report pages all compare teacher_id.

WHY EIGHT AND NOT FIVE
The first pass grepped for routes with {student_id} in the path and found
five. Three more took student_id from the FORM BODY instead and were invisible
to that grep:

    POST /teacher/notes/add
    POST /teacher/payments/record        (moves money)
    POST /api/mobile/teacher/notes/add

The lesson is in the method, not the count: a grep over URL shapes does not
enumerate the ways a caller supplies an id. This file drives every route as a
real signed-in attacker instead.

WHAT IS ASSERTED
Not the response. A 303 or a 404 proves nothing on its own — the question is
whether the victim's row changed. Every test here reads the victim's balance,
ledger and notes back out of the CSVs and asserts they are untouched.
"""
import csv
import os
import sys

import pytest

from conftest import raw_exists, raw_open, redir   # /data patching lives there

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

BASE = "https://testserver"


def _rows(path, headers):
    p = redir(path)
    if not raw_exists(p):
        return []
    with raw_open(p, "r") as f:
        return list(csv.DictReader(f))


def _student(student_id):
    return next((s for s in _rows(main.STUDENTS_FILE, main.STUDENTS_HEADERS)
                 if s["student_id"] == student_id), None)


def _ledger_for(student_id):
    return [r for r in _rows(main.LEDGER_FILE, main.LEDGER_HEADERS)
            if r["student_id"] == student_id]


def _notes_for(student_id):
    return [r for r in _rows(main.NOTES_FILE, main.NOTES_HEADERS)
            if r["student_id"] == student_id]


def _make_school(tag):
    """One school, one teacher, one student — built by writing the CSVs
    directly, since public signup is deliberately closed."""
    school_id  = f"sch-{tag}"
    teacher_id = f"tch-{tag}"
    student_id = f"stu-{tag}"
    pw = main._hash_password("a-long-enough-password")
    main._append_csv(main.SCHOOLS_FILE, main.SCHOOLS_HEADERS, {
        "school_id": school_id, "name": f"School {tag}",
        "owner_email": f"owner-{tag}@example.test", "owner_name": "Owner",
        "password_hash": pw, "plan": "trial", "active": "true",
        "is_subscribed": "true", "trial_ends": "2099-01-01"})
    main._append_csv(main.TEACHERS_FILE, main.TEACHERS_HEADERS, {
        "teacher_id": teacher_id, "school_id": school_id,
        "name": f"Teacher {tag}", "email": f"teacher-{tag}@example.test",
        "password_hash": pw, "active": "true"})
    main._append_csv(main.STUDENTS_FILE, main.STUDENTS_HEADERS, {
        "student_id": student_id, "school_id": school_id,
        "teacher_id": teacher_id, "name": f"Student {tag}",
        "rate": "50", "prepaid": "100.00"})
    return {"school_id": school_id, "teacher_id": teacher_id,
            "student_id": student_id, "password_hash": pw}


@pytest.fixture(scope="module")
def world():
    a = _make_school("aaa")   # the attacker
    b = _make_school("bbb")   # the victim
    return {"a": a, "b": b}


@pytest.fixture
def attacker(world):
    """Signed in as school A's teacher, on the web."""
    c = TestClient(main.app, base_url=BASE)
    c.cookies.set("teacher_id",
                  main.issue_token("teacher", world["a"]["teacher_id"],
                                   world["a"]["password_hash"]))
    r = c.get("/teacher/dashboard", follow_redirects=False)
    assert r.status_code == 200, "attacker session is not valid; test proves nothing"
    return c


@pytest.fixture
def attacker_bearer(world):
    return {"Authorization": "Bearer " + main.issue_token(
        "teacher", world["a"]["teacher_id"], world["a"]["password_hash"])}


@pytest.fixture
def untouched(world):
    """Snapshot the victim, and hand back a checker each test calls itself.

    This was originally an autouse fixture that asserted during TEARDOWN. That
    was a trap: pytest reports a teardown failure as an ERROR and still marks
    the test PASSED, so with the guards reverted the summary read
    "11 passed, 8 errors" — the exact shape of a suite that looks green to
    anyone skimming. Asserted inside the test body instead, so a breach is a
    failure.
    """
    vid = world["b"]["student_id"]
    before = (_student(vid), len(_ledger_for(vid)), len(_notes_for(vid)))

    def check():
        after = (_student(vid), len(_ledger_for(vid)), len(_notes_for(vid)))
        assert after[0] == before[0], (
            f"the victim's student row changed: {before[0]} -> {after[0]}")
        assert after[1] == before[1], "a ledger row was written against the victim"
        assert after[2] == before[2], "a note was written against the victim"
    return check


# ── The five path-parameter routes ───────────────────────────────────────────

def test_cannot_record_a_payment_on_another_schools_student(attacker, world, untouched):
    attacker.post(f"/teacher/students/{world['b']['student_id']}/payment",
                  data={"amount": "500"}, follow_redirects=False)
    untouched()

def test_cannot_charge_another_schools_student(attacker, world, untouched):
    attacker.post(f"/teacher/students/{world['b']['student_id']}/charge",
                  data={"amount": "500"}, follow_redirects=False)
    untouched()

def test_cannot_record_attendance_for_another_schools_student(attacker, world, untouched):
    attacker.post(f"/teacher/students/{world['b']['student_id']}/attendance",
                  data={"date": "2026-09-01", "status": "Confirmed"},
                  follow_redirects=False)
    untouched()

def test_cannot_charge_another_schools_student_from_mobile(attacker_bearer, world, untouched):
    TestClient(main.app, base_url=BASE).post(
        f"/api/mobile/teacher/students/{world['b']['student_id']}/charge",
        json={"amount": 500}, headers=attacker_bearer)
    untouched()

def test_cannot_pay_another_schools_student_from_mobile(attacker_bearer, world, untouched):
    TestClient(main.app, base_url=BASE).post(
        f"/api/mobile/teacher/students/{world['b']['student_id']}/payment",
        json={"amount": 500}, headers=attacker_bearer)
    untouched()

# ── The three the URL grep missed ────────────────────────────────────────────

def test_cannot_write_a_note_into_another_schools_student(attacker, world, untouched):
    attacker.post("/teacher/notes/add",
                  data={"student_id": world["b"]["student_id"], "date": "2026-09-01",
                        "notes": "injected", "assignment": "injected"},
                  follow_redirects=False)
    untouched()

def test_cannot_record_a_payment_via_the_payments_form(attacker, world, untouched):
    """student_id comes from the form body here, which is why the first pass
    missed it. It moves money."""
    attacker.post("/teacher/payments/record",
                  data={"student_id": world["b"]["student_id"], "amount": "500",
                        "date": "2026-09-01", "notes": ""},
                  follow_redirects=False)
    untouched()

def test_cannot_write_a_mobile_note_into_another_schools_student(attacker_bearer, world, untouched):
    TestClient(main.app, base_url=BASE).post(
        "/api/mobile/teacher/notes/add",
        json={"student_id": world["b"]["student_id"], "date": "2026-09-01",
              "notes": "injected", "assignment": ""},
        headers=attacker_bearer)
    untouched()

# ── Reads, which were already correct and must stay that way ─────────────────

def test_cannot_read_another_schools_student(attacker, world, untouched):
    r = attacker.get(f"/teacher/students/{world['b']['student_id']}",
                     follow_redirects=False)
    assert r.status_code == 303, "another school's student detail page rendered"
    untouched()

def test_mobile_cannot_read_another_schools_student(attacker_bearer, world, untouched):
    r = TestClient(main.app, base_url=BASE).get(
        f"/api/mobile/teacher/students/{world['b']['student_id']}",
        headers=attacker_bearer)
    assert r.status_code == 404
    assert "Student bbb" not in r.text
    untouched()

# ── The attacker's own student still works ───────────────────────────────────

def test_the_teacher_can_still_act_on_their_OWN_student(attacker, world):
    """A scoping fix that breaks the legitimate path is not a fix.

    Deliberately the last test: if the guards were simply refusing everything,
    every assertion above would pass for the wrong reason and only this one
    would notice.
    """
    own = world["a"]["student_id"]
    before = float(_student(own)["prepaid"])
    r = attacker.post(f"/teacher/students/{own}/payment",
                      data={"amount": "25"}, follow_redirects=False)
    assert r.status_code == 303
    after = float(_student(own)["prepaid"])
    assert after == before + 25, (
        f"the teacher can no longer pay their own student: {before} -> {after}")
