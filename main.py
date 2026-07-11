from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import os, csv, json, secrets, hashlib, time
from datetime import datetime, timedelta

app = FastAPI(title="Music School App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
os.makedirs("/data", exist_ok=True)

# ── Rate limiting ─────────────────────────────────────────────────────────────
_login_attempts: dict = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 600

def _rl_blocked(ip: str) -> bool:
    e = _login_attempts.get(ip)
    return bool(e and e["locked_until"] > time.time())

def _rl_fail(ip: str):
    now = time.time()
    e   = _login_attempts.get(ip, {"count": 0, "locked_until": 0})
    if e["locked_until"] < now: e["count"] += 1
    if e["count"] >= _MAX_ATTEMPTS: e["locked_until"] = now + _LOCKOUT_SECS
    _login_attempts[ip] = e

def _rl_clear(ip: str):
    _login_attempts.pop(ip, None)

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
:root{--primary:#6366f1;--secondary:#8b5cf6;--success:#10b981;--warning:#f59e0b;--danger:#ef4444;--dark:#1e293b;--muted:#64748b;--border:#e2e8f0;--bg:#f1f5f9;--sidebar:#0f172a;--sw:256px;}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--dark);min-height:100vh;font-size:14px;line-height:1.5;}
.layout{display:flex;min-height:100vh;}
.sidebar{width:var(--sw);background:var(--sidebar);position:fixed;top:0;left:0;bottom:0;display:flex;flex-direction:column;z-index:200;overflow-y:auto;}
.sidebar-brand{padding:18px 14px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;align-items:center;gap:12px;}
.brand-icon{width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,var(--primary),var(--secondary));display:flex;align-items:center;justify-content:center;font-size:17px;}
.brand-name{color:#fff;font-size:14px;font-weight:700;}.brand-sub{color:rgba(255,255,255,.3);font-size:10px;margin-top:1px;}
.sidebar-nav{flex:1;padding:10px;}
.nav-link{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:7px;text-decoration:none;color:rgba(255,255,255,.5);font-size:13px;font-weight:500;transition:all .15s;margin-bottom:1px;}
.nav-link:hover{background:rgba(255,255,255,.07);color:rgba(255,255,255,.9);}
.nav-link.active{background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff;}
.nav-icon{font-size:15px;width:17px;text-align:center;}
.sidebar-footer{padding:10px;border-top:1px solid rgba(255,255,255,.06);}
.main{margin-left:var(--sw);flex:1;display:flex;flex-direction:column;}
.topbar{background:#fff;border-bottom:1px solid var(--border);padding:0 26px;height:58px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
.topbar-title{font-size:16px;font-weight:700;}
.page-body{padding:26px;flex:1;}
.card{background:#fff;border-radius:14px;padding:22px;border:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,.04);margin-bottom:18px;}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}
.card-title{font-size:14px;font-weight:700;}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:22px;}
.stat-card{background:#fff;border:1px solid var(--border);border-radius:13px;padding:16px 18px;}
.stat-icon{width:38px;height:38px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:17px;margin-bottom:10px;}
.stat-val{font-size:24px;font-weight:800;}.stat-lbl{font-size:11px;color:var(--muted);font-weight:500;margin-top:2px;text-transform:uppercase;letter-spacing:.4px;}
h1{font-size:22px;font-weight:800;}h2{font-size:16px;font-weight:700;margin-bottom:12px;}h3{font-size:14px;font-weight:700;}
.btn{display:inline-flex;align-items:center;gap:5px;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;cursor:pointer;border:none;outline:none;transition:all .15s;white-space:nowrap;background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff;box-shadow:0 1px 4px rgba(99,102,241,.3);margin:2px;}
.btn:hover{transform:translateY(-1px);}
.btn-success{background:var(--success);}.btn-danger{background:var(--danger);}.btn-warning{background:var(--warning);color:#fff;}
.btn-outline{background:transparent;color:var(--primary);border:1.5px solid var(--border);box-shadow:none;}
.btn-outline:hover{border-color:var(--primary);background:#f5f3ff;transform:none;}
.btn-sm{padding:5px 11px;font-size:12px;border-radius:6px;}
table{width:100%;border-collapse:collapse;}
thead th{background:var(--bg);color:var(--muted);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:9px 13px;text-align:left;border-bottom:1px solid var(--border);}
tbody td{padding:11px 13px;border-bottom:1px solid var(--border);}
tbody tr:last-child td{border-bottom:none;}
tbody tr:hover td{background:#fafaff;}
.form-group{margin-bottom:14px;}
.form-label{display:block;font-size:12px;font-weight:600;margin-bottom:4px;}
input[type=text],input[type=number],input[type=email],input[type=password],select,textarea{width:100%;padding:8px 11px;border:1.5px solid var(--border);border-radius:8px;font-size:13px;color:var(--dark);background:#fff;outline:none;font-family:inherit;}
input:focus,select:focus,textarea:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.1);}
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;}
.badge-success{background:#d1fae5;color:#065f46;}.badge-danger{background:#fee2e2;color:#991b1b;}
.badge-warning{background:#fef3c7;color:#92400e;}.badge-info{background:#e0e7ff;color:#3730a3;}
.badge-muted{background:var(--bg);color:var(--muted);}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px;}
.alert{padding:12px 16px;border-radius:9px;margin-bottom:14px;font-size:13px;font-weight:500;}
.alert-danger{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5;}
.alert-success{background:#d1fae5;color:#065f46;border:1px solid #a7f3d0;}
.login-wrap{min-height:100vh;background:var(--bg);display:flex;align-items:center;justify-content:center;padding:24px;}
.login-card{background:#fff;border-radius:18px;padding:36px;width:100%;max-width:420px;border:1px solid var(--border);box-shadow:0 8px 32px rgba(0,0,0,.08);}
.login-logo{width:52px;height:52px;border-radius:13px;background:linear-gradient(135deg,var(--primary),var(--secondary));display:flex;align-items:center;justify-content:center;font-size:24px;margin:0 auto 18px;}
.menu-btn{display:none;background:none;border:none;font-size:24px;cursor:pointer;padding:4px 8px;}
@media(max-width:768px){.two-col{grid-template-columns:1fr;}.main{margin-left:0!important;}.sidebar{display:none!important;}.menu-btn{display:block!important;}}
.toast-container{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;pointer-events:none;}
.toast{background:#1e293b;color:#fff;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,.18);display:flex;align-items:center;gap:10px;transition:opacity .4s ease;pointer-events:auto;}
.toast.hiding{opacity:0;}
.empty-state{text-align:center;padding:48px 24px;color:var(--muted);}
.empty-state-icon{font-size:48px;margin-bottom:14px;opacity:.6;}
"""

with open("static/style.css", "w") as _f:
    _f.write(CSS)


# ── Data files & helpers ───────────────────────────────────────────────────────
SCHOOLS_FILE  = "/data/schools.csv"
TEACHERS_FILE = "/data/teachers.csv"
STUDENTS_FILE = "/data/students.csv"
LEDGER_FILE   = "/data/ledger.csv"
NOTES_FILE    = "/data/notes.csv"

SCHOOLS_HEADERS  = ["school_id", "name", "owner_email", "owner_name", "password_hash",
                    "plan", "created_at", "active"]
TEACHERS_HEADERS = ["teacher_id", "school_id", "name", "email", "password_hash",
                    "created_at", "active"]
STUDENTS_HEADERS = ["student_id", "school_id", "teacher_id", "name", "rate",
                    "parent_email", "parent_code", "access_code", "prepaid", "created_at"]
LEDGER_HEADERS   = ["id", "school_id", "teacher_id", "student_id", "student_name",
                    "date", "status", "amount", "notes"]
NOTES_HEADERS    = ["id", "school_id", "teacher_id", "student_id", "student_name",
                    "date", "notes", "assignment", "created_at"]


def _init_csv(path, headers):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=headers).writeheader()


_init_csv(SCHOOLS_FILE,  SCHOOLS_HEADERS)
_init_csv(TEACHERS_FILE, TEACHERS_HEADERS)
_init_csv(STUDENTS_FILE, STUDENTS_HEADERS)
_init_csv(LEDGER_FILE,   LEDGER_HEADERS)
_init_csv(NOTES_FILE,    NOTES_HEADERS)


def _read_csv(path, headers) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _write_csv(path, headers, rows: list[dict]):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in headers})


def _append_csv(path, headers, row: dict):
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=headers).writerow(
            {k: row.get(k, "") for k in headers}
        )


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ── School helpers ─────────────────────────────────────────────────────────────
def get_school(school_id: str) -> dict | None:
    return next((s for s in _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
                 if s["school_id"] == school_id), None)

def get_school_by_email(email: str) -> dict | None:
    return next((s for s in _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
                 if s["owner_email"] == email), None)


# ── Teacher helpers ────────────────────────────────────────────────────────────
def get_teachers(school_id: str) -> list[dict]:
    return [t for t in _read_csv(TEACHERS_FILE, TEACHERS_HEADERS)
            if t["school_id"] == school_id and t.get("active", "true") == "true"]

def get_teacher(teacher_id: str) -> dict | None:
    return next((t for t in _read_csv(TEACHERS_FILE, TEACHERS_HEADERS)
                 if t["teacher_id"] == teacher_id), None)

def get_teacher_by_email(email: str) -> dict | None:
    return next((t for t in _read_csv(TEACHERS_FILE, TEACHERS_HEADERS)
                 if t["email"] == email), None)


# ── Student helpers ────────────────────────────────────────────────────────────
def get_students(teacher_id: str) -> list[dict]:
    return [s for s in _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
            if s["teacher_id"] == teacher_id]

def get_all_school_students(school_id: str) -> list[dict]:
    return [s for s in _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
            if s["school_id"] == school_id]

def get_student(student_id: str) -> dict | None:
    return next((s for s in _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
                 if s["student_id"] == student_id), None)


# ── Revenue helpers ────────────────────────────────────────────────────────────
def school_revenue(school_id: str) -> float:
    return sum(float(r.get("amount", 0)) for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
               if r["school_id"] == school_id)

def teacher_revenue(teacher_id: str) -> float:
    return sum(float(r.get("amount", 0)) for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
               if r["teacher_id"] == teacher_id)

def month_revenue(school_id: str, year: int, month: int) -> float:
    prefix = f"{year}-{month:02d}"
    return sum(float(r.get("amount", 0)) for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
               if r["school_id"] == school_id and r.get("date", "").startswith(prefix))


# ── Page builder ───────────────────────────────────────────────────────────────
def _page(title: str, content: str, active: str,
          links: list, logout_url: str, brand: str = "🎵 Music School") -> str:
    nav = "".join(
        f'<a href="{href}" class="nav-link{" active" if k==active else ""}">'
        f'<span class="nav-icon">{icon}</span>{label}</a>'
        for k, href, icon, label in links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Music School</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="layout">
<aside class="sidebar">
  <div class="sidebar-brand">
    <div class="brand-icon">🎵</div>
    <div><div class="brand-name">{brand}</div><div class="brand-sub">Music School Manager</div></div>
  </div>
  <nav class="sidebar-nav">{nav}</nav>
  <div class="sidebar-footer">
    <a href="{logout_url}" class="nav-link"><span class="nav-icon">🚪</span>Logout</a>
  </div>
</aside>
<div class="main">
  <header class="topbar">
    <span class="topbar-title">{title}</span>
  </header>
  <div class="page-body">{content}</div>
</div>
</div>
<div class="toast-container" id="tc"></div>
<script>
function showToast(msg,type){{
  var t=document.createElement('div');
  t.className='toast';t.textContent=msg;
  document.getElementById('tc').appendChild(t);
  setTimeout(function(){{t.classList.add('hiding');}},2800);
  setTimeout(function(){{t.remove();}},3200);
}}
(function(){{
  var p=new URLSearchParams(window.location.search);
  if(p.get('toast')) showToast(decodeURIComponent(p.get('toast').replace(/\+/g,' ')));
}})();
</script>
</body></html>"""


def school_page(title, content, active):
    return _page(title, content, active, [
        ("dashboard", "/school/dashboard", "🏠", "Dashboard"),
        ("teachers",  "/school/teachers",  "👩‍🏫", "Teachers"),
        ("students",  "/school/students",  "👥", "All Students"),
        ("analytics", "/school/analytics", "📊", "Analytics"),
        ("settings",  "/school/settings",  "⚙️",  "Settings"),
    ], "/school/logout")


def teacher_page(title, content, active):
    return _page(title, content, active, [
        ("dashboard", "/teacher/dashboard", "🏠", "Dashboard"),
        ("students",  "/teacher/students",  "👥", "My Students"),
        ("schedule",  "/teacher/schedule",  "📅", "Schedule"),
        ("payments",  "/teacher/payments",  "💳", "Payments"),
        ("notes",     "/teacher/notes",     "📝", "Notes"),
        ("analytics", "/teacher/analytics", "📊", "Analytics"),
    ], "/teacher/logout")


def parent_page(title, content, active):
    return _page(title, content, active, [
        ("dashboard", "/parent/dashboard", "🏠", "Dashboard"),
        ("notes",     "/parent/notes",     "📝", "Lesson Notes"),
        ("payments",  "/parent/payments",  "💳", "Payments"),
    ], "/parent/logout")


# ── Login pages ────────────────────────────────────────────────────────────────
def _login_html(title: str, action: str, fields: str, error: str = "",
                signup_link: str = "", extra: str = "") -> str:
    err = f'<div class="alert alert-danger">{error}</div>' if error else ""
    sig = f'<p style="text-align:center;margin-top:14px;font-size:13px;">{signup_link}</p>' if signup_link else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo">🎵</div>
    <h1 style="text-align:center;margin-bottom:4px;font-size:20px;">{title}</h1>
    <p style="text-align:center;color:var(--muted);font-size:13px;margin-bottom:20px;">Music School Manager</p>
    {err}
    <form action="{action}" method="post">
      {fields}
      <button type="submit" class="btn" style="width:100%;justify-content:center;padding:10px;margin-top:4px;">Sign In</button>
    </form>
    {sig}{extra}
  </div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
#  ROOT
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def root():
    return RedirectResponse("/school/login")


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHOOL ADMIN — signup / login / dashboard
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/school/signup", response_class=HTMLResponse)
def school_signup_page(error: str = ""):
    err = f'<div class="alert alert-danger">{error}</div>' if error else ""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Create School — Music School</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo">🎵</div>
    <h1 style="text-align:center;margin-bottom:4px;font-size:20px;">Create Your School</h1>
    <p style="text-align:center;color:var(--muted);font-size:13px;margin-bottom:20px;">Set up your music school account</p>
    {err}
    <form action="/school/signup" method="post">
      <div class="form-group">
        <label class="form-label">School Name</label>
        <input type="text" name="school_name" placeholder="Harmony Music Academy" required autofocus>
      </div>
      <div class="form-group">
        <label class="form-label">Your Name</label>
        <input type="text" name="owner_name" placeholder="Jane Smith" required>
      </div>
      <div class="form-group">
        <label class="form-label">Email</label>
        <input type="email" name="email" placeholder="you@example.com" required>
      </div>
      <div class="form-group">
        <label class="form-label">Password</label>
        <input type="password" name="password" placeholder="••••••••" required minlength="6">
      </div>
      <button type="submit" class="btn" style="width:100%;justify-content:center;padding:10px;margin-top:4px;">
        Create School</button>
    </form>
    <p style="text-align:center;margin-top:14px;font-size:13px;color:var(--muted);">
      Already have an account? <a href="/school/login" style="color:var(--primary);font-weight:600;">Sign in</a>
    </p>
  </div>
</div>
</body></html>""")


@app.post("/school/signup")
async def school_signup_post(
    school_name: str = Form(...),
    owner_name:  str = Form(...),
    email:       str = Form(...),
    password:    str = Form(...),
):
    email = email.strip().lower()
    if get_school_by_email(email):
        return RedirectResponse(f"/school/signup?error=Email+already+registered", status_code=303)
    school_id = secrets.token_hex(8)
    _append_csv(SCHOOLS_FILE, SCHOOLS_HEADERS, {
        "school_id":    school_id,
        "name":         school_name.strip(),
        "owner_email":  email,
        "owner_name":   owner_name.strip(),
        "password_hash": _hash(password),
        "plan":         "starter",
        "created_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active":       "true",
    })
    resp = RedirectResponse("/school/dashboard?toast=Welcome!+Your+school+is+ready.", status_code=303)
    resp.set_cookie("school_id", school_id, httponly=True, max_age=86400 * 30)
    return resp


@app.get("/school/login", response_class=HTMLResponse)
def school_login_page(error: str = ""):
    fields = """
      <div class="form-group"><label class="form-label">Email</label>
        <input type="email" name="email" placeholder="you@example.com" required autofocus></div>
      <div class="form-group"><label class="form-label">Password</label>
        <input type="password" name="password" placeholder="••••••••" required></div>"""
    return HTMLResponse(_login_html(
        "School Admin Login", "/school/login", fields, error,
        signup_link='No account? <a href="/school/signup" style="color:var(--primary);font-weight:600;">Create your school</a>',
        extra='<p style="text-align:center;margin-top:10px;font-size:13px;color:var(--muted);">Teacher? <a href="/teacher/login" style="color:var(--primary);font-weight:600;">Teacher login →</a></p>',
    ))


@app.post("/school/login")
async def school_login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    ip = request.client.host
    if _rl_blocked(ip):
        return RedirectResponse("/school/login?error=Too+many+attempts.+Try+again+in+10+minutes.", status_code=303)
    school = get_school_by_email(email.strip().lower())
    if school and school["password_hash"] == _hash(password):
        _rl_clear(ip)
        resp = RedirectResponse("/school/dashboard", status_code=303)
        resp.set_cookie("school_id", school["school_id"], httponly=True, max_age=86400 * 30)
        return resp
    _rl_fail(ip)
    return RedirectResponse("/school/login?error=Invalid+email+or+password", status_code=303)


@app.get("/school/logout")
def school_logout():
    resp = RedirectResponse("/school/login", status_code=303)
    resp.delete_cookie("school_id")
    return resp


def _require_school(request: Request) -> dict | None:
    sid = request.cookies.get("school_id", "")
    return get_school(sid) if sid else None


@app.get("/school/dashboard", response_class=HTMLResponse)
def school_dashboard(request: Request):
    school = _require_school(request)
    if not school:
        return RedirectResponse("/school/login", status_code=303)

    teachers = get_teachers(school["school_id"])
    students = get_all_school_students(school["school_id"])
    now      = datetime.now()
    this_month = month_revenue(school["school_id"], now.year, now.month)
    total_rev  = school_revenue(school["school_id"])

    teacher_rows = "".join(
        f'<tr><td><strong>{t["name"]}</strong></td>'
        f'<td style="color:var(--muted);">{t["email"]}</td>'
        f'<td>{len([s for s in students if s["teacher_id"]==t["teacher_id"]])}</td>'
        f'<td style="color:var(--success);font-weight:600;">${teacher_revenue(t["teacher_id"]):.2f}</td>'
        f'<td><a href="/school/teachers/{t["teacher_id"]}" class="btn btn-outline btn-sm">View</a></td></tr>'
        for t in teachers
    ) or '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px;">No teachers yet — <a href="/school/teachers/invite">invite one</a></td></tr>'

    content = f"""
<h1>Dashboard</h1>
<p style="color:var(--muted);margin-bottom:20px;">{school['name']}</p>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">👩‍🏫</div><div class="stat-val">{len(teachers)}</div><div class="stat-lbl">Teachers</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#dbeafe;">👥</div><div class="stat-val">{len(students)}</div><div class="stat-lbl">Students</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div><div class="stat-val">${this_month:.2f}</div><div class="stat-lbl">This Month</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fef3c7;">📈</div><div class="stat-val">${total_rev:.2f}</div><div class="stat-lbl">All-Time Revenue</div></div>
</div>
<div class="card">
  <div class="card-header">
    <span class="card-title">👩‍🏫 Teachers</span>
    <a href="/school/teachers/invite" class="btn btn-sm">+ Invite Teacher</a>
  </div>
  <table>
    <thead><tr><th>Name</th><th>Email</th><th>Students</th><th>Revenue</th><th></th></tr></thead>
    <tbody>{teacher_rows}</tbody>
  </table>
</div>"""
    return HTMLResponse(school_page("Dashboard", content, "dashboard"))


# ── School: Teachers ───────────────────────────────────────────────────────────
@app.get("/school/teachers", response_class=HTMLResponse)
def school_teachers(request: Request):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)

    teachers = get_teachers(school["school_id"])
    students = get_all_school_students(school["school_id"])

    rows = "".join(
        f'<tr><td><strong>{t["name"]}</strong></td>'
        f'<td>{t["email"]}</td>'
        f'<td>{len([s for s in students if s["teacher_id"]==t["teacher_id"]])}</td>'
        f'<td style="color:var(--success);font-weight:600;">${teacher_revenue(t["teacher_id"]):.2f}</td>'
        f'<td>'
        f'<a href="/school/teachers/{t["teacher_id"]}" class="btn btn-outline btn-sm">View</a> '
        f'<a href="/school/teachers/{t["teacher_id"]}/remove" class="btn btn-sm" style="background:var(--danger);" onclick="return confirm(\'Remove this teacher?\')">Remove</a>'
        f'</td></tr>'
        for t in teachers
    ) or '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px;">No teachers yet.</td></tr>'

    content = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <h1>Teachers</h1>
  <a href="/school/teachers/invite" class="btn">+ Invite Teacher</a>
</div>
<div class="card">
  <table>
    <thead><tr><th>Name</th><th>Email</th><th>Students</th><th>Revenue</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return HTMLResponse(school_page("Teachers", content, "teachers"))


@app.get("/school/teachers/invite", response_class=HTMLResponse)
def school_invite_page(request: Request, error: str = ""):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    err = f'<div class="alert alert-danger">{error}</div>' if error else ""
    content = f"""
<div style="max-width:480px;">
  <h1 style="margin-bottom:20px;">Invite a Teacher</h1>
  {err}
  <div class="card">
    <form action="/school/teachers/invite" method="post">
      <div class="form-group"><label class="form-label">Teacher's Name</label>
        <input type="text" name="name" placeholder="Jane Smith" required autofocus></div>
      <div class="form-group"><label class="form-label">Email</label>
        <input type="email" name="email" placeholder="teacher@example.com" required></div>
      <div class="form-group"><label class="form-label">Temporary Password</label>
        <input type="text" name="password" placeholder="They can change it after first login" required></div>
      <button type="submit" class="btn">Send Invite</button>
      <a href="/school/teachers" class="btn btn-outline">Cancel</a>
    </form>
  </div>
</div>"""
    return HTMLResponse(school_page("Invite Teacher", content, "teachers"))


@app.post("/school/teachers/invite")
async def school_invite_post(request: Request,
    name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    email = email.strip().lower()
    if get_teacher_by_email(email):
        return RedirectResponse(f"/school/teachers/invite?error=Email+already+registered", status_code=303)
    teacher_id = secrets.token_hex(8)
    _append_csv(TEACHERS_FILE, TEACHERS_HEADERS, {
        "teacher_id":    teacher_id,
        "school_id":     school["school_id"],
        "name":          name.strip(),
        "email":         email,
        "password_hash": _hash(password),
        "created_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active":        "true",
    })
    return RedirectResponse(f"/school/teachers?toast={name.replace(' ','+')}+added", status_code=303)


@app.get("/school/teachers/{teacher_id}", response_class=HTMLResponse)
def school_teacher_detail(teacher_id: str, request: Request):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    teacher  = get_teacher(teacher_id)
    if not teacher or teacher["school_id"] != school["school_id"]:
        return RedirectResponse("/school/teachers", status_code=303)
    students = get_students(teacher_id)
    ledger   = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS) if r["teacher_id"] == teacher_id]
    total    = sum(float(r.get("amount", 0)) for r in ledger)

    stu_rows = "".join(
        f'<tr><td><strong>{s["name"]}</strong></td>'
        f'<td style="color:var(--muted);">{s.get("parent_email","—")}</td>'
        f'<td>${float(s.get("rate",50)):.2f}</td>'
        f'<td style="color:{"var(--success)" if float(s.get("prepaid",0))>0 else "var(--danger)"};font-weight:600;">${float(s.get("prepaid",0)):.2f}</td></tr>'
        for s in students
    ) or '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:16px;">No students yet</td></tr>'

    content = f"""
<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
  <a href="/school/teachers" style="color:var(--muted);text-decoration:none;">← Teachers</a>
  <h1>{teacher['name']}</h1>
</div>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">👥</div><div class="stat-val">{len(students)}</div><div class="stat-lbl">Students</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div><div class="stat-val">${total:.2f}</div><div class="stat-lbl">Total Revenue</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#dbeafe;">📧</div><div class="stat-val" style="font-size:13px;margin-top:4px;">{teacher['email']}</div><div class="stat-lbl">Email</div></div>
</div>
<div class="card">
  <div class="card-title" style="margin-bottom:14px;">Students</div>
  <table><thead><tr><th>Name</th><th>Parent Email</th><th>Rate</th><th>Balance</th></tr></thead>
  <tbody>{stu_rows}</tbody></table>
</div>"""
    return HTMLResponse(school_page(teacher["name"], content, "teachers"))


@app.get("/school/teachers/{teacher_id}/remove")
def school_remove_teacher(teacher_id: str, request: Request):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    rows = _read_csv(TEACHERS_FILE, TEACHERS_HEADERS)
    for r in rows:
        if r["teacher_id"] == teacher_id and r["school_id"] == school["school_id"]:
            r["active"] = "false"
    _write_csv(TEACHERS_FILE, TEACHERS_HEADERS, rows)
    return RedirectResponse("/school/teachers?toast=Teacher+removed", status_code=303)


# ── School: All Students ───────────────────────────────────────────────────────
@app.get("/school/students", response_class=HTMLResponse)
def school_students(request: Request):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    students = get_all_school_students(school["school_id"])
    teachers = {t["teacher_id"]: t["name"] for t in get_teachers(school["school_id"])}

    rows = "".join(
        f'<tr><td><strong>{s["name"]}</strong></td>'
        f'<td>{teachers.get(s["teacher_id"],"—")}</td>'
        f'<td style="color:var(--muted);">{s.get("parent_email","—")}</td>'
        f'<td>${float(s.get("rate",50)):.2f}</td>'
        f'<td style="color:{"var(--success)" if float(s.get("prepaid",0))>0 else "var(--danger)"};font-weight:600;">${float(s.get("prepaid",0)):.2f}</td></tr>'
        for s in students
    ) or '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px;">No students enrolled yet.</td></tr>'

    content = f"""
<h1 style="margin-bottom:20px;">All Students</h1>
<div class="card">
  <table>
    <thead><tr><th>Student</th><th>Teacher</th><th>Parent Email</th><th>Rate</th><th>Balance</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return HTMLResponse(school_page("Students", content, "students"))


# ── School: Analytics ──────────────────────────────────────────────────────────
@app.get("/school/analytics", response_class=HTMLResponse)
def school_analytics(request: Request):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    sid      = school["school_id"]
    teachers = get_teachers(sid)
    students = get_all_school_students(sid)
    ledger   = _read_csv(LEDGER_FILE, LEDGER_HEADERS)
    school_ledger = [r for r in ledger if r["school_id"] == sid]

    now = datetime.now()
    monthly = []
    for i in range(5, -1, -1):
        m = now.month - i; y = now.year
        while m <= 0: m += 12; y -= 1
        rev = sum(float(r.get("amount",0)) for r in school_ledger
                  if r.get("date","").startswith(f"{y}-{m:02d}"))
        monthly.append({"label": datetime(y,m,1).strftime("%b %Y"), "rev": round(rev,2)})

    teacher_stats = []
    for t in teachers:
        t_ledger = [r for r in school_ledger if r["teacher_id"] == t["teacher_id"]]
        teacher_stats.append({
            "name": t["name"],
            "students": len([s for s in students if s["teacher_id"]==t["teacher_id"]]),
            "revenue": round(sum(float(r.get("amount",0)) for r in t_ledger), 2),
            "lessons": len(t_ledger),
        })
    teacher_stats.sort(key=lambda x: x["revenue"], reverse=True)

    t_rows = "".join(
        f'<tr><td><strong>{t["name"]}</strong></td><td>{t["students"]}</td>'
        f'<td>{t["lessons"]}</td>'
        f'<td style="color:var(--success);font-weight:700;">${t["revenue"]:.2f}</td></tr>'
        for t in teacher_stats
    ) or '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:20px;">No data yet</td></tr>'

    chart_json = json.dumps({
        "labels": [m["label"] for m in monthly],
        "values": [m["rev"]   for m in monthly],
    })

    content = f"""
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<h1 style="margin-bottom:20px;">Analytics</h1>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div><div class="stat-val">${monthly[-1]['rev']:.2f}</div><div class="stat-lbl">This Month</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">📈</div><div class="stat-val">${sum(m['rev'] for m in monthly)/6:.2f}</div><div class="stat-lbl">Monthly Average</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#dbeafe;">👩‍🏫</div><div class="stat-val">{len(teachers)}</div><div class="stat-lbl">Teachers</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fef3c7;">👥</div><div class="stat-val">{len(students)}</div><div class="stat-lbl">Students</div></div>
</div>
<div class="two-col">
  <div class="card"><h3 style="margin-bottom:14px;">📊 Monthly Revenue</h3><canvas id="chart"></canvas></div>
  <div class="card"><h3 style="margin-bottom:14px;">👩‍🏫 Revenue by Teacher</h3>
    <table><thead><tr><th>Teacher</th><th>Students</th><th>Lessons</th><th>Revenue</th></tr></thead>
    <tbody>{t_rows}</tbody></table>
  </div>
</div>
<script>
const D={chart_json};
new Chart(document.getElementById('chart'),{{type:'bar',data:{{labels:D.labels,datasets:[{{label:'Revenue',data:D.values,backgroundColor:'rgba(99,102,241,.75)',borderColor:'#6366f1',borderWidth:2,borderRadius:7,borderSkipped:false}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{y:{{beginAtZero:true,ticks:{{callback:v=>'$'+v}}}}}}}}}});
</script>"""
    return HTMLResponse(school_page("Analytics", content, "analytics"))


# ── School: Settings ───────────────────────────────────────────────────────────
@app.get("/school/settings", response_class=HTMLResponse)
def school_settings(request: Request, toast: str = ""):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    t = f'<div class="alert alert-success">{toast}</div>' if toast else ""
    content = f"""
<div style="max-width:480px;">
  <h1 style="margin-bottom:20px;">Settings</h1>
  {t}
  <div class="card">
    <h3 style="margin-bottom:16px;">School Info</h3>
    <form action="/school/settings" method="post">
      <div class="form-group"><label class="form-label">School Name</label>
        <input type="text" name="school_name" value="{school['name']}" required></div>
      <div class="form-group"><label class="form-label">Owner Name</label>
        <input type="text" name="owner_name" value="{school['owner_name']}" required></div>
      <button type="submit" class="btn">Save</button>
    </form>
  </div>
  <div class="card">
    <h3 style="margin-bottom:16px;">Change Password</h3>
    <form action="/school/settings/password" method="post">
      <div class="form-group"><label class="form-label">Current Password</label>
        <input type="password" name="current_password" required></div>
      <div class="form-group"><label class="form-label">New Password</label>
        <input type="password" name="new_password" required minlength="6"></div>
      <button type="submit" class="btn btn-outline">Update Password</button>
    </form>
  </div>
</div>"""
    return HTMLResponse(school_page("Settings", content, "settings"))


@app.post("/school/settings")
async def school_settings_post(request: Request,
    school_name: str = Form(...), owner_name: str = Form(...)):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    rows = _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
    for r in rows:
        if r["school_id"] == school["school_id"]:
            r["name"] = school_name.strip()
            r["owner_name"] = owner_name.strip()
    _write_csv(SCHOOLS_FILE, SCHOOLS_HEADERS, rows)
    return RedirectResponse("/school/settings?toast=Saved", status_code=303)


@app.post("/school/settings/password")
async def school_password_post(request: Request,
    current_password: str = Form(...), new_password: str = Form(...)):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    if school["password_hash"] != _hash(current_password):
        return RedirectResponse("/school/settings?toast=Incorrect+current+password", status_code=303)
    rows = _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
    for r in rows:
        if r["school_id"] == school["school_id"]:
            r["password_hash"] = _hash(new_password)
    _write_csv(SCHOOLS_FILE, SCHOOLS_HEADERS, rows)
    return RedirectResponse("/school/settings?toast=Password+updated", status_code=303)


# ═══════════════════════════════════════════════════════════════════════════════
#  TEACHER PORTAL
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/teacher/login", response_class=HTMLResponse)
def teacher_login_page(error: str = ""):
    fields = """
      <div class="form-group"><label class="form-label">Email</label>
        <input type="email" name="email" placeholder="you@example.com" required autofocus></div>
      <div class="form-group"><label class="form-label">Password</label>
        <input type="password" name="password" placeholder="••••••••" required></div>"""
    return HTMLResponse(_login_html(
        "Teacher Login", "/teacher/login", fields, error,
        extra='<p style="text-align:center;margin-top:10px;font-size:13px;color:var(--muted);">School admin? <a href="/school/login" style="color:var(--primary);font-weight:600;">Admin login →</a></p>',
    ))


@app.post("/teacher/login")
async def teacher_login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    ip = request.client.host
    if _rl_blocked(ip):
        return RedirectResponse("/teacher/login?error=Too+many+attempts.+Try+again+in+10+minutes.", status_code=303)
    teacher = get_teacher_by_email(email.strip().lower())
    if teacher and teacher["password_hash"] == _hash(password) and teacher.get("active","true") == "true":
        _rl_clear(ip)
        resp = RedirectResponse("/teacher/dashboard", status_code=303)
        resp.set_cookie("teacher_id", teacher["teacher_id"], httponly=True, max_age=86400 * 30)
        return resp
    _rl_fail(ip)
    return RedirectResponse("/teacher/login?error=Invalid+email+or+password", status_code=303)


@app.get("/teacher/logout")
def teacher_logout():
    resp = RedirectResponse("/teacher/login", status_code=303)
    resp.delete_cookie("teacher_id")
    return resp


def _require_teacher(request: Request) -> dict | None:
    tid = request.cookies.get("teacher_id", "")
    return get_teacher(tid) if tid else None


@app.get("/teacher/dashboard", response_class=HTMLResponse)
def teacher_dashboard(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    students = get_students(teacher["teacher_id"])
    now      = datetime.now()
    this_month = sum(
        float(r.get("amount",0)) for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
        if r["teacher_id"] == teacher["teacher_id"]
        and r.get("date","").startswith(f"{now.year}-{now.month:02d}")
    )
    total_rev = teacher_revenue(teacher["teacher_id"])

    bal_rows = "".join(
        f'<div style="display:flex;align-items:center;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--border);">'
        f'<span style="font-weight:600;">{"🟢" if float(s.get("prepaid",0))>0 else "🔴"} {s["name"]}</span>'
        f'<span style="color:{"var(--success)" if float(s.get("prepaid",0))>0 else "var(--danger)"};font-weight:700;">${float(s.get("prepaid",0)):.2f}</span>'
        f'</div>'
        for s in students
    ) or '<p style="color:var(--muted);font-size:13px;">No students yet.</p>'

    content = f"""
<h1>Dashboard</h1>
<p style="color:var(--muted);margin-bottom:20px;">Welcome back, {teacher['name']}!</p>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">👥</div><div class="stat-val">{len(students)}</div><div class="stat-lbl">Students</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div><div class="stat-val">${this_month:.2f}</div><div class="stat-lbl">This Month</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fef3c7;">📈</div><div class="stat-val">${total_rev:.2f}</div><div class="stat-lbl">All-Time</div></div>
</div>
<div class="two-col">
  <div class="card">
    <div class="card-header"><span class="card-title">Quick Actions</span></div>
    <a href="/teacher/students/add" class="btn" style="display:block;margin-bottom:8px;">👤 Add Student</a>
    <a href="/teacher/payments/record" class="btn btn-success" style="display:block;margin-bottom:8px;">💳 Record Payment</a>
    <a href="/teacher/notes/add" class="btn btn-outline" style="display:block;">📝 Add Lesson Note</a>
  </div>
  <div class="card">
    <div class="card-header"><span class="card-title">💰 Student Balances</span></div>
    {bal_rows}
  </div>
</div>"""
    return HTMLResponse(teacher_page("Dashboard", content, "dashboard"))


# ── Teacher: Students ──────────────────────────────────────────────────────────
@app.get("/teacher/students", response_class=HTMLResponse)
def teacher_students(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    students = get_students(teacher["teacher_id"])

    rows = "".join(
        f'<tr><td><strong>{s["name"]}</strong></td>'
        f'<td style="color:var(--muted);">{s.get("parent_email","—")}</td>'
        f'<td>${float(s.get("rate",50)):.2f}</td>'
        f'<td style="color:{"var(--success)" if float(s.get("prepaid",0))>0 else "var(--danger)"};font-weight:600;">${float(s.get("prepaid",0)):.2f}</td>'
        f'<td><a href="/teacher/students/{s["student_id"]}" class="btn btn-outline btn-sm">View</a></td></tr>'
        for s in students
    ) or '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px;">No students yet.</td></tr>'

    content = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <h1>My Students</h1>
  <a href="/teacher/students/add" class="btn">+ Add Student</a>
</div>
<div class="card">
  <table>
    <thead><tr><th>Name</th><th>Parent Email</th><th>Rate</th><th>Balance</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return HTMLResponse(teacher_page("Students", content, "students"))


@app.get("/teacher/students/add", response_class=HTMLResponse)
def teacher_add_student_page(request: Request, error: str = ""):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    err = f'<div class="alert alert-danger">{error}</div>' if error else ""
    content = f"""
<div style="max-width:480px;">
  <h1 style="margin-bottom:20px;">Add Student</h1>
  {err}
  <div class="card">
    <form action="/teacher/students/add" method="post">
      <div class="form-group"><label class="form-label">Student Name</label>
        <input type="text" name="name" required autofocus></div>
      <div class="form-group"><label class="form-label">Parent Email (optional)</label>
        <input type="email" name="parent_email"></div>
      <div class="form-group"><label class="form-label">Lesson Rate ($/lesson)</label>
        <input type="number" name="rate" value="50" step="0.01" min="0" required></div>
      <div class="form-group"><label class="form-label">Starting Prepaid Balance</label>
        <input type="number" name="prepaid" value="0" step="0.01" min="0"></div>
      <div class="form-group"><label class="form-label">Parent Access Code (optional)</label>
        <input type="text" name="parent_code" placeholder="e.g. smith2024"></div>
      <button type="submit" class="btn">Add Student</button>
      <a href="/teacher/students" class="btn btn-outline">Cancel</a>
    </form>
  </div>
</div>"""
    return HTMLResponse(teacher_page("Add Student", content, "students"))


@app.post("/teacher/students/add")
async def teacher_add_student_post(request: Request,
    name: str = Form(...), parent_email: str = Form(""),
    rate: float = Form(50), prepaid: float = Form(0),
    parent_code: str = Form("")):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student_id = secrets.token_hex(8)
    _append_csv(STUDENTS_FILE, STUDENTS_HEADERS, {
        "student_id":   student_id,
        "school_id":    teacher["school_id"],
        "teacher_id":   teacher["teacher_id"],
        "name":         name.strip(),
        "rate":         f"{rate:.2f}",
        "parent_email": parent_email.strip().lower(),
        "parent_code":  parent_code.strip(),
        "access_code":  "",
        "prepaid":      f"{prepaid:.2f}",
        "created_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return RedirectResponse(f"/teacher/students?toast={name.replace(' ','+')}+added", status_code=303)


@app.get("/teacher/students/{student_id}", response_class=HTMLResponse)
def teacher_student_detail(student_id: str, request: Request, toast: str = ""):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    if not student or student["teacher_id"] != teacher["teacher_id"]:
        return RedirectResponse("/teacher/students", status_code=303)

    notes   = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS) if r["student_id"] == student_id]
    notes.sort(key=lambda r: r.get("date",""), reverse=True)
    ledger  = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS) if r["student_id"] == student_id]
    total_charged = sum(float(r.get("amount",0)) for r in ledger)

    notes_html = "".join(
        f'<div style="padding:12px 0;border-bottom:1px solid var(--border);">'
        f'<div style="font-size:11px;color:var(--muted);">{n.get("date","")}</div>'
        f'<div style="font-size:13px;margin-top:4px;">{n.get("notes","")}</div>'
        + (f'<div style="font-size:12px;color:var(--success);margin-top:4px;"><strong>Assignment:</strong> {n["assignment"]}</div>' if n.get("assignment","").strip() else "")
        + '</div>'
        for n in notes[:5]
    ) or '<p style="color:var(--muted);font-size:13px;">No notes yet.</p>'

    t_html = f'<div class="alert alert-success">{toast}</div>' if toast else ""
    content = f"""
{t_html}
<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
  <a href="/teacher/students" style="color:var(--muted);text-decoration:none;">← Students</a>
  <h1>{student['name']}</h1>
</div>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div>
    <div class="stat-val" style="color:{"var(--success)" if float(student.get("prepaid",0))>0 else "var(--danger)"};">${float(student.get("prepaid",0)):.2f}</div>
    <div class="stat-lbl">Prepaid Balance</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fef3c7;">📋</div>
    <div class="stat-val">${total_charged:.2f}</div><div class="stat-lbl">Total Charged</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">💵</div>
    <div class="stat-val">${float(student.get("rate",50)):.2f}</div><div class="stat-lbl">Rate / Lesson</div></div>
</div>
<div class="two-col">
  <div class="card">
    <div class="card-header"><span class="card-title">📝 Recent Notes</span>
      <a href="/teacher/notes/add?student_id={student_id}" class="btn btn-sm">+ Add Note</a></div>
    {notes_html}
  </div>
  <div class="card">
    <div class="card-title" style="margin-bottom:14px;">Actions</div>
    <form action="/teacher/students/{student_id}/payment" method="post" style="display:flex;gap:8px;margin-bottom:12px;">
      <input type="number" name="amount" placeholder="Amount" step="0.01" min="0" style="flex:1;">
      <button type="submit" class="btn btn-success btn-sm">+ Payment</button>
    </form>
    <form action="/teacher/students/{student_id}/charge" method="post" style="display:flex;gap:8px;">
      <input type="number" name="amount" placeholder="Charge" step="0.01" min="0" style="flex:1;" value="{float(student.get("rate",50)):.2f}">
      <button type="submit" class="btn btn-sm" style="background:var(--danger);">- Charge</button>
    </form>
  </div>
</div>"""
    return HTMLResponse(teacher_page(student["name"], content, "students"))


@app.post("/teacher/students/{student_id}/payment")
async def teacher_record_payment(student_id: str, request: Request, amount: float = Form(...)):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    for r in rows:
        if r["student_id"] == student_id:
            r["prepaid"] = f"{float(r.get('prepaid',0)) + amount:.2f}"
    _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    _append_csv(LEDGER_FILE, LEDGER_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": get_student(student_id).get("name",""),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "Payment", "amount": f"{amount:.2f}", "notes": "",
    })
    return RedirectResponse(f"/teacher/students/{student_id}?toast=Payment+recorded", status_code=303)


@app.post("/teacher/students/{student_id}/charge")
async def teacher_charge_student(student_id: str, request: Request, amount: float = Form(...)):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    for r in rows:
        if r["student_id"] == student_id:
            r["prepaid"] = f"{float(r.get('prepaid',0)) - amount:.2f}"
    _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    _append_csv(LEDGER_FILE, LEDGER_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": student.get("name","") if student else "",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "Lesson Charged", "amount": f"-{amount:.2f}", "notes": "",
    })
    return RedirectResponse(f"/teacher/students/{student_id}?toast=Lesson+charged", status_code=303)


# ── Teacher: Notes ─────────────────────────────────────────────────────────────
@app.get("/teacher/notes", response_class=HTMLResponse)
def teacher_notes(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    notes = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS) if r["teacher_id"] == teacher["teacher_id"]]
    notes.sort(key=lambda r: r.get("date",""), reverse=True)

    rows = "".join(
        f'<tr><td>{n.get("date","")}</td><td><strong>{n.get("student_name","")}</strong></td>'
        f'<td style="color:var(--muted);max-width:300px;">{n.get("notes","")[:80]}{"…" if len(n.get("notes",""))>80 else ""}</td>'
        f'<td>{n.get("assignment","")[:50]}</td></tr>'
        for n in notes[:50]
    ) or '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px;">No notes yet.</td></tr>'

    content = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <h1>Lesson Notes</h1>
  <a href="/teacher/notes/add" class="btn">+ Add Note</a>
</div>
<div class="card">
  <table>
    <thead><tr><th>Date</th><th>Student</th><th>Notes</th><th>Assignment</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return HTMLResponse(teacher_page("Notes", content, "notes"))


@app.get("/teacher/notes/add", response_class=HTMLResponse)
def teacher_add_note_page(request: Request, student_id: str = ""):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    students = get_students(teacher["teacher_id"])
    opts = "".join(
        f'<option value="{s["student_id"]}" {"selected" if s["student_id"]==student_id else ""}>{s["name"]}</option>'
        for s in students
    )
    content = f"""
<div style="max-width:560px;">
  <h1 style="margin-bottom:20px;">Add Lesson Note</h1>
  <div class="card">
    <form action="/teacher/notes/add" method="post">
      <div class="form-group"><label class="form-label">Student</label>
        <select name="student_id" required><option value="">— Select student —</option>{opts}</select></div>
      <div class="form-group"><label class="form-label">Date</label>
        <input type="date" name="date" value="{datetime.now().strftime('%Y-%m-%d')}" required></div>
      <div class="form-group"><label class="form-label">Notes</label>
        <textarea name="notes" rows="4" placeholder="What did you work on today?"></textarea></div>
      <div class="form-group"><label class="form-label">Assignment</label>
        <input type="text" name="assignment" placeholder="Practice scales for 10 minutes daily"></div>
      <button type="submit" class="btn">Save Note</button>
      <a href="/teacher/notes" class="btn btn-outline">Cancel</a>
    </form>
  </div>
</div>"""
    return HTMLResponse(teacher_page("Add Note", content, "notes"))


@app.post("/teacher/notes/add")
async def teacher_add_note_post(request: Request,
    student_id: str = Form(...), date: str = Form(...),
    notes: str = Form(""), assignment: str = Form("")):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    _append_csv(NOTES_FILE, NOTES_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": student.get("name","") if student else "",
        "date": date, "notes": notes.strip(), "assignment": assignment.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return RedirectResponse("/teacher/notes?toast=Note+saved", status_code=303)


# ── Teacher: Payments ──────────────────────────────────────────────────────────
@app.get("/teacher/payments", response_class=HTMLResponse)
def teacher_payments(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
              if r["teacher_id"] == teacher["teacher_id"]]
    ledger.sort(key=lambda r: r.get("date",""), reverse=True)

    rows = "".join(
        f'<tr><td>{r.get("date","")}</td><td><strong>{r.get("student_name","")}</strong></td>'
        f'<td><span class="badge {"badge-success" if r.get("status")=="Payment" else "badge-info"}">{r.get("status","")}</span></td>'
        f'<td style="font-weight:600;color:{"var(--success)" if float(r.get("amount",0))>0 else "var(--danger)"};">${float(r.get("amount",0)):.2f}</td></tr>'
        for r in ledger[:100]
    ) or '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px;">No transactions yet.</td></tr>'

    content = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <h1>Payments</h1>
  <a href="/teacher/payments/record" class="btn">+ Record Payment</a>
</div>
<div class="card">
  <table>
    <thead><tr><th>Date</th><th>Student</th><th>Type</th><th>Amount</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return HTMLResponse(teacher_page("Payments", content, "payments"))


@app.get("/teacher/payments/record", response_class=HTMLResponse)
def teacher_record_payment_page(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    students = get_students(teacher["teacher_id"])
    opts = "".join(f'<option value="{s["student_id"]}">{s["name"]}</option>' for s in students)
    content = f"""
<div style="max-width:420px;">
  <h1 style="margin-bottom:20px;">Record Payment</h1>
  <div class="card">
    <form action="/teacher/payments/record" method="post">
      <div class="form-group"><label class="form-label">Student</label>
        <select name="student_id" required><option value="">— Select —</option>{opts}</select></div>
      <div class="form-group"><label class="form-label">Amount ($)</label>
        <input type="number" name="amount" step="0.01" min="0" required></div>
      <div class="form-group"><label class="form-label">Date</label>
        <input type="date" name="date" value="{datetime.now().strftime('%Y-%m-%d')}" required></div>
      <div class="form-group"><label class="form-label">Notes (optional)</label>
        <input type="text" name="notes" placeholder="e.g. Venmo, cash"></div>
      <button type="submit" class="btn btn-success">Save Payment</button>
      <a href="/teacher/payments" class="btn btn-outline">Cancel</a>
    </form>
  </div>
</div>"""
    return HTMLResponse(teacher_page("Record Payment", content, "payments"))


@app.post("/teacher/payments/record")
async def teacher_record_payment_post(request: Request,
    student_id: str = Form(...), amount: float = Form(...),
    date: str = Form(...), notes: str = Form("")):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    for r in rows:
        if r["student_id"] == student_id:
            r["prepaid"] = f"{float(r.get('prepaid',0)) + amount:.2f}"
    _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    _append_csv(LEDGER_FILE, LEDGER_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": student.get("name","") if student else "",
        "date": date, "status": "Payment",
        "amount": f"{amount:.2f}", "notes": notes.strip(),
    })
    return RedirectResponse("/teacher/payments?toast=Payment+recorded", status_code=303)


# ── Teacher: Analytics ─────────────────────────────────────────────────────────
@app.get("/teacher/analytics", response_class=HTMLResponse)
def teacher_analytics(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    tid    = teacher["teacher_id"]
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS) if r["teacher_id"] == tid]
    now    = datetime.now()
    monthly = []
    for i in range(5, -1, -1):
        m = now.month - i; y = now.year
        while m <= 0: m += 12; y -= 1
        rev = sum(float(r.get("amount",0)) for r in ledger
                  if r.get("date","").startswith(f"{y}-{m:02d}") and float(r.get("amount",0))>0)
        monthly.append({"label": datetime(y,m,1).strftime("%b %Y"), "rev": round(rev,2)})

    chart_json = json.dumps({"labels":[m["label"] for m in monthly],"values":[m["rev"] for m in monthly]})
    content = f"""
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<h1 style="margin-bottom:20px;">Analytics</h1>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div><div class="stat-val">${monthly[-1]['rev']:.2f}</div><div class="stat-lbl">This Month</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">📈</div><div class="stat-val">${sum(m['rev'] for m in monthly)/6:.2f}</div><div class="stat-lbl">Monthly Avg</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#dbeafe;">📋</div><div class="stat-val">{len(ledger)}</div><div class="stat-lbl">Total Transactions</div></div>
</div>
<div class="card"><h3 style="margin-bottom:14px;">📊 Monthly Revenue</h3><canvas id="chart"></canvas></div>
<script>
const D={chart_json};
new Chart(document.getElementById('chart'),{{type:'bar',data:{{labels:D.labels,datasets:[{{label:'Revenue',data:D.values,backgroundColor:'rgba(99,102,241,.75)',borderColor:'#6366f1',borderWidth:2,borderRadius:7,borderSkipped:false}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{y:{{beginAtZero:true,ticks:{{callback:v=>'$'+v}}}}}}}}}});
</script>"""
    return HTMLResponse(teacher_page("Analytics", content, "analytics"))


# ── Teacher: Schedule placeholder ─────────────────────────────────────────────
@app.get("/teacher/schedule", response_class=HTMLResponse)
def teacher_schedule(request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    content = """
<h1 style="margin-bottom:20px;">Schedule</h1>
<div class="card">
  <div class="empty-state">
    <div class="empty-state-icon">📅</div>
    <h3>Calendar Integration Coming Soon</h3>
    <p>Connect Google Calendar or iCal to see your schedule here.</p>
  </div>
</div>"""
    return HTMLResponse(teacher_page("Schedule", content, "schedule"))


# ═══════════════════════════════════════════════════════════════════════════════
#  PARENT PORTAL
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/parent/login", response_class=HTMLResponse)
def parent_login_page(error: str = ""):
    fields = """
      <div class="form-group"><label class="form-label">Student Name</label>
        <input type="text" name="student_name" placeholder="e.g. Emma Smith" required autofocus></div>
      <div class="form-group"><label class="form-label">Parent Code</label>
        <input type="password" name="parent_code" placeholder="Provided by your teacher" required></div>"""
    return HTMLResponse(_login_html("Parent Portal", "/parent/login", fields, error))


@app.post("/parent/login")
async def parent_login_post(request: Request,
    student_name: str = Form(...), parent_code: str = Form(...)):
    ip = request.client.host
    if _rl_blocked(ip):
        return RedirectResponse("/parent/login?error=Too+many+attempts.+Try+again+in+10+minutes.", status_code=303)
    students = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    match = next((s for s in students
                  if s["name"].lower() == student_name.strip().lower()
                  and s.get("parent_code","") == parent_code.strip()), None)
    if match:
        _rl_clear(ip)
        resp = RedirectResponse("/parent/dashboard", status_code=303)
        resp.set_cookie("parent_student_id", match["student_id"], httponly=True, max_age=86400*30)
        return resp
    _rl_fail(ip)
    return RedirectResponse("/parent/login?error=Invalid+student+name+or+code", status_code=303)


@app.get("/parent/logout")
def parent_logout():
    resp = RedirectResponse("/parent/login", status_code=303)
    resp.delete_cookie("parent_student_id")
    return resp


def _require_parent(request: Request) -> dict | None:
    sid = request.cookies.get("parent_student_id","")
    return get_student(sid) if sid else None


@app.get("/parent/dashboard", response_class=HTMLResponse)
def parent_dashboard(request: Request):
    student = _require_parent(request)
    if not student: return RedirectResponse("/parent/login", status_code=303)
    notes = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS) if r["student_id"]==student["student_id"]]
    notes.sort(key=lambda r: r.get("date",""), reverse=True)
    latest = notes[0] if notes else None

    latest_html = ""
    if latest:
        latest_html = (
            f'<div class="card" style="border-color:#a5b4fc;">'
            f'<h3>📌 Latest Note — {latest.get("date","")}</h3>'
            f'<p style="font-size:13px;margin:8px 0;">{latest.get("notes","")}</p>'
            + (f'<div style="background:#f0fdf4;border-left:3px solid #10b981;padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;"><strong>Assignment:</strong> {latest["assignment"]}</div>' if latest.get("assignment","").strip() else "")
            + "</div>"
        )

    prepaid = float(student.get("prepaid",0))
    rate    = float(student.get("rate",50))
    covered = int(prepaid / rate) if rate > 0 else 0
    bal_color = "var(--success)" if prepaid > 0 else "var(--danger)"

    content = f"""
<h1>Welcome, {student['name']}! 👋</h1>
<p style="color:var(--muted);margin-bottom:20px;">Your student portal</p>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div>
    <div class="stat-val" style="color:{bal_color};">${prepaid:.2f}</div>
    <div class="stat-lbl">Prepaid Balance</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">📅</div>
    <div class="stat-val">{covered}</div>
    <div class="stat-lbl">Lessons Covered</div></div>
</div>
{latest_html or '<div class="card"><p style="color:var(--muted);">No lesson notes yet.</p></div>'}"""
    return HTMLResponse(parent_page("Dashboard", content, "dashboard"))


@app.get("/parent/notes", response_class=HTMLResponse)
def parent_notes(request: Request):
    student = _require_parent(request)
    if not student: return RedirectResponse("/parent/login", status_code=303)
    notes = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS) if r["student_id"]==student["student_id"]]
    notes.sort(key=lambda r: r.get("date",""), reverse=True)

    notes_html = "".join(
        f'<div style="padding:16px;border:1px solid var(--border);border-radius:10px;margin-bottom:12px;">'
        f'<div style="font-size:11px;color:var(--muted);margin-bottom:6px;">{n.get("date","")}</div>'
        + (f'<p style="margin:0 0 10px;font-size:13px;">{n["notes"]}</p>' if n.get("notes","").strip() else "")
        + (f'<div style="background:#f0fdf4;border-left:3px solid #10b981;padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;"><strong>Assignment:</strong> {n["assignment"]}</div>' if n.get("assignment","").strip() else "")
        + '</div>'
        for n in notes
    ) or '<p style="color:var(--muted);">No notes yet.</p>'

    content = f'<h1 style="margin-bottom:20px;">Lesson Notes</h1><div class="card">{notes_html}</div>'
    return HTMLResponse(parent_page("Lesson Notes", content, "notes"))


@app.get("/parent/payments", response_class=HTMLResponse)
def parent_payments(request: Request):
    student = _require_parent(request)
    if not student: return RedirectResponse("/parent/login", status_code=303)
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS) if r["student_id"]==student["student_id"]]
    ledger.sort(key=lambda r: r.get("date",""), reverse=True)

    rows = "".join(
        f'<tr><td>{r.get("date","")}</td>'
        f'<td><span class="badge {"badge-success" if r.get("status")=="Payment" else "badge-info"}">{r.get("status","")}</span></td>'
        f'<td style="font-weight:600;color:{"var(--success)" if float(r.get("amount",0))>0 else "var(--danger)"};">${float(r.get("amount",0)):.2f}</td></tr>'
        for r in ledger
    ) or '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:20px;">No transactions yet.</td></tr>'

    content = f"""
<h1 style="margin-bottom:20px;">Payments</h1>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div>
    <div class="stat-val" style="color:{"var(--success)" if float(student.get("prepaid",0))>0 else "var(--danger)"};">${float(student.get("prepaid",0)):.2f}</div>
    <div class="stat-lbl">Current Balance</div></div>
</div>
<div class="card">
  <table><thead><tr><th>Date</th><th>Type</th><th>Amount</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>"""
    return HTMLResponse(parent_page("Payments", content, "payments"))


# ── Static ─────────────────────────────────────────────────────────────────────
@app.get("/static/style.css")
def serve_css():
    return Response(content=CSS, media_type="text/css")


@app.get("/health")
def health():
    return {"ok": True}
