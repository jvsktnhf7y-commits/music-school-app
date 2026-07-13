from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import os, csv, json, secrets, hashlib, time
from datetime import datetime, timedelta

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDGRID_FROM    = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@musicschoolapp.com")

def _send_email(to: str, subject: str, body_html: str) -> bool:
    if not SENDGRID_API_KEY:
        print(f"[Email — no key] To: {to} | {subject}")
        return False
    try:
        import urllib.request as _ur
        payload = json.dumps({
            "personalizations": [{"to": [{"email": to}]}],
            "from":    {"email": SENDGRID_FROM},
            "subject": subject,
            "content": [{"type": "text/html", "value": body_html}],
        }).encode()
        req = _ur.Request(
            "https://api.sendgrid.com/v3/mail/send", data=payload, method="POST",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}",
                     "Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[Email error] {e}")
        return False

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
                 if t["email"] == email and t.get("active", "true") == "true"), None)


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
        ("policies",  "/school/policies",  "📋", "Policies"),
        ("billing",   "/school/billing",   "💳", "Billing"),
        ("settings",  "/school/settings",  "⚙️",  "Settings"),
    ], "/school/logout")


def teacher_page(title, content, active):
    return _page(title, content, active, [
        ("dashboard",  "/teacher/dashboard",          "🏠", "Dashboard"),
        ("students",   "/teacher/students",           "👥", "My Students"),
        ("notes",      "/teacher/notes",              "📝", "Notes"),
        ("attendance", "/teacher/attendance-history", "📋", "Attendance"),
        ("payments",   "/teacher/payments",           "💳", "Payments"),
        ("analytics",  "/teacher/analytics",          "📊", "Analytics"),
        ("schedule",   "/teacher/schedule",           "📅", "Schedule"),
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
      <p style="font-size:13px;color:var(--muted);margin-bottom:14px;">
        A temporary password will be auto-generated and emailed to the teacher.
      </p>
      <button type="submit" class="btn">✉️ Send Invite</button>
      <a href="/school/teachers" class="btn btn-outline">Cancel</a>
    </form>
  </div>
</div>"""
    return HTMLResponse(school_page("Invite Teacher", content, "teachers"))


@app.post("/school/teachers/invite")
async def school_invite_post(request: Request,
    name: str = Form(...), email: str = Form(...)):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    email    = email.strip().lower()
    password = secrets.token_urlsafe(10)
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
    login_url = "https://music-school-app-hde7.onrender.com/teacher/login"
    _send_email(email, f"You've been added to {school['name']} on Music School App", f"""
    <div style="font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
      <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:14px;padding:28px;text-align:center;margin-bottom:24px;">
        <div style="font-size:36px;margin-bottom:8px;">🎵</div>
        <h1 style="color:#fff;font-size:22px;font-weight:800;margin:0;">Welcome to {school['name']}!</h1>
      </div>
      <p style="color:#334155;font-size:15px;line-height:1.7;">
        Hi {name.strip()},<br><br>
        <strong>{school['owner_name']}</strong> has added you as a teacher on <strong>Music School App</strong>.
        You can log in and start managing your students right away.
      </p>
      <div style="background:#f8faff;border:1px solid #e2e8f0;border-radius:12px;padding:18px;margin:20px 0;">
        <p style="margin:0 0 6px;font-size:13px;color:#64748b;font-weight:600;">YOUR LOGIN DETAILS</p>
        <p style="margin:4px 0;font-size:14px;color:#1e293b;"><strong>Email:</strong> {email}</p>
        <p style="margin:4px 0;font-size:14px;color:#1e293b;"><strong>Password:</strong> {password}</p>
      </div>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
        <tr>
          <td align="center">
            <a href="{login_url}" target="_blank"
               style="background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#ffffff;
                      padding:14px 32px;border-radius:12px;text-decoration:none;
                      font-weight:700;font-size:15px;display:inline-block;
                      mso-padding-alt:0;border:1px solid #6366f1;">
              Log In Now &rarr;
            </a>
          </td>
        </tr>
      </table>
      <p style="text-align:center;font-size:13px;color:#64748b;">
        Or copy this link: <a href="{login_url}" style="color:#6366f1;">{login_url}</a>
      </p>
      <p style="color:#94a3b8;font-size:12px;text-align:center;">
        Music School App · Please change your password after first login.
      </p>
    </div>
    """)
    return RedirectResponse(f"/school/teachers?toast={name.strip().replace(' ','+')}+added+%26+emailed", status_code=303)


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

    att = [r for r in ledger if r.get("status") in ("Confirmed","Missed","Cancelled")]
    confirmed  = len([r for r in att if r["status"] == "Confirmed"])
    missed     = len([r for r in att if r["status"] == "Missed"])
    cancelled  = len([r for r in att if r["status"] == "Cancelled"])
    att_pct    = f"{confirmed/(confirmed+missed)*100:.0f}%" if (confirmed+missed) > 0 else "—"
    credits    = sum(1 for r in att if r["status"] == "Cancelled")

    t_html = f'<div class="alert alert-success">{toast}</div>' if toast else ""
    content = f"""
{t_html}
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px;">
  <div style="display:flex;align-items:center;gap:12px;">
    <a href="/teacher/students" style="color:var(--muted);text-decoration:none;">← Students</a>
    <h1>{student['name']}</h1>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;">
    <a href="/teacher/students/{student_id}/edit" class="btn btn-outline btn-sm">✏️ Edit</a>
    <a href="/teacher/students/{student_id}/report" class="btn btn-outline btn-sm" target="_blank">🖨️ Report</a>
  </div>
</div>
<div class="stats-row">
  <div class="stat-card"><div class="stat-icon" style="background:#d1fae5;">💰</div>
    <div class="stat-val" style="color:{"var(--success)" if float(student.get("prepaid",0))>0 else "var(--danger)"};">${float(student.get("prepaid",0)):.2f}</div>
    <div class="stat-lbl">Prepaid Balance</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#dbeafe;">✅</div>
    <div class="stat-val">{confirmed}</div><div class="stat-lbl">Confirmed</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fee2e2;">❌</div>
    <div class="stat-val">{missed}</div><div class="stat-lbl">Missed</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fef3c7;">🎟️</div>
    <div class="stat-val">{credits}</div><div class="stat-lbl">Make-up Credits</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#ede9fe;">📊</div>
    <div class="stat-val">{att_pct}</div><div class="stat-lbl">Attendance %</div></div>
  <div class="stat-card"><div class="stat-icon" style="background:#fef3c7;">💵</div>
    <div class="stat-val">${float(student.get("rate",50)):.2f}</div><div class="stat-lbl">Rate / Lesson</div></div>
</div>
<div class="two-col">
  <div class="card">
    <div class="card-header"><span class="card-title">📝 Recent Notes</span>
      <a href="/teacher/notes/add?student_id={student_id}" class="btn btn-sm">+ Add Note</a></div>
    {notes_html}
  </div>
  <div class="card">
    <div class="card-title" style="margin-bottom:14px;">Record Attendance</div>
    <form action="/teacher/students/{student_id}/attendance" method="post" style="margin-bottom:16px;">
      <div class="form-group"><label class="form-label">Date</label>
        <input type="date" name="date" value="{datetime.now().strftime('%Y-%m-%d')}" required></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button name="status" value="Confirmed" class="btn btn-success btn-sm">✅ Confirmed</button>
        <button name="status" value="Missed" class="btn btn-sm" style="background:var(--danger);">❌ Missed</button>
        <button name="status" value="Cancelled" class="btn btn-warning btn-sm">🎟️ Cancelled</button>
      </div>
    </form>
    <hr style="border:none;border-top:1px solid var(--border);margin:14px 0;">
    <div class="card-title" style="margin-bottom:10px;">Payment</div>
    <form action="/teacher/students/{student_id}/payment" method="post" style="display:flex;gap:8px;margin-bottom:10px;">
      <input type="number" name="amount" placeholder="Amount" step="0.01" min="0" style="flex:1;">
      <button type="submit" class="btn btn-success btn-sm">+ Payment</button>
    </form>
    <form action="/teacher/students/{student_id}/charge" method="post" style="display:flex;gap:8px;">
      <input type="number" name="amount" placeholder="Charge" step="0.01" min="0" style="flex:1;" value="{float(student.get('rate',50)):.2f}">
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


@app.post("/teacher/students/{student_id}/attendance")
async def teacher_record_attendance(student_id: str, request: Request,
    date: str = Form(...), status: str = Form(...)):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    if not student: return RedirectResponse("/teacher/students", status_code=303)
    rate = float(student.get("rate", 50))
    # Confirmed = charge lesson; Cancelled = give make-up credit (no charge); Missed = charge
    amount = 0.0
    if status in ("Confirmed", "Missed"):
        amount = -rate
        rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
        for r in rows:
            if r["student_id"] == student_id:
                r["prepaid"] = f"{float(r.get('prepaid',0)) - rate:.2f}"
        _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    _append_csv(LEDGER_FILE, LEDGER_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": student.get("name",""),
        "date": date, "status": status,
        "amount": f"{amount:.2f}" if amount else "0.00", "notes": "",
    })
    return RedirectResponse(f"/teacher/students/{student_id}?toast={status}+recorded", status_code=303)


@app.get("/teacher/students/{student_id}/edit", response_class=HTMLResponse)
def teacher_edit_student_page(student_id: str, request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    if not student or student["teacher_id"] != teacher["teacher_id"]:
        return RedirectResponse("/teacher/students", status_code=303)
    content = f"""
<div style="max-width:480px;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
    <a href="/teacher/students/{student_id}" style="color:var(--muted);text-decoration:none;">← {student['name']}</a>
    <h1>Edit Student</h1>
  </div>
  <div class="card">
    <form action="/teacher/students/{student_id}/edit" method="post">
      <div class="form-group"><label class="form-label">Student Name</label>
        <input type="text" name="name" value="{student['name']}" required autofocus></div>
      <div class="form-group"><label class="form-label">Lesson Rate ($/lesson)</label>
        <input type="number" name="rate" value="{float(student.get('rate',50)):.2f}" step="0.01" min="0" required></div>
      <div class="form-group"><label class="form-label">Parent Email</label>
        <input type="email" name="parent_email" value="{student.get('parent_email','')}"></div>
      <div class="form-group"><label class="form-label">Parent Access Code</label>
        <input type="text" name="parent_code" value="{student.get('parent_code','')}">
        <small style="color:var(--muted);">Parents use this to log in to the parent portal.</small></div>
      <button type="submit" class="btn">Save Changes</button>
      <a href="/teacher/students/{student_id}" class="btn btn-outline">Cancel</a>
    </form>
  </div>
</div>"""
    return HTMLResponse(teacher_page("Edit Student", content, "students"))


@app.post("/teacher/students/{student_id}/edit")
async def teacher_edit_student_post(student_id: str, request: Request,
    name: str = Form(...), rate: float = Form(...),
    parent_email: str = Form(""), parent_code: str = Form("")):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    for r in rows:
        if r["student_id"] == student_id and r["teacher_id"] == teacher["teacher_id"]:
            r["name"]         = name.strip()
            r["rate"]         = f"{rate:.2f}"
            r["parent_email"] = parent_email.strip().lower()
            r["parent_code"]  = parent_code.strip()
    _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    return RedirectResponse(f"/teacher/students/{student_id}?toast=Student+updated", status_code=303)


@app.get("/teacher/students/{student_id}/report", response_class=HTMLResponse)
def teacher_student_report(student_id: str, request: Request):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    student = get_student(student_id)
    if not student or student["teacher_id"] != teacher["teacher_id"]:
        return RedirectResponse("/teacher/students", status_code=303)
    notes  = sorted([r for r in _read_csv(NOTES_FILE, NOTES_HEADERS)
                     if r["student_id"] == student_id],
                    key=lambda r: r.get("date",""), reverse=True)
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS) if r["student_id"] == student_id]
    att    = [r for r in ledger if r.get("status") in ("Confirmed","Missed","Cancelled")]
    confirmed = len([r for r in att if r["status"] == "Confirmed"])
    missed    = len([r for r in att if r["status"] == "Missed"])
    att_pct   = f"{confirmed/(confirmed+missed)*100:.0f}%" if (confirmed+missed) > 0 else "—"
    notes_html = "".join(f"""
    <tr>
      <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;white-space:nowrap;">{n.get('date','')}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">{n.get('notes','')}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;color:#10b981;">{n.get('assignment','')}</td>
    </tr>""" for n in notes[:20]) or '<tr><td colspan="3" style="padding:12px;color:#94a3b8;">No notes recorded.</td></tr>'
    school = next((s for s in _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
                   if s["school_id"] == teacher["school_id"]), {})
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset=UTF-8>
    <title>Progress Report — {student['name']}</title>
    <style>
      body{{font-family:-apple-system,sans-serif;max-width:760px;margin:0 auto;padding:32px;color:#1e293b;}}
      h1{{font-size:24px;font-weight:800;margin:0;}}
      .header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:28px;padding-bottom:16px;border-bottom:2px solid #6366f1;}}
      .school{{font-size:13px;color:#64748b;text-align:right;}}
      .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:28px;}}
      .stat{{background:#f8faff;border:1px solid #e2e8f0;border-radius:10px;padding:14px;text-align:center;}}
      .stat-val{{font-size:22px;font-weight:800;color:#6366f1;}}
      .stat-lbl{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.5px;margin-top:4px;}}
      h2{{font-size:15px;font-weight:700;margin:0 0 12px;color:#1e293b;}}
      table{{width:100%;border-collapse:collapse;font-size:13px;}}
      thead th{{background:#f1f5f9;padding:8px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#64748b;}}
      .print-btn{{position:fixed;bottom:24px;right:24px;background:#6366f1;color:#fff;padding:12px 24px;border-radius:10px;border:none;font-size:14px;font-weight:700;cursor:pointer;}}
      @media print{{.print-btn{{display:none;}}}}
    </style></head><body>
    <div class="header">
      <div>
        <h1>📋 Progress Report</h1>
        <div style="font-size:20px;font-weight:700;color:#6366f1;margin-top:6px;">{student['name']}</div>
        <div style="font-size:13px;color:#64748b;margin-top:4px;">Teacher: {teacher.get('name','')} · Generated {datetime.now().strftime('%B %d, %Y')}</div>
      </div>
      <div class="school"><strong>{school.get('name','')}</strong><br>${float(student.get('rate',50)):.2f}/lesson</div>
    </div>
    <div class="stats">
      <div class="stat"><div class="stat-val">{confirmed}</div><div class="stat-lbl">Confirmed</div></div>
      <div class="stat"><div class="stat-val">{missed}</div><div class="stat-lbl">Missed</div></div>
      <div class="stat"><div class="stat-val">{att_pct}</div><div class="stat-lbl">Attendance</div></div>
      <div class="stat"><div class="stat-val" style="color:{"#10b981" if float(student.get("prepaid",0))>=0 else "#ef4444"};">${float(student.get('prepaid',0)):.2f}</div><div class="stat-lbl">Balance</div></div>
    </div>
    <h2>📝 Lesson Notes</h2>
    <table><thead><tr><th>Date</th><th>Notes</th><th>Assignment</th></tr></thead>
    <tbody>{notes_html}</tbody></table>
    <button class="print-btn" onclick="window.print()">🖨️ Print</button>
    </body></html>""")


@app.get("/teacher/attendance-history", response_class=HTMLResponse)
def teacher_attendance_history(request: Request, student_id: str = "", month: str = ""):
    teacher = _require_teacher(request)
    if not teacher: return RedirectResponse("/teacher/login", status_code=303)
    students = get_students(teacher["teacher_id"])
    ledger   = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
                if r["teacher_id"] == teacher["teacher_id"]
                and r.get("status") in ("Confirmed","Missed","Cancelled")]
    if student_id:
        ledger = [r for r in ledger if r["student_id"] == student_id]
    if month:
        ledger = [r for r in ledger if r.get("date","").startswith(month)]
    ledger.sort(key=lambda r: r.get("date",""), reverse=True)

    student_opts = "".join(
        f'<option value="{s["student_id"]}" {"selected" if s["student_id"]==student_id else ""}>{s["name"]}</option>'
        for s in students)
    rows = "".join(
        f'<tr><td>{r.get("date","")}</td><td><strong>{r.get("student_name","")}</strong></td>'
        f'<td><span class="badge {"badge-success" if r["status"]=="Confirmed" else "badge-danger" if r["status"]=="Missed" else "badge-warning"}">{r["status"]}</span></td></tr>'
        for r in ledger[:100]
    ) or '<tr><td colspan="3" style="text-align:center;color:var(--muted);padding:24px;">No records found.</td></tr>'
    content = f"""
<h1 style="margin-bottom:18px;">📋 Attendance History</h1>
<div class="card" style="margin-bottom:18px;">
  <form method="get" action="/teacher/attendance-history" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
    <div class="form-group" style="margin:0;flex:1;min-width:160px;">
      <label class="form-label">Student</label>
      <select name="student_id"><option value="">All Students</option>{student_opts}</select>
    </div>
    <div class="form-group" style="margin:0;flex:1;min-width:140px;">
      <label class="form-label">Month</label>
      <input type="month" name="month" value="{month}">
    </div>
    <button type="submit" class="btn btn-sm">Filter</button>
  </form>
</div>
<div class="card">
  <table><thead><tr><th>Date</th><th>Student</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>"""
    return HTMLResponse(teacher_page("Attendance History", content, "attendance"))


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
    if student:
        _save_note_and_notify(teacher, student_id, student, date,
                              notes.strip(), assignment.strip())
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


# ═══════════════════════════════════════════════════════════════════════════════
#  MOBILE API
# ═══════════════════════════════════════════════════════════════════════════════

PUSH_TOKENS_FILE = "/data/push_tokens.json"

def _load_push_tokens() -> dict:
    if os.path.exists(PUSH_TOKENS_FILE):
        try:
            with open(PUSH_TOKENS_FILE) as f: return json.load(f)
        except Exception: pass
    return {}

def _save_push_tokens(t: dict):
    with open(PUSH_TOKENS_FILE, "w") as f: json.dump(t, f)

def _send_push(token: str, title: str, body: str, data: dict = None):
    try:
        import urllib.request as _ur
        payload = json.dumps({
            "to": token, "title": title, "body": body,
            "data": data or {}, "sound": "default",
        }).encode()
        req = _ur.Request("https://exp.host/--/api/v2/push/send", data=payload,
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        _ur.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[Push error] {e}")

# ── School Admin mobile auth ───────────────────────────────────────────────────
@app.post("/api/mobile/school/login")
async def mobile_school_login(request: Request):
    ip = request.client.host
    if _rl_blocked(ip):
        return JSONResponse({"ok": False, "error": "Too many attempts"}, status_code=429)
    data   = await request.json()
    email  = data.get("email", "").strip().lower()
    pw     = data.get("password", "")
    school = get_school_by_email(email)
    if school and school["password_hash"] == _hash(pw):
        _rl_clear(ip)
        return JSONResponse({"ok": True, "session": school["school_id"],
                             "school_name": school["name"], "role": "school"})
    _rl_fail(ip)
    return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=401)

def _school_auth(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer school:"):
        return None
    sid = auth.removeprefix("Bearer school:").strip()
    return get_school(sid)

@app.get("/api/mobile/school/dashboard")
def mobile_school_dashboard(request: Request):
    school = _school_auth(request)
    if not school: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    sid      = school["school_id"]
    teachers = get_teachers(sid)
    students = get_all_school_students(sid)
    now      = datetime.now()
    this_month = month_revenue(sid, now.year, now.month)
    total_rev  = school_revenue(sid)
    return JSONResponse({
        "ok": True,
        "school_name": school["name"],
        "teacher_count": len(teachers),
        "student_count": len(students),
        "this_month": round(this_month, 2),
        "total_revenue": round(total_rev, 2),
    })

@app.get("/api/mobile/school/teachers")
def mobile_school_teachers(request: Request):
    school = _school_auth(request)
    if not school: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    students = get_all_school_students(school["school_id"])
    teachers = get_teachers(school["school_id"])
    result = []
    for t in teachers:
        result.append({
            "teacher_id": t["teacher_id"],
            "name": t["name"],
            "email": t["email"],
            "student_count": len([s for s in students if s["teacher_id"] == t["teacher_id"]]),
            "revenue": round(teacher_revenue(t["teacher_id"]), 2),
        })
    return JSONResponse({"ok": True, "teachers": result})

@app.get("/api/mobile/school/analytics")
def mobile_school_analytics(request: Request):
    school = _school_auth(request)
    if not school: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    sid    = school["school_id"]
    now    = datetime.now()
    monthly = []
    for i in range(5, -1, -1):
        m = now.month - i; y = now.year
        while m <= 0: m += 12; y -= 1
        rev = month_revenue(sid, y, m)
        monthly.append({"label": datetime(y, m, 1).strftime("%b %Y"), "rev": round(rev, 2)})
    return JSONResponse({"ok": True, "monthly": monthly,
                         "total_revenue": round(school_revenue(sid), 2),
                         "teacher_count": len(get_teachers(sid)),
                         "student_count": len(get_all_school_students(sid))})

# ── Teacher mobile auth ────────────────────────────────────────────────────────
@app.post("/api/mobile/teacher/login")
async def mobile_teacher_login(request: Request):
    ip = request.client.host
    if _rl_blocked(ip):
        return JSONResponse({"ok": False, "error": "Too many attempts"}, status_code=429)
    data    = await request.json()
    email   = data.get("email", "").strip().lower()
    pw      = data.get("password", "")
    teacher = get_teacher_by_email(email)
    if teacher and teacher["password_hash"] == _hash(pw) and teacher.get("active","true") == "true":
        _rl_clear(ip)
        return JSONResponse({"ok": True, "session": teacher["teacher_id"],
                             "name": teacher["name"], "role": "teacher"})
    _rl_fail(ip)
    return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=401)

def _teacher_auth(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer teacher:"):
        return None
    tid = auth.removeprefix("Bearer teacher:").strip()
    return get_teacher(tid)

@app.get("/api/mobile/teacher/dashboard")
def mobile_teacher_dashboard(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    students = get_students(teacher["teacher_id"])
    now = datetime.now()
    this_month = sum(
        float(r.get("amount", 0)) for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
        if r["teacher_id"] == teacher["teacher_id"]
        and r.get("date", "").startswith(f"{now.year}-{now.month:02d}")
        and float(r.get("amount", 0)) > 0
    )
    balances = [{"name": s["name"], "prepaid": float(s.get("prepaid", 0)),
                 "rate": float(s.get("rate", 50))} for s in students]
    return JSONResponse({"ok": True, "name": teacher["name"],
                         "student_count": len(students),
                         "this_month": round(this_month, 2),
                         "total_revenue": round(teacher_revenue(teacher["teacher_id"]), 2),
                         "balances": balances})

@app.get("/api/mobile/teacher/students")
def mobile_teacher_students(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    students = get_students(teacher["teacher_id"])
    return JSONResponse({"ok": True, "students": [
        {"student_id": s["student_id"], "name": s["name"],
         "rate": float(s.get("rate", 50)), "prepaid": float(s.get("prepaid", 0)),
         "parent_email": s.get("parent_email", "")} for s in students
    ]})

@app.post("/api/mobile/teacher/students/add")
async def mobile_teacher_add_student(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    data = await request.json()
    name = data.get("name", "").strip()
    if not name: return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    student_id = secrets.token_hex(8)
    _append_csv(STUDENTS_FILE, STUDENTS_HEADERS, {
        "student_id":   student_id,
        "school_id":    teacher["school_id"],
        "teacher_id":   teacher["teacher_id"],
        "name":         name,
        "rate":         f"{float(data.get('rate', 50)):.2f}",
        "parent_email": data.get("parent_email", "").strip().lower(),
        "parent_code":  data.get("parent_code", "").strip(),
        "access_code":  "",
        "prepaid":      f"{float(data.get('prepaid', 0)):.2f}",
        "created_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return JSONResponse({"ok": True, "student_id": student_id})

@app.get("/api/mobile/teacher/students/{student_id}")
def mobile_teacher_student_detail(student_id: str, request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    student = get_student(student_id)
    if not student or student["teacher_id"] != teacher["teacher_id"]:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    notes  = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS) if r["student_id"] == student_id]
    notes.sort(key=lambda r: r.get("date", ""), reverse=True)
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS) if r["student_id"] == student_id]
    return JSONResponse({"ok": True,
        "student": {"student_id": student["student_id"], "name": student["name"],
                    "rate": float(student.get("rate", 50)),
                    "prepaid": float(student.get("prepaid", 0)),
                    "parent_email": student.get("parent_email", ""),
                    "parent_code": student.get("parent_code", "")},
        "notes": [{"date": n["date"], "notes": n["notes"], "assignment": n["assignment"]}
                  for n in notes[:10]],
        "total_charged": round(sum(float(r.get("amount", 0)) for r in ledger), 2),
    })

@app.post("/api/mobile/teacher/students/{student_id}/charge")
async def mobile_teacher_charge(student_id: str, request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    data   = await request.json()
    amount = float(data.get("amount", 0))
    student = get_student(student_id)
    if not student: return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    for r in rows:
        if r["student_id"] == student_id:
            r["prepaid"] = f"{float(r.get('prepaid', 0)) - amount:.2f}"
    _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    _append_csv(LEDGER_FILE, LEDGER_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": student.get("name", ""),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "Lesson Charged", "amount": f"-{amount:.2f}", "notes": "",
    })
    return JSONResponse({"ok": True, "new_balance": float(student.get("prepaid", 0)) - amount})

@app.post("/api/mobile/teacher/students/{student_id}/payment")
async def mobile_teacher_payment(student_id: str, request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    data   = await request.json()
    amount = float(data.get("amount", 0))
    student = get_student(student_id)
    if not student: return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    rows = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    for r in rows:
        if r["student_id"] == student_id:
            r["prepaid"] = f"{float(r.get('prepaid', 0)) + amount:.2f}"
    _write_csv(STUDENTS_FILE, STUDENTS_HEADERS, rows)
    _append_csv(LEDGER_FILE, LEDGER_HEADERS, {
        "id": secrets.token_hex(6), "school_id": teacher["school_id"],
        "teacher_id": teacher["teacher_id"], "student_id": student_id,
        "student_name": student.get("name", ""),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "Payment", "amount": f"{amount:.2f}",
        "notes": data.get("notes", ""),
    })
    return JSONResponse({"ok": True, "new_balance": float(student.get("prepaid", 0)) + amount})

@app.get("/api/mobile/teacher/notes")
def mobile_teacher_notes(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    notes = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS)
             if r["teacher_id"] == teacher["teacher_id"]]
    notes.sort(key=lambda r: r.get("date", ""), reverse=True)
    return JSONResponse({"ok": True, "notes": [
        {"id": n["id"], "student_name": n["student_name"],
         "date": n["date"], "notes": n["notes"], "assignment": n["assignment"]}
        for n in notes[:50]
    ]})

@app.post("/api/mobile/teacher/notes/add")
async def mobile_teacher_add_note(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    data       = await request.json()
    student_id = data.get("student_id", "").strip()
    student    = get_student(student_id)
    if not student: return JSONResponse({"ok": False, "error": "student not found"}, status_code=404)
    _save_note_and_notify(teacher, student_id, student,
                          data.get("date", datetime.now().strftime("%Y-%m-%d")),
                          data.get("notes", "").strip(),
                          data.get("assignment", "").strip())
    return JSONResponse({"ok": True})

@app.get("/api/mobile/teacher/payments")
def mobile_teacher_payments(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
              if r["teacher_id"] == teacher["teacher_id"]]
    ledger.sort(key=lambda r: r.get("date", ""), reverse=True)
    return JSONResponse({"ok": True, "transactions": [
        {"date": r["date"], "student_name": r["student_name"],
         "status": r["status"], "amount": float(r.get("amount", 0))}
        for r in ledger[:100]
    ]})

@app.post("/api/mobile/teacher/register-push")
async def mobile_teacher_register_push(request: Request):
    teacher = _teacher_auth(request)
    if not teacher: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    data   = await request.json()
    token  = data.get("token", "")
    tokens = _load_push_tokens()
    tokens[f"teacher:{teacher['teacher_id']}"] = token
    _save_push_tokens(tokens)
    return JSONResponse({"ok": True})

# ── Parent mobile auth ─────────────────────────────────────────────────────────
@app.post("/api/mobile/parent/login")
async def mobile_parent_login(request: Request):
    ip = request.client.host
    if _rl_blocked(ip):
        return JSONResponse({"ok": False, "error": "Too many attempts"}, status_code=429)
    data   = await request.json()
    name   = data.get("student_name", "").strip().lower()
    code   = data.get("parent_code", "").strip()
    students = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    match = next((s for s in students
                  if s["name"].lower() == name and s.get("parent_code", "") == code), None)
    if match:
        _rl_clear(ip)
        return JSONResponse({"ok": True, "session": match["student_id"],
                             "student_name": match["name"], "role": "parent"})
    _rl_fail(ip)
    return JSONResponse({"ok": False, "error": "Invalid name or code"}, status_code=401)

def _parent_auth(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer parent:"):
        return None
    sid = auth.removeprefix("Bearer parent:").strip()
    return get_student(sid)

@app.get("/api/mobile/parent/dashboard")
def mobile_parent_dashboard(request: Request):
    student = _parent_auth(request)
    if not student: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    notes = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS)
             if r["student_id"] == student["student_id"]]
    notes.sort(key=lambda r: r.get("date", ""), reverse=True)
    latest = notes[0] if notes else None
    return JSONResponse({"ok": True,
        "student_name": student["name"],
        "prepaid": float(student.get("prepaid", 0)),
        "rate": float(student.get("rate", 50)),
        "latest_note": {"date": latest["date"], "notes": latest["notes"],
                        "assignment": latest["assignment"]} if latest else None,
    })

@app.get("/api/mobile/parent/notes")
def mobile_parent_notes(request: Request):
    student = _parent_auth(request)
    if not student: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    notes = [r for r in _read_csv(NOTES_FILE, NOTES_HEADERS)
             if r["student_id"] == student["student_id"]]
    notes.sort(key=lambda r: r.get("date", ""), reverse=True)
    return JSONResponse({"ok": True, "notes": [
        {"date": n["date"], "notes": n["notes"], "assignment": n["assignment"]}
        for n in notes
    ]})

@app.get("/api/mobile/parent/payments")
def mobile_parent_payments(request: Request):
    student = _parent_auth(request)
    if not student: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    ledger = [r for r in _read_csv(LEDGER_FILE, LEDGER_HEADERS)
              if r["student_id"] == student["student_id"]]
    ledger.sort(key=lambda r: r.get("date", ""), reverse=True)
    return JSONResponse({"ok": True,
        "prepaid": float(student.get("prepaid", 0)),
        "rate": float(student.get("rate", 50)),
        "transactions": [{"date": r["date"], "status": r["status"],
                          "amount": float(r.get("amount", 0))} for r in ledger],
    })

@app.post("/api/mobile/parent/register-push")
async def mobile_parent_register_push(request: Request):
    student = _parent_auth(request)
    if not student: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    data   = await request.json()
    token  = data.get("token", "")
    tokens = _load_push_tokens()
    tokens[f"parent:{student['student_id']}"] = token
    _save_push_tokens(tokens)
    return JSONResponse({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION 2: Stripe billing · Push on note · Policy signing · Waitlist
# ═══════════════════════════════════════════════════════════════════════════════

import stripe, threading

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
WAITLIST_FILE = "/data/waitlist.csv"
POLICIES_FILE = "/data/policies.csv"
SIGNATURES_FILE = "/data/signatures.csv"

WAITLIST_HEADERS   = ["id", "email", "created_at"]
POLICIES_HEADERS   = ["id", "school_id", "title", "body", "created_at"]
SIGNATURES_HEADERS = ["id", "policy_id", "school_id", "student_id",
                      "student_name", "signed_at"]

PLAN_PRICES = {
    "school": os.environ.get("STRIPE_PRICE_SCHOOL", ""),   # $99/mo
}

_init_csv(WAITLIST_FILE,   WAITLIST_HEADERS)
_init_csv(POLICIES_FILE,   POLICIES_HEADERS)
_init_csv(SIGNATURES_FILE, SIGNATURES_HEADERS)


# ── Push helper: fire in background thread ─────────────────────────────────────
def _push_parent_note(student_id: str, student_name: str, teacher_name: str):
    tokens = _load_push_tokens()
    token  = tokens.get(f"parent:{student_id}")
    if token:
        threading.Thread(
            target=_send_push,
            args=(token, "New lesson note 🎵",
                  f"{teacher_name} added a note for {student_name}.",
                  {"type": "note", "student_id": student_id}),
            daemon=True,
        ).start()


# ── Patch add-note endpoints to fire push ─────────────────────────────────────
# We monkey-patch by wrapping _append_csv for notes is complex,
# so instead we expose a helper called from both web and mobile note saves.
# The web POST and mobile POST both call _save_note_and_notify below.

def _save_note_and_notify(teacher: dict, student_id: str, student: dict,
                           date: str, notes: str, assignment: str):
    _append_csv(NOTES_FILE, NOTES_HEADERS, {
        "id": secrets.token_hex(6),
        "school_id":    teacher["school_id"],
        "teacher_id":   teacher["teacher_id"],
        "student_id":   student_id,
        "student_name": student.get("name", ""),
        "date":         date,
        "notes":        notes,
        "assignment":   assignment,
        "created_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _push_parent_note(student_id, student.get("name", ""), teacher.get("name", ""))


# ── Waitlist ───────────────────────────────────────────────────────────────────
@app.post("/waitlist")
async def waitlist_signup(request: Request):
    try:
        body  = await request.json()
        email = body.get("email", "").strip().lower()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid body"}, status_code=400)
    if not email or "@" not in email:
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)
    existing = [r for r in _read_csv(WAITLIST_FILE, WAITLIST_HEADERS)
                if r.get("email") == email]
    if not existing:
        _append_csv(WAITLIST_FILE, WAITLIST_HEADERS, {
            "id": secrets.token_hex(6), "email": email,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return JSONResponse({"ok": True})


# ── Stripe: create checkout session ───────────────────────────────────────────
@app.post("/api/billing/checkout")
async def billing_checkout(request: Request):
    school = _require_school(request)
    if not school: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    if not STRIPE_SECRET_KEY:
        return JSONResponse({"ok": False, "error": "Stripe not configured"}, status_code=503)
    data     = await request.json()
    plan     = data.get("plan", "solo")
    price_id = PLAN_PRICES.get(plan)
    if not price_id:
        return JSONResponse({"ok": False, "error": "unknown plan"}, status_code=400)
    stripe.api_key = STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=school["owner_email"],
            metadata={"school_id": school["school_id"], "plan": plan},
            success_url=f"https://music-school-app-hde7.onrender.com/school/dashboard?toast=Subscription+active",
            cancel_url=f"https://music-school-app-hde7.onrender.com/school/billing",
        )
        return JSONResponse({"ok": True, "url": session.url})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── Stripe: webhook ────────────────────────────────────────────────────────────
@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    payload   = await request.body()
    sig_hdr   = request.headers.get("stripe-signature", "")
    stripe.api_key = STRIPE_SECRET_KEY
    try:
        event = stripe.Webhook.construct_event(payload, sig_hdr, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    if event["type"] in ("checkout.session.completed",
                          "customer.subscription.updated"):
        meta      = event["data"]["object"].get("metadata", {})
        school_id = meta.get("school_id")
        plan      = meta.get("plan", "solo")
        if school_id:
            schools = _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
            updated = False
            for s in schools:
                if s["school_id"] == school_id:
                    s["plan"] = plan
                    updated = True
            if updated:
                _write_csv(SCHOOLS_FILE, SCHOOLS_HEADERS, schools)

    elif event["type"] == "customer.subscription.deleted":
        sub       = event["data"]["object"]
        # find school by stripe customer — we store customer_id in metadata at checkout
        meta      = sub.get("metadata", {})
        school_id = meta.get("school_id")
        if school_id:
            schools = _read_csv(SCHOOLS_FILE, SCHOOLS_HEADERS)
            for s in schools:
                if s["school_id"] == school_id:
                    s["plan"] = "inactive"
            _write_csv(SCHOOLS_FILE, SCHOOLS_HEADERS, schools)

    return JSONResponse({"ok": True})


# ── Billing page (web) ─────────────────────────────────────────────────────────
@app.get("/school/billing", response_class=HTMLResponse)
def school_billing_page(request: Request):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    plan = school.get("plan", "none")
    plan_html = {
        "school":   '<span class="badge badge-success">School — $99/mo</span>',
        "inactive": '<span class="badge badge-danger">Inactive</span>',
    }.get(plan, '<span class="badge badge-muted">No active plan</span>')

    content = f"""
    <h1>💳 Billing</h1>
    <div class="card" style="max-width:520px;">
      <h2>Current Plan</h2>
      <p style="margin-bottom:16px;">Active plan: {plan_html}</p>
      <hr style="border:none;border-top:1px solid var(--border);margin:18px 0;">
      <h3 style="margin-bottom:14px;">Upgrade / Change Plan</h3>
      <form method="post" action="/school/billing/checkout">
        <input type="hidden" name="plan" value="school">
        <button class="btn" type="submit">Subscribe — $99/mo<br>
          <small style="font-weight:400;font-size:11px;">Up to 10 teachers · unlimited students</small>
        </button>
      </form>
    </div>
    """
    return HTMLResponse(school_page("Billing", content, "billing"))


@app.post("/school/billing/checkout")
async def school_billing_checkout(request: Request, plan: str = Form(...)):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    if not STRIPE_SECRET_KEY:
        return RedirectResponse("/school/billing?toast=Stripe+not+configured", status_code=303)
    price_id = PLAN_PRICES.get(plan)
    if not price_id:
        return RedirectResponse("/school/billing?toast=Unknown+plan", status_code=303)
    stripe.api_key = STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=school["owner_email"],
            metadata={"school_id": school["school_id"], "plan": plan},
            success_url=f"https://music-school-app-hde7.onrender.com/school/dashboard?toast=Subscription+active",
            cancel_url=f"https://music-school-app-hde7.onrender.com/school/billing",
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        return RedirectResponse(f"/school/billing?toast={str(e)[:80]}", status_code=303)


# ── Policy signing ─────────────────────────────────────────────────────────────
@app.get("/school/policies", response_class=HTMLResponse)
def school_policies_page(request: Request, toast: str = ""):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    policies = [p for p in _read_csv(POLICIES_FILE, POLICIES_HEADERS)
                if p["school_id"] == school["school_id"]]
    sigs     = _read_csv(SIGNATURES_FILE, SIGNATURES_HEADERS)
    toast_html = f'<div class="alert alert-success">{toast}</div>' if toast else ""
    rows = ""
    for p in policies:
        signed_count = len([s for s in sigs if s["policy_id"] == p["id"]])
        rows += (f'<tr><td><strong>{p["title"]}</strong></td>'
                 f'<td>{p["created_at"][:10]}</td>'
                 f'<td><span class="badge badge-info">{signed_count} signed</span></td>'
                 f'<td><a class="btn btn-sm btn-outline" href="/school/policies/{p["id"]}/sigs">View Signatures</a></td></tr>')
    table = (f'<table><thead><tr><th>Title</th><th>Created</th><th>Signatures</th><th></th></tr></thead>'
             f'<tbody>{rows or "<tr><td colspan=4 style=text-align:center;color:var(--muted)>No policies yet.</td></tr>"}</tbody></table>'
             if policies else
             '<div class="empty-state"><div class="empty-state-icon">📋</div><p>No policies yet. Add one below.</p></div>')
    content = f"""
    <h1>📋 Policies</h1>
    {toast_html}
    <div class="card">{table}</div>
    <div class="card" style="max-width:600px;">
      <h2>Add Policy</h2>
      <form method="post" action="/school/policies/add">
        <div class="form-group">
          <label class="form-label">Title</label>
          <input type="text" name="title" placeholder="e.g. Studio Policy 2026" required>
        </div>
        <div class="form-group">
          <label class="form-label">Policy Text</label>
          <textarea name="body" rows="8" placeholder="Enter the full policy text..." required style="width:100%;padding:8px 11px;border:1.5px solid var(--border);border-radius:8px;font-size:13px;font-family:inherit;"></textarea>
        </div>
        <button class="btn" type="submit">➕ Add Policy</button>
      </form>
    </div>
    """
    return HTMLResponse(school_page("Policies", content, "policies"))


@app.post("/school/policies/add")
async def school_add_policy(request: Request,
                             title: str = Form(...), body: str = Form(...)):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    _append_csv(POLICIES_FILE, POLICIES_HEADERS, {
        "id": secrets.token_hex(8), "school_id": school["school_id"],
        "title": title.strip(), "body": body.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return RedirectResponse("/school/policies?toast=Policy+added", status_code=303)


@app.get("/school/policies/{policy_id}/sigs", response_class=HTMLResponse)
def policy_signatures(request: Request, policy_id: str):
    school = _require_school(request)
    if not school: return RedirectResponse("/school/login", status_code=303)
    policy = next((p for p in _read_csv(POLICIES_FILE, POLICIES_HEADERS)
                   if p["id"] == policy_id and p["school_id"] == school["school_id"]), None)
    if not policy: return RedirectResponse("/school/policies", status_code=303)
    sigs = [s for s in _read_csv(SIGNATURES_FILE, SIGNATURES_HEADERS)
            if s["policy_id"] == policy_id]
    students = get_all_school_students(school["school_id"])
    signed_ids = {s["student_id"] for s in sigs}
    rows = ""
    for stu in students:
        if stu["student_id"] in signed_ids:
            sig = next(s for s in sigs if s["student_id"] == stu["student_id"])
            rows += (f'<tr><td>{stu["name"]}</td>'
                     f'<td><span class="badge badge-success">✓ Signed {sig["signed_at"][:10]}</span></td></tr>')
        else:
            rows += (f'<tr><td>{stu["name"]}</td>'
                     f'<td><span class="badge badge-danger">Not signed</span></td></tr>')
    content = f"""
    <h1>📋 {policy["title"]} — Signatures</h1>
    <div class="card">
      <table><thead><tr><th>Student</th><th>Status</th></tr></thead>
      <tbody>{rows or "<tr><td colspan=2>No students found.</td></tr>"}</tbody></table>
    </div>
    <a href="/school/policies" class="btn btn-outline">← Back to Policies</a>
    """
    return HTMLResponse(school_page("Policy Signatures", content, "policies"))


# ── Policy: parent web signing ─────────────────────────────────────────────────
@app.get("/sign/{policy_id}", response_class=HTMLResponse)
def policy_sign_page(request: Request, policy_id: str, code: str = ""):
    policy = next((p for p in _read_csv(POLICIES_FILE, POLICIES_HEADERS)
                   if p["id"] == policy_id), None)
    if not policy:
        return HTMLResponse("<h2>Policy not found.</h2>", status_code=404)
    already_signed = ""
    if code:
        students = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
        student  = next((s for s in students if s.get("access_code") == code
                         and s["school_id"] == policy["school_id"]), None)
        if student:
            existing = next((s for s in _read_csv(SIGNATURES_FILE, SIGNATURES_HEADERS)
                             if s["policy_id"] == policy_id
                             and s["student_id"] == student["student_id"]), None)
            if existing:
                already_signed = f'<div class="alert alert-success">✓ Already signed on {existing["signed_at"][:10]}.</div>'
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset=UTF-8>
    <meta name=viewport content="width=device-width,initial-scale=1">
    <title>Sign Policy — {policy["title"]}</title>
    <style>
      body{{font-family:-apple-system,sans-serif;background:#f8faff;padding:24px;max-width:640px;margin:0 auto;}}
      h1{{font-size:22px;font-weight:800;margin-bottom:8px;color:#1e293b;}}
      .policy-body{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;
                    white-space:pre-wrap;font-size:14px;line-height:1.7;color:#334155;
                    max-height:340px;overflow-y:auto;margin:16px 0;}}
      .form-group{{margin-bottom:14px;}}
      label{{display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:#64748b;}}
      input{{width:100%;padding:10px 13px;border:1.5px solid #e2e8f0;border-radius:9px;font-size:14px;}}
      input:focus{{outline:none;border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.1);}}
      .btn{{display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
            color:#fff;border:none;border-radius:10px;font-weight:700;font-size:15px;cursor:pointer;width:100%;}}
      .alert-success{{background:#d1fae5;color:#065f46;border:1px solid #a7f3d0;
                      padding:12px 16px;border-radius:9px;margin-bottom:14px;font-weight:600;}}
    </style></head><body>
    <h1>📋 {policy["title"]}</h1>
    <p style="color:#64748b;font-size:14px;">Please read and sign this policy from {policy["school_id"]}.</p>
    <div class="policy-body">{policy["body"]}</div>
    {already_signed}
    <form method="post" action="/sign/{policy_id}">
      <div class="form-group">
        <label>Your Student Access Code</label>
        <input type="text" name="code" value="{code}" placeholder="Enter your access code" required>
      </div>
      <button class="btn" type="submit">✍️ I agree &amp; sign</button>
    </form>
    </body></html>""")


@app.post("/sign/{policy_id}", response_class=HTMLResponse)
async def policy_sign_post(request: Request, policy_id: str, code: str = Form(...)):
    policy = next((p for p in _read_csv(POLICIES_FILE, POLICIES_HEADERS)
                   if p["id"] == policy_id), None)
    if not policy:
        return HTMLResponse("<h2>Policy not found.</h2>", status_code=404)
    students = _read_csv(STUDENTS_FILE, STUDENTS_HEADERS)
    student  = next((s for s in students if s.get("access_code") == code
                     and s["school_id"] == policy["school_id"]), None)
    if not student:
        return HTMLResponse(f"""<!DOCTYPE html><html><body style="font-family:-apple-system,sans-serif;padding:24px;">
        <div style="background:#fee2e2;color:#991b1b;padding:14px;border-radius:9px;margin-bottom:14px;">
          Invalid access code. Please check with your teacher.
        </div>
        <a href="/sign/{policy_id}" style="color:#6366f1;">← Try again</a>
        </body></html>""")
    existing = next((s for s in _read_csv(SIGNATURES_FILE, SIGNATURES_HEADERS)
                     if s["policy_id"] == policy_id
                     and s["student_id"] == student["student_id"]), None)
    if not existing:
        _append_csv(SIGNATURES_FILE, SIGNATURES_HEADERS, {
            "id": secrets.token_hex(6), "policy_id": policy_id,
            "school_id": policy["school_id"],
            "student_id": student["student_id"],
            "student_name": student["name"],
            "signed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return HTMLResponse(f"""<!DOCTYPE html><html><body style="font-family:-apple-system,sans-serif;padding:24px;max-width:480px;margin:0 auto;text-align:center;">
    <div style="margin-top:60px;">
      <div style="font-size:64px;margin-bottom:16px;">✅</div>
      <h1 style="font-size:22px;font-weight:800;color:#1e293b;margin-bottom:8px;">Signed!</h1>
      <p style="color:#64748b;">Thank you, {student["name"]}. Your signature has been recorded.</p>
    </div></body></html>""")


# ── Mobile: policy endpoints ───────────────────────────────────────────────────
@app.get("/api/mobile/parent/policies")
def mobile_parent_policies(request: Request):
    student = _parent_auth(request)
    if not student: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    policies = [p for p in _read_csv(POLICIES_FILE, POLICIES_HEADERS)
                if p["school_id"] == student["school_id"]]
    sigs     = _read_csv(SIGNATURES_FILE, SIGNATURES_HEADERS)
    result   = []
    for p in policies:
        signed = any(s["policy_id"] == p["id"] and s["student_id"] == student["student_id"]
                     for s in sigs)
        result.append({"id": p["id"], "title": p["title"], "signed": signed,
                       "sign_url": f"https://music-school-app-hde7.onrender.com/sign/{p['id']}"
                                   f"?code={student.get('access_code', '')}"})
    return JSONResponse({"ok": True, "policies": result})


# ── Mobile: school billing ─────────────────────────────────────────────────────
@app.post("/api/mobile/school/billing/checkout")
async def mobile_school_billing_checkout(request: Request):
    school = _require_school(request)
    if not school: return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
    if not STRIPE_SECRET_KEY:
        return JSONResponse({"ok": False, "error": "Stripe not configured"}, status_code=503)
    data     = await request.json()
    plan     = data.get("plan", "solo")
    price_id = PLAN_PRICES.get(plan)
    if not price_id:
        return JSONResponse({"ok": False, "error": "unknown plan"}, status_code=400)
    stripe.api_key = STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=school["owner_email"],
            metadata={"school_id": school["school_id"], "plan": plan},
            success_url=f"https://music-school-app-hde7.onrender.com/school/dashboard?toast=Subscription+active",
            cancel_url=f"https://music-school-app-hde7.onrender.com/school/billing",
        )
        return JSONResponse({"ok": True, "url": session.url})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
