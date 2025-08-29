#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SohbetLite Pro
- Modern + Lite (Nokia 6303)
- Şifreli odalar
- Foto/Video yükleme
- Tek tık paylaşım
"""
import os, sqlite3, uuid, html, hashlib
from datetime import datetime
from flask import Flask, request, redirect, url_for, make_response, send_from_directory

from werkzeug.utils import secure_filename

APP_SECRET = os.environ.get("APP_SECRET", os.urandom(16))
DB_PATH = os.environ.get("DB_PATH", "chat.db")
SITE_NAME = os.environ.get("SITE_NAME", "SohbetLite Pro")
DEFAULT_ROOM = os.environ.get("DEFAULT_ROOM", "genel")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))  # 10MB

ALLOWED_IMG = {"jpg","jpeg","png","gif","webp"}
ALLOWED_VID = {"mp4","webm","3gp","mov","m4v"}

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  token TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  passhash TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room TEXT NOT NULL,
  username TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'text',
  msg TEXT,
  media TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_room_time ON messages(room, created_at);
"""

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                conn.execute(stmt)
        conn.commit()

@app.before_first_request
def _startup():
    init_db()

def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def sha256(s: str) -> str:
    if isinstance(APP_SECRET, bytes):
        secret = APP_SECRET
    else:
        secret = str(APP_SECRET).encode()
    return hashlib.sha256((s or "").encode("utf-8") + secret).hexdigest()

def get_user_by_token(token: str):
    if not token:
        return None
    with db() as conn:
        cur = conn.execute("SELECT username, token FROM users WHERE token=?", (token,))
        row = cur.fetchone()
        return dict(row) if row else None

def ensure_user(username: str):
    username = (username or "").strip()
    if not username or not (1 <= len(username) <= 20):
        return None
    if any(ch in username for ch in " <>'\"\n\r\t/\\?"):
        return None
    tok = uuid.uuid4().hex
    try:
        with db() as conn:
            conn.execute("INSERT INTO users(username, token, created_at) VALUES(?,?,?)",
                         (username, tok, now_iso()))
            conn.commit()
        return {"username": username, "token": tok}
    except sqlite3.IntegrityError:
        return None

def ensure_room(name: str, password: str = ""):
    name = (name or DEFAULT_ROOM).strip()[:32]
    p = sha256(password) if password else None
    with db() as conn:
        cur = conn.execute("SELECT name, passhash FROM rooms WHERE name=?", (name,))
        row = cur.fetchone()
        if row:
            return {"name": row["name"], "passhash": row["passhash"]}
        conn.execute("INSERT INTO rooms(name, passhash, created_at) VALUES(?,?,?)",
                     (name, p, now_iso()))
        conn.commit()
        return {"name": name, "passhash": p}

def room_requires_pass(name: str) -> bool:
    with db() as conn:
        cur = conn.execute("SELECT passhash FROM rooms WHERE name=?", (name,))
        row = cur.fetchone()
        return bool(row and row["passhash"])

def check_room_pass(name: str, password: str) -> bool:
    with db() as conn:
        cur = conn.execute("SELECT passhash FROM rooms WHERE name=?", (name,))
        row = cur.fetchone()
        if not row or not row["passhash"]:
            return True
        return sha256(password) == row["passhash"]

def add_message(room: str, username: str, text: str = "", mtype: str = "text", media: str = None):
    room = (room or DEFAULT_ROOM).strip()[:32]
    username = html.escape((username or "misafir")[:20])
    text = html.escape((text or "")[:500])
    with db() as conn:
        conn.execute("INSERT INTO messages(room, username, type, msg, media, created_at) VALUES(?,?,?,?,?,?)",
                     (room, username, mtype, text, media, now_iso()))
        conn.commit()
    return True

def recent_messages(room: str, limit: int = 80):
    room = (room or DEFAULT_ROOM).strip()[:32]
    with db() as conn:
        cur = conn.execute(
            "SELECT username, type, msg, media, created_at FROM messages WHERE room=? ORDER BY id DESC LIMIT ?",
            (room, limit)
        )
        rows = [dict(r) for r in cur.fetchall()]
    return list(reversed(rows))

def is_allowed_file(filename: str):
    ext = filename.rsplit(".",1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_IMG or ext in ALLOWED_VID

@app.route("/")
def home():
    return f"""<!doctype html><html lang=tr><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>
<title>{SITE_NAME}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;margin:0;background:#0b1020;color:#e8ecf1;}}
.header{{padding:24px 16px;text-align:center;}}
.card{{max-width:640px;margin:0 auto 24px;background:#121933;border:1px solid #1e2746;border-radius:16px;padding:16px;box-shadow:0 6px 24px rgba(0,0,0,.35);}}
input,button{{width:100%;padding:12px;border-radius:12px;border:1px solid #2a355e;background:#0f1530;color:#e8ecf1}}
label{{display:block;margin:6px 0 4px}}
button{{cursor:pointer;margin-top:8px}}
small{{opacity:.8}}
</style>
<div class=header>
  <h1>{SITE_NAME}</h1>
  <p>Hızlı kayıt, şifreli odalar, foto/video paylaşımı.</p>
</div>
<div class=card>
  <form action='/register' method=post>
    <label>Kullanıcı adı (1–20)</label>
    <input name=username maxlength=20 required>
    <label>Oda adı</label>
    <input name=room placeholder='{DEFAULT_ROOM}' maxlength=32>
    <label>Oda şifresi (opsiyonel)</label>
    <input name=room_pass type=password maxlength=64 placeholder='(boş bırakabilirsiniz)'>
    <button type=submit>Giriş bağlantımı oluştur</button>
    <p><small>Bağlantınızı paylaşabilir ya da Lite sürümünü Nokia ile kullanabilirsiniz.</small></p>
  </form>
</div>
"""

@app.route("/register", methods=["POST"]) 
def register():
    username = request.form.get("username","");
    room = (request.form.get("room") or DEFAULT_ROOM).strip()[:32]
    room_pass = request.form.get("room_pass","");
    user = ensure_user(username)
    if not user:
        return redirect(url_for("home"))
    ensure_room(room, room_pass)
    modern_url = url_for("room_modern", room=room)
    lite_url = url_for("lite", u=user["username"], k=user["token"], room=room, rp=room_pass or "")
    share_url = url_for("share", room=room, u=user["username"], k=user["token"], rp=room_pass or "")
    resp = make_response(f"""<!doctype html><meta charset=utf-8><title>Hazır</title>
<p>Kayıt OK. Linkler:</p>
<ul>
  <li><a href="{modern_url}">Modern oda</a></li>
  <li><a href="{lite_url}">Lite (Nokia) oda</a></li>
  <li><a href="{share_url}">Tek tık paylaşım</a></li>
</ul>
""")
    resp.set_cookie("chat_user", user["username"], max_age=31536000, httponly=True, samesite="Lax")
    resp.set_cookie("chat_token", user["token"], max_age=31536000, httponly=True, samesite="Lax")
    if room_pass:
        resp.set_cookie(f"room_{room}", sha256(room_pass), max_age=31536000, httponly=True, samesite="Lax")
    return resp

@app.route("/share/<room>")
def share(room):
    u = request.args.get("u","")
    k = request.args.get("k","")
    rp = request.args.get("rp","")
    modern = url_for("room_modern", room=room, _external=False)
    lite = url_for("lite", u=u, k=k, room=room, rp=rp, _external=False)
    return f"""<!doctype html><meta charset=utf-8><title>Paylaş: {html.escape(room)}</title>
<h2>Oda: {html.escape(room)}</h2>
<p>Modern: <a href="{modern}">{modern}</a></p>
<p>Lite: <a href="{lite}">{lite}</a></p>
<p>Bu sayfayı arkadaşına gönder.</p>
"""

def room_requires_pass(name: str) -> bool:
    with db() as conn:
        cur = conn.execute("SELECT passhash FROM rooms WHERE name=?", (name,))
        row = cur.fetchone()
        return bool(row and row["passhash"])

def check_room_pass(name: str, password: str) -> bool:
    with db() as conn:
        cur = conn.execute("SELECT passhash FROM rooms WHERE name=?", (name,))
        row = cur.fetchone()
        if not row or not row["passhash"]:
            return True
        return sha256(password) == row["passhash"]

def has_room_access(room: str, provided_pass: str = "") -> bool:
    if not room_requires_pass(room):
        return True
    cookie_hash = request.cookies.get(f"room_{room}")
    if cookie_hash and provided_pass and sha256(provided_pass) == cookie_hash:
        return True
    if cookie_hash and not provided_pass:
        return True
    return check_room_pass(room, provided_pass)

@app.route("/enter/<room>", methods=["POST"]) 
def enter_room(room):
    room_pass = request.form.get("room_pass","");
    if not check_room_pass(room, room_pass):
        return "<p>Yanlış şifre.</p>", 403
    resp = redirect(url_for("room_modern", room=room))
    if room_pass:
        resp.set_cookie(f"room_{room}", sha256(room_pass), max_age=31536000, httponly=True, samesite="Lax")
    return resp

@app.route("/room/<room>")
def room_modern(room):
    username = request.cookies.get("chat_user") or "misafir"
    token = request.cookies.get("chat_token") or ""    
    if room_requires_pass(room) and not has_room_access(room):
        return f"""<!doctype html><meta charset=utf-8><title>Şifre gerekli</title>
<h3>Oda şifreli</h3>
<form method=post action="{url_for('enter_room', room=room)}">
  <input name=room_pass type=password placeholder="Oda şifresi" required>
  <button type=submit>Giriş</button>
</form>
"""
    msgs = recent_messages(room, limit=100)
    def render_item(m):
        if m["type"]=="image":
            return f"<div><b>{html.escape(m['username'])}</b>: <br><img src='/media/{html.escape(m['media'])}' style='max-width:100%;border-radius:8px'><br><small>({m['created_at']})</small></div>"
        if m["type"]=="video":
            return f"<div><b>{html.escape(m['username'])}</b>: <br><video src='/media/{html.escape(m['media'])}' controls style='max-width:100%'></video><br><small>({m['created_at']})</small></div>"
        return f"<div><b>{html.escape(m['username'])}</b>: {m['msg']} <small>({m['created_at']})</small></div>"
    items = "\n".join(render_item(m) for m in msgs)
    return f"""<!doctype html><html lang=tr><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>
<title>{SITE_NAME} • {html.escape(room)}</title>
<meta http-equiv="refresh" content="12">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial,sans-serif;margin:0;background:#090f1a;color:#e8ecf1;}}
.header{{position:sticky;top:0;background:#0e1628;border-bottom:1px solid #1c2a4a;padding:12px 16px;}}
.wrap{{max-width:760px;margin:0 auto;padding:16px;}}
.msgs{{display:flex;flex-direction:column;gap:10px;margin:12px 0 120px;}}
.card{{background:#0e1628;border:1px solid #1c2a4a;border-radius:14px;padding:12px;}}
form.send{{position:fixed;bottom:0;left:0;right:0;background:#0e1628;border-top:1px solid #1c2a4a;padding:8px 12px;}}
input[type=text],input[type=file]{{width:100%;padding:10px;border-radius:10px;border:1px solid #30416d;background:#0a1222;color:#e8ecf1;margin-top:6px}}
button{{margin-top:8px;width:100%;padding:12px;border-radius:10px;border:1px solid #30416d;background:#13224a;color:#e8ecf1}}
small{{opacity:.8}}
</style>
<div class=header><div class=wrap><b>Oda:</b> {html.escape(room)} • <b>Kullanıcı:</b> {html.escape(username)}</div></div>
<div class=wrap><div class="msgs">{items or '<div class=card>Henüz mesaj yok.</div>'}</div></div>

<form class=send action="{url_for('send')}" method=post enctype="multipart/form-data">
  <input type=hidden name=room value="{html.escape(room)}">
  <input type=hidden name=username value="{html.escape(username)}">
  <input type=hidden name=token value="{html.escape(token)}">
  <input type=text name=msg placeholder="Mesaj yaz..." maxlength=500>
  <input type=file name=file>
  <button type=submit>Gönder</button>
  <p><small>Foto/Video limiti: {app.config['MAX_CONTENT_LENGTH']//(1024*1024)}MB</small></p>
</form>
"""

@app.route("/upload", methods=["POST"]) 
def upload():
    room = (request.form.get("room") or DEFAULT_ROOM).strip()[:32]
    username = request.form.get("username") or "misafir"
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect(url_for("room_modern", room=room))
    ext = f.filename.rsplit(".",1)[-1].lower() if "." in f.filename else ""
    if ext not in (ALLOWED_IMG | ALLOWED_VID):
        return "<p>İzin verilmeyen dosya türü.</p>", 400
    from uuid import uuid4
    filename = secure_filename(f"{uuid4().hex}_{f.filename}")
    path = os.path.join(UPLOAD_DIR, filename)
    f.save(path)
    mtype = "image" if ext in ALLOWED_IMG else "video"
    add_message(room, username, mtype=mtype, media=filename)
    return redirect(url_for("room_modern", room=room), code=303)

@app.route("/send", methods=["POST"]) 
def send():
    room = request.form.get("room") or DEFAULT_ROOM
    username = request.form.get("username") or "misafir"
    if "file" in request.files and request.files["file"].filename:
        return upload()
    add_message(room, username, request.form.get("msg",""))
    return redirect(url_for("room_modern", room=room), code=303)

# Lite
XHTML_DOCTYPE = ('<!DOCTYPE html PUBLIC "-//WAPFORUM//DTD XHTML Mobile 1.2//EN" '
                 '"http://www.openmobilealliance.org/tech/DTD/xhtml-mobile12.dtd">')

def xhtml_page(title: str, body: str, refresh_seconds: int = 0) -> str:
    refresh = ('<meta http-equiv="refresh" content="%d" />' % int(refresh_seconds)) if refresh_seconds>0 else ""
    return ("%s\n<html xmlns=\"http://www.w3.org/1999/xhtml\" xml:lang=\"tr\">\n<head>\n"
            "  <meta http-equiv=\"Content-Type\" content=\"application/xhtml+xml; charset=utf-8\" />\n"
            "  <title>%s</title>\n%s\n"
            "  <style type=\"text/css\">body{font-family:Tahoma,Arial,sans-serif;font-size:14px;margin:6px} fieldset{border:1px solid #888;padding:6px} input{width:98%%}</style>\n"
            "</head>\n<body>\n%s\n</body></html>" % (XHTML_DOCTYPE, html.escape(title), refresh, body))

def xhtml_response(content: str, status: int = 200):
    resp = make_response(content, status)
    resp.headers["Content-Type"] = "application/xhtml+xml; charset=utf-8"
    return resp

@app.route("/lite", methods=["GET","POST"]) 
def lite():
    u = (request.values.get("u") or "").strip()[:20]
    k = (request.values.get("k") or "").strip()[:64]
    room = (request.values.get("room") or DEFAULT_ROOM).strip()[:32]
    rp = request.values.get("rp", "")
    if room_requires_pass(room) and not check_room_pass(room, rp):
        body = "<h3>Oda şifreli</h3><p>rp parametresiyle doğru şifreyi ekleyin.</p>"
        return xhtml_response(xhtml_page("Şifre gerekli", body))
    if request.method == "POST":
        msg = request.form.get("msg","");
        add_message(room, u or "misafir", msg)
        return redirect(url_for("lite", u=u, k=k, room=room, rp=rp), code=303)
    msgs = recent_messages(room, limit=60)
    items = "".join([
        "<p><b>%s</b>: %s <small>(%s)</small></p>" % (
            html.escape(m["username"]),
            ("[Resim/Video] /media/%s" % html.escape(m["media"])) if m["type"]!="text" else m["msg"],
            m["created_at"]
        ) for m in msgs
    ])
    body = """<h1>%s</h1>
<p><b>Oda:</b> %s | <b>Kullanıcı:</b> %s</p>
<fieldset><legend>Mesajlar</legend>%s</fieldset>
<form method="post" action="%s">
  <input type="hidden" name="u" value="%s" />
  <input type="hidden" name="k" value="%s" />
  <input type="hidden" name="room" value="%s" />
  <input type="hidden" name="rp" value="%s" />
  <p><input type="text" name="msg" maxlength="500" /></p>
  <p><input type="submit" value="Gönder" /></p>
</form>
<p><small>Medya Lite'ta link olarak görünür. Sayfa 20 sn'de bir yenilenir.</small></p>
""" % (SITE_NAME, html.escape(room), html.escape(u), items or "<p>Henüz mesaj yok.</p>",
       url_for("lite"), html.escape(u), html.escape(k), html.escape(room), html.escape(rp))
    return xhtml_response(xhtml_page(f"{SITE_NAME} - {room}", body, refresh_seconds=20))

@app.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/health")
def health():
    return {"ok": True, "time": now_iso()}

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
