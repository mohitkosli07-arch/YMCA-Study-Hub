import os, sqlite3, re, uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or ("dev-only-change-me" if not os.environ.get("RENDER") else None)
if not app.secret_key:
    raise RuntimeError("SECRET_KEY must be set in production.")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1" if os.environ.get("RENDER") else "0") == "1",
    SESSION_COOKIE_NAME="ymca_session"
)

# Direct staff uploads.
DATA_DIR = os.environ.get("DATA_DIR", "")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or (os.path.join(DATA_DIR, "uploads") if DATA_DIR else os.path.join(app.static_folder, "resources", "uploads"))
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "txt"}
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# Set these in Render Environment Variables for production.
STAFF_NAME = os.environ.get("STAFF_NAME", "Mohit")
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD") or ("dev-password-change-me" if not os.environ.get("RENDER") else None)
if not STAFF_PASSWORD:
    raise RuntimeError("STAFF_PASSWORD must be set in production.")
DB_PATH = os.environ.get("DB_PATH") or (os.path.join(DATA_DIR, "study_hub.db") if DATA_DIR else "study_hub.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

def allowed_file(filename):
    return bool(filename) and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file):
    if not file or not file.filename:
        return None, "Please select a file to upload."
    if not allowed_file(file.filename):
        return None, "Unsupported file type. Allowed: PDF, DOC, DOCX, PPT, PPTX, TXT."
    original = os.path.basename(file.filename)
    stem, ext = os.path.splitext(original)
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "resource"
    filename = f"{safe_stem}_{uuid.uuid4().hex[:10]}{ext.lower()}"
    file.save(os.path.join(UPLOAD_DIR, filename))
    return filename, None


branches = {"it": {"code":"IT","name":"Information Technology","semesters": {
1:{"available":False,"subjects":[]}, 2:{"available":False,"subjects":[]},
3:{"available":True,"subjects":[
{"slug":"dsa","code":"DSA","name":"Data Structures & Algorithms"},
{"slug":"aec","code":"AEC","name":"AEC"},{"slug":"maths","code":"MATHS","name":"Mathematics"},
{"slug":"de","code":"DE","name":"DE"},{"slug":"ee","code":"EE","name":"EE"},
{"slug":"it-workshop","code":"IT WORKSHOP","name":"IT Workshop"}]},
4:{"available":False,"subjects":[]},5:{"available":False,"subjects":[]},
6:{"available":False,"subjects":[]},7:{"available":False,"subjects":[]},8:{"available":False,"subjects":[]}}}}

CATEGORIES=[("notes","📚","Notes"),("pyp","📄","Previous Year Papers"),
("assignments","📝","Assignments"),("practicals","💻","Practicals"),
("syllabus","📋","Syllabus"),("important","❓","Important Questions")]

def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def canonical_branch(value):
    """Convert common branch names/codes to the exact values used by the public site."""
    v = (value or "").strip().lower()
    if v in {"it", "information technology", "information-technology"}:
        return "IT"
    return (value or "").strip()

def canonical_semester(value):
    """Store semester as a simple number string (e.g. 3, 3rd, 3rd Semester -> 3)."""
    m = re.search(r"\\d+", (value or "").strip())
    return m.group(0) if m else (value or "").strip()

def canonical_subject(branch_code, semester_value, value):
    """Convert subject code/name/slug to the exact subject code used in branches."""
    v = (value or "").strip().lower()
    b = branches.get((branch_code or "").strip().lower())
    try:
        sem = int(canonical_semester(semester_value))
    except (TypeError, ValueError):
        return (value or "").strip()
    if b and sem in b["semesters"]:
        for sub in b["semesters"][sem]["subjects"]:
            if v in {sub["slug"].lower(), sub["code"].lower(), sub["name"].lower()}:
                return sub["code"]
    return (value or "").strip()

def canonical_resource_values(title, branch, semester, subject, category, file_path, contributor_name):
    branch = canonical_branch(branch)
    semester = canonical_semester(semester)
    subject = canonical_subject(branch, semester, subject)
    return [title.strip(), branch, semester, subject, category.strip(), file_path.strip(), contributor_name.strip()]

def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS contributions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,roll_no TEXT NOT NULL,
      branch TEXT NOT NULL,semester TEXT NOT NULL,phone TEXT NOT NULL,
      contribution TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Pending',
      submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,published_count INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS published_resources(
      id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,branch TEXT NOT NULL,
      semester TEXT NOT NULL,subject TEXT NOT NULL,category TEXT NOT NULL,
      file_path TEXT NOT NULL,contributor_id INTEGER,contributor_name TEXT,
      published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    # Repair older resources that may have been stored as "Information Technology",
    # "3rd Semester", "Data Structures & Algorithms", etc. The public pages use
    # canonical values such as IT / 3 / DSA.
    existing = c.execute("SELECT id,branch,semester,subject FROM published_resources").fetchall()
    for r in existing:
        branch = canonical_branch(r["branch"])
        semester = canonical_semester(r["semester"])
        subject = canonical_subject(branch, semester, r["subject"])
        c.execute("""UPDATE published_resources
                     SET branch=?, semester=?, subject=?
                     WHERE id=?""",
                  (branch, semester, subject, r["id"]))

    c.commit(); c.close()
init_db()

def staff_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("staff_logged_in"): return redirect(url_for("staff_login"))
        return f(*a,**k)
    return w

@app.route("/")
def home(): return render_template("index.html")

@app.route("/branch/<code>")
def branch(code):
    b=branches.get(code.lower())
    return render_template("semesters.html",branch=b,branch_slug=code.lower()) if b else (render_template("not_found.html"),404)

@app.route("/branch/<code>/semester/<int:sem>")
def semester(code,sem):
    b=branches.get(code.lower())
    if not b or sem not in b["semesters"]: return render_template("not_found.html"),404
    s=b["semesters"][sem]
    if not s["available"]: return render_template("coming_soon.html",title=f"{b['code']} — Semester {sem}")
    return render_template("subjects.html",branch=b,branch_slug=code.lower(),semester=sem,semester_data=s)

@app.route("/branch/<code>/semester/<int:sem>/subject/<slug>")
def subject(code,sem,slug):
    b=branches.get(code.lower())
    if not b or sem not in b["semesters"]: return render_template("not_found.html"),404
    s=next((x for x in b["semesters"][sem]["subjects"] if x["slug"]==slug),None)
    if not s: return render_template("not_found.html"),404
    c=db(); rows=c.execute("""SELECT * FROM published_resources
      WHERE LOWER(TRIM(branch))=LOWER(?)
        AND CAST(TRIM(semester) AS INTEGER)=?
        AND LOWER(TRIM(subject))=LOWER(?)
      ORDER BY category,published_at DESC""",(b["code"],sem,s["code"])).fetchall(); c.close()
    grouped={x[0]:[] for x in CATEGORIES}
    for r in rows:
        if r["category"] in grouped: grouped[r["category"]].append(r)
    return render_template("subject.html",branch=b,semester=sem,subject=s,grouped=grouped,categories=CATEGORIES)

@app.route("/contribution")
def contribution():
    return render_template("contribution.html")

@app.route("/contribute",methods=["GET","POST"])
def contribute():
    if request.method=="POST":
        fields=["name","roll_no","branch","semester","phone","contribution"]
        d={x:request.form.get(x,"").strip() for x in fields}
        if not all(d.values()):
            flash("Please fill every required field.","error"); return render_template("contribute.html",data=d)
        c=db(); c.execute("""INSERT INTO contributions
        (name,roll_no,branch,semester,phone,contribution) VALUES (?,?,?,?,?,?)""",tuple(d.values()))
        c.commit(); c.close(); return render_template("contribute_success.html",name=d["name"])
    return render_template("contribute.html",data={})

@app.route("/contribution/leaderboard")
def leaderboard():
    c=db()
    rows=c.execute("""SELECT name,roll_no,branch,semester,
      COUNT(*) contributions,
      MAX(submitted_at) last_activity
      FROM contributions
      WHERE status='Published'
      GROUP BY name,roll_no,branch,semester
      ORDER BY contributions DESC,name""").fetchall()
    details={}
    for r in rows:
        details[r["name"]+"|"+r["roll_no"]+"|"+r["branch"]+"|"+r["semester"]] = c.execute(
          """SELECT title,branch,semester,subject,category,contributor_name,published_at
             FROM published_resources
             WHERE contributor_id IN
               (SELECT id FROM contributions WHERE name=? AND roll_no=? AND branch=? AND semester=? AND status='Published')
             ORDER BY published_at DESC""",
          (r["name"],r["roll_no"],r["branch"],r["semester"])).fetchall()
    c.close()
    return render_template("leaderboard.html",rows=rows,details=details)

@app.route("/leaderboard")
def old_leaderboard_block():
    return render_template("not_found.html"), 404

@app.route("/staff/login",methods=["GET","POST"])
def staff_login():
    if request.method=="POST":
        if not STAFF_PASSWORD:
            flash("Staff password is not configured. Set STAFF_PASSWORD before using the staff area.","error")
        elif request.form.get("name","").strip()==STAFF_NAME and request.form.get("password","")==STAFF_PASSWORD:
            session["staff_logged_in"]=True; return redirect(url_for("staff_dashboard"))
        flash("Invalid staff credentials.","error")
    return render_template("staff_login.html")

@app.route("/staff/logout")
def logout(): session.clear(); return redirect(url_for("home"))

@app.route("/resource/<path:filename>")
def resource_file(filename):
    # Uploaded resources live outside Flask's static directory in production.
    # Only the basename is allowed, preventing path traversal.
    safe_name = os.path.basename(filename)
    if safe_name != filename or safe_name in {"", ".", ".."}:
        abort(404)
    full_path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.isfile(full_path):
        abort(404)
    return send_from_directory(UPLOAD_DIR, safe_name, as_attachment=False)

@app.get("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/staff/resources")
@staff_required
def staff_resources():
    c=db()
    resources=c.execute("""SELECT * FROM published_resources ORDER BY published_at DESC""").fetchall()
    c.close()
    return render_template("staff_resources.html", resources=resources)

@app.route("/staff/upload", methods=["POST"])
@staff_required
def upload_resource_file():
    uploaded = request.files.get("file")
    file_path, error = save_uploaded_file(uploaded)
    if error:
        flash(error, "error")
    else:
        flash(f"File uploaded successfully: {file_path}", "success")
    return redirect(request.referrer or url_for("staff_resources"))


@app.route("/staff/resources/add", methods=["GET","POST"])
@staff_required
def add_resource():
    if request.method=="POST":
        title = request.form.get("title","").strip()
        branch = request.form.get("branch","").strip()
        semester = request.form.get("semester","").strip()
        subject = request.form.get("subject","").strip()
        category = request.form.get("category","").strip()
        contributor_name = request.form.get("contributor_name","").strip()
        file_path = request.form.get("file_path","").strip()

        uploaded = request.files.get("file")
        if uploaded and uploaded.filename:
            file_path, error = save_uploaded_file(uploaded)
            if error:
                flash(error, "error")
                return render_template("resource_form.html", resource=request.form, categories=CATEGORIES, mode="Add")

        if not all([title, branch, semester, subject, category, file_path]):
            flash("Title, branch, semester, subject, category and a file are required.", "error")
            return render_template("resource_form.html", resource=request.form, categories=CATEGORIES, mode="Add")

        vals = canonical_resource_values(title, branch, semester, subject, category, file_path, contributor_name)
        c=db()
        c.execute("INSERT INTO published_resources (title,branch,semester,subject,category,file_path,contributor_name) VALUES (?,?,?,?,?,?,?)", tuple(vals))
        c.commit(); c.close()
        flash("Resource added successfully.", "success")
        return redirect(url_for("staff_resources"))
    return render_template("resource_form.html", resource={}, categories=CATEGORIES, mode="Add")

@app.route("/staff/resources/<int:rid>/edit", methods=["GET","POST"])
@staff_required
def edit_resource(rid):
    c=db()
    resource=c.execute("SELECT * FROM published_resources WHERE id=?",(rid,)).fetchone()
    if not resource:
        c.close(); return render_template("not_found.html"),404
    if request.method=="POST":
        title = request.form.get("title", "").strip()
        branch = request.form.get("branch", "").strip()
        semester = request.form.get("semester", "").strip()
        subject = request.form.get("subject", "").strip()
        category = request.form.get("category", "").strip()
        contributor_name = request.form.get("contributor_name", "").strip()
        file_path = resource["file_path"] or ""
        uploaded = request.files.get("file")
        old_file = file_path
        if uploaded and uploaded.filename:
            file_path, error = save_uploaded_file(uploaded)
            if error:
                c.close(); flash(error, "error")
                return render_template("resource_form.html", resource=resource, categories=CATEGORIES, mode="Edit")
        if not all([title, branch, semester, subject, category, file_path]):
            c.close(); flash("Title, branch, semester, subject, category and a file are required.", "error")
            return render_template("resource_form.html", resource=resource, categories=CATEGORIES, mode="Edit")
        vals = canonical_resource_values(title, branch, semester, subject, category, file_path, contributor_name)
        c.execute("""UPDATE published_resources SET title=?,branch=?,semester=?,subject=?,
          category=?,file_path=?,contributor_name=? WHERE id=?""",(*vals,rid))
        c.commit(); c.close()
        if uploaded and uploaded.filename and old_file and old_file != file_path:
            old_name=os.path.basename(old_file)
            old_path=os.path.join(UPLOAD_DIR, old_name)
            if old_name == old_file and os.path.isfile(old_path):
                try: os.remove(old_path)
                except OSError: pass
        flash("Resource updated.","success")
        return redirect(url_for("staff_resources"))
    c.close()
    return render_template("resource_form.html", resource=resource, categories=CATEGORIES, mode="Edit")

@app.post("/staff/resources/<int:rid>/delete")
@staff_required
def delete_resource(rid):
    c=db(); resource=c.execute("SELECT file_path FROM published_resources WHERE id=?",(rid,)).fetchone()
    c.execute("DELETE FROM published_resources WHERE id=?",(rid,)); c.commit(); c.close()
    if resource and resource["file_path"]:
        filename=os.path.basename(resource["file_path"])
        if filename == resource["file_path"]:
            path=os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(path):
                try: os.remove(path)
                except OSError: pass
    flash("Resource deleted.","success")
    return redirect(url_for("staff_resources"))

@app.route("/staff")
def staff_entry():
    # Public Staff button always opens the login page.
    # Dashboard is deliberately at /staff/dashboard and is protected.
    if not session.get("staff_logged_in"):
        return redirect(url_for("staff_login"))
    return redirect(url_for("staff_dashboard"))

@app.route("/staff/dashboard")
@staff_required
def staff_dashboard():
    c=db()
    pending=c.execute("SELECT * FROM contributions WHERE status='Pending' ORDER BY submitted_at DESC").fetchall()
    contacted=c.execute("SELECT * FROM contributions WHERE status='Contacted' ORDER BY submitted_at DESC").fetchall()
    published=c.execute("SELECT * FROM contributions WHERE status='Published' ORDER BY submitted_at DESC").fetchall()
    stats=[c.execute("SELECT COUNT(*) FROM contributions WHERE status=?", (x,)).fetchone()[0] for x in ["Pending","Contacted","Published"]]
    resources=c.execute("SELECT COUNT(*) FROM published_resources").fetchone()[0]; c.close()
    return render_template("staff.html",pending=pending,contacted=contacted,published=published,
                           stats={"pending":stats[0],"contacted":stats[1],"published":stats[2],"resources":resources})

@app.post("/staff/<int:cid>/contacted")
@staff_required
def contacted(cid):
    c=db(); c.execute("UPDATE contributions SET status='Contacted' WHERE id=?",(cid,)); c.commit(); c.close()
    return redirect(url_for("staff_dashboard"))

@app.route("/staff/publish/<int:cid>",methods=["GET","POST"])
@staff_required
def publish(cid):
    c=db(); person=c.execute("SELECT * FROM contributions WHERE id=?",(cid,)).fetchone()
    if not person: c.close(); return redirect(url_for("staff_dashboard"))
    if request.method=="POST":
        title = request.form.get("title","").strip()
        branch = request.form.get("branch","").strip()
        semester = request.form.get("semester","").strip()
        subject = request.form.get("subject","").strip()
        category = request.form.get("category","").strip()
        file_path = request.form.get("file_path","").strip()

        uploaded = request.files.get("file")
        if uploaded and uploaded.filename:
            file_path, error = save_uploaded_file(uploaded)
            if error:
                c.close()
                flash(error, "error")
                return render_template("publish.html",person=person,categories=CATEGORIES)

        if not all([title, branch, semester, subject, category, file_path]):
            flash("Title, branch, semester, subject, category and a file are required.", "error")
            c.close()
            return render_template("publish.html",person=person,categories=CATEGORIES)

        branch = canonical_branch(branch)
        semester = canonical_semester(semester)
        subject = canonical_subject(branch, semester, subject)
        vals = [title, branch, semester, subject, category, file_path]
        c.execute("""INSERT INTO published_resources
          (title,branch,semester,subject,category,file_path,contributor_id,contributor_name)
          VALUES (?,?,?,?,?,?,?,?)""",(*vals,person["id"],person["name"]))
        c.execute("UPDATE contributions SET status='Published',published_count=published_count+1 WHERE id=?",(cid,))
        c.commit(); c.close(); flash("Resource published.","success"); return redirect(url_for("staff_dashboard"))
    c.close(); return render_template("publish.html",person=person,categories=CATEGORIES)

@app.route("/search")
def search():
    q=request.args.get("q","").lower().strip(); results=[]
    if q:
        for slug,b in branches.items():
            if q in b["code"].lower() or q in b["name"].lower(): results.append((f"branch/{slug}",b))
            for sem,s in b["semesters"].items():
                for sub in s["subjects"]:
                    if q in sub["code"].lower() or q in sub["name"].lower():
                        results.append((f"branch/{slug}/semester/{sem}/subject/{sub['slug']}",sub))
    return render_template("search.html",query=q,results=results)

@app.errorhandler(413)
def file_too_large(error):
    flash("File is too large. Maximum upload size is 25 MB.", "error")
    return redirect(request.referrer or url_for("staff_resources"))


if __name__=="__main__": app.run(debug=True)
