import hashlib
import hmac
import html
import os
import re
import secrets
import shutil
import sqlite3
import string
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from core import (FILES_DIR, MAX_FILE_BYTES, PDFJS_DIR, PUBLIC_HOST, PUBLIC_URL, connect,
                  hash_password, hash_token, init_db, now, transaction, verify_password)
import render
import texts

GB = 1024**3
SESSION_TTL = 30 * 24 * 3600
COOKIE = "pd_session"
ID_ALPHABET = string.ascii_lowercase + string.digits
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")
DUMMY_HASH = hash_password(secrets.token_hex(16))


@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="PDF Display", version="1.0", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()



def current_user(request: Request, db: sqlite3.Connection):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return db.execute(
        "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ?", (hash_token(token), now())).fetchone()


def require_user(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        raise HTTPException(401, "Нужно войти")
    return user


class LoginIn(BaseModel):
    username: str
    password: str


_login_fails: dict[str, list[float]] = {}


@app.post("/api/login", tags=["auth"])
def login(body: LoginIn, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    t = time.time()
    fails = [x for x in _login_fails.get(ip, []) if t - x < 600]
    if len(fails) >= 10:
        raise HTTPException(429, "Слишком много попыток, подождите 10 минут")
    row = db.execute("SELECT id, password_hash FROM users WHERE username = ?", (body.username,)).fetchone()
    ok = verify_password(body.password, row["password_hash"] if row else DUMMY_HASH)
    if not (row and ok):
        _login_fails[ip] = fails + [t]
        raise HTTPException(401, "Неверный логин или пароль")
    _login_fails.pop(ip, None)
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    db.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
               (hash_token(token), row["id"], now() + SESSION_TTL))
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, secure=True, samesite="lax", path="/")
    return {"username": body.username}


@app.post("/api/logout", tags=["auth"])
def logout(request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me", tags=["auth"])
def me(user=Depends(require_user)):
    return {"username": user["username"]}


MIN_PASSWORD_LEN = 10


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/me/password", tags=["auth"])
def change_password(body: PasswordChange, request: Request, user=Depends(require_user), db=Depends(get_db)):
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(400, "Текущий пароль неверен")
    new = body.new_password
    if len(new) < MIN_PASSWORD_LEN:
        raise HTTPException(422, f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов")
    if len(new) > 200:
        raise HTTPException(422, "Пароль слишком длинный")
    if new == body.current_password:
        raise HTTPException(422, "Новый пароль совпадает с текущим")
    if user["username"].lower() in new.lower():
        raise HTTPException(422, "Пароль не должен содержать логин")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user["id"]))
    db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
               (user["id"], hash_token(request.cookies.get(COOKIE, ""))))
    return {"ok": True}


USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")


class UsernameChange(BaseModel):
    current_password: str
    new_username: str


@app.post("/api/me/username", tags=["auth"])
def change_username(body: UsernameChange, user=Depends(require_user), db=Depends(get_db)):
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(400, "Текущий пароль неверен")
    new = body.new_username.strip()
    if not USERNAME_RE.match(new):
        raise HTTPException(422, "Логин: от 3 до 64 символов, латинские буквы, цифры и . _ @ -")
    if new == user["username"]:
        raise HTTPException(422, "Это и так ваш текущий логин")
    try:
        db.execute("UPDATE users SET username = ? WHERE id = ?", (new, user["id"]))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Такой логин уже занят")
    return {"username": new}



def normalize_domain(raw: str) -> str:
    d = raw.strip().lower()
    d = re.sub(r"^[a-z][a-z0-9+.-]*://", "", d)
    d = re.split(r"[/?#]", d, maxsplit=1)[0].split(":")[0].rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        raise HTTPException(422, f"Неверный домен: {raw}")
    if not DOMAIN_RE.match(d):
        raise HTTPException(422, f"Неверный домен: {raw}")
    return d


def display_domain(d: str) -> str:
    try:
        return d.encode("ascii").decode("idna")
    except UnicodeError:
        return d


def frame_ancestors(domains: list[str]) -> str:
    sources = ["'self'"]
    for d in domains:
        for host in (d, "www." + d):
            sources += [f"https://{host}", f"http://{host}"]
    return " ".join(sources)


def folder_domains(db, folder_id: int) -> list[str]:
    return [r[0] for r in db.execute(
        "SELECT domain FROM folder_domains WHERE folder_id = ? ORDER BY domain", (folder_id,))]


def folder_used(db, folder_id: int) -> int:
    return db.execute("SELECT COALESCE(SUM(size), 0) FROM files WHERE folder_id = ?", (folder_id,)).fetchone()[0]


def folder_out(db, row) -> dict:
    count = db.execute("SELECT COUNT(*) FROM files WHERE folder_id = ?", (row["id"],)).fetchone()[0]
    quota = row["quota_bytes"]
    return {
        "id": row["id"],
        "name": row["name"],
        "domains": [display_domain(d) for d in folder_domains(db, row["id"])],
        "allow_direct": bool(row["allow_direct"]),
        "quota_bytes": quota,
        "quota_gb": round(quota / GB, 3) if quota else None,
        "used_bytes": folder_used(db, row["id"]),
        "file_count": count,
        "created_at": row["created_at"],
    }


def get_folder(db, folder_id: int):
    row = db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Папка не найдена")
    return row


def set_domains(db, folder_id: int, domains: list[str]) -> None:
    db.execute("DELETE FROM folder_domains WHERE folder_id = ?", (folder_id,))
    for d in dict.fromkeys(normalize_domain(x) for x in domains if x.strip()):
        db.execute("INSERT INTO folder_domains (folder_id, domain) VALUES (?, ?)", (folder_id, d))


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Обычно домен сайта клиента")
    domains: list[str] | None = Field(None, description="Сайты, где можно показывать файлы. "
                                      "Не указано — берётся из имени папки. www-вариант добавляется сам.")
    quota_gb: float | None = Field(None, gt=0, description="Лимит места, ГБ. Пусто — без лимита")
    allow_direct: bool = Field(False, description="Разрешить открывать ссылку напрямую, не в iframe")


class FolderPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    domains: list[str] | None = None
    quota_gb: float | None = Field(None, gt=0, description="null — снять лимит")
    allow_direct: bool | None = None


@app.get("/api/folders", tags=["folders"])
def list_folders(user=Depends(require_user), db=Depends(get_db)):
    return [folder_out(db, r) for r in db.execute("SELECT * FROM folders ORDER BY name")]


@app.post("/api/folders", status_code=201, tags=["folders"])
def create_folder(body: FolderIn, user=Depends(require_user), db=Depends(get_db)):
    name = body.name.strip()
    if body.domains is not None:
        domains = body.domains
    else:
        try:
            domains = [normalize_domain(name)]
        except HTTPException:
            domains = []
    quota = int(body.quota_gb * GB) if body.quota_gb else None
    try:
        with transaction(db):
            cur = db.execute("INSERT INTO folders (name, quota_bytes, allow_direct, created_at) VALUES (?, ?, ?, ?)",
                             (name, quota, int(body.allow_direct), now()))
            set_domains(db, cur.lastrowid, domains)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Папка с таким именем уже есть")
    return folder_out(db, get_folder(db, cur.lastrowid))


@app.get("/api/folders/{folder_id}", tags=["folders"])
def read_folder(folder_id: int, user=Depends(require_user), db=Depends(get_db)):
    return folder_out(db, get_folder(db, folder_id))


@app.patch("/api/folders/{folder_id}", tags=["folders"])
def update_folder(folder_id: int, body: FolderPatch, user=Depends(require_user), db=Depends(get_db)):
    get_folder(db, folder_id)
    fields = body.model_fields_set
    try:
        with transaction(db):
            if "name" in fields and body.name:
                db.execute("UPDATE folders SET name = ? WHERE id = ?", (body.name.strip(), folder_id))
            if "quota_gb" in fields:
                quota = int(body.quota_gb * GB) if body.quota_gb else None
                db.execute("UPDATE folders SET quota_bytes = ? WHERE id = ?", (quota, folder_id))
            if "allow_direct" in fields and body.allow_direct is not None:
                db.execute("UPDATE folders SET allow_direct = ? WHERE id = ?", (int(body.allow_direct), folder_id))
            if "domains" in fields and body.domains is not None:
                set_domains(db, folder_id, body.domains)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Папка с таким именем уже есть")
    return folder_out(db, get_folder(db, folder_id))


@app.delete("/api/folders/{folder_id}", tags=["folders"])
def delete_folder(folder_id: int, force: bool = Query(False, description="Удалить вместе с файлами"),
                  user=Depends(require_user), db=Depends(get_db)):
    get_folder(db, folder_id)
    with transaction(db):
        count = db.execute("SELECT COUNT(*) FROM files WHERE folder_id = ?", (folder_id,)).fetchone()[0]
        if count and not force:
            raise HTTPException(409, f"В папке {count} файлов. Удалите их или передайте force=true")
        db.execute("DELETE FROM files WHERE folder_id = ?", (folder_id,))
        db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    shutil.rmtree(FILES_DIR / str(folder_id), ignore_errors=True)
    return {"ok": True}



def file_path(folder_id: int, file_id: str) -> Path:
    return FILES_DIR / str(folder_id) / f"{file_id}.pdf"


def file_out(row) -> dict:
    view_url = f"{PUBLIC_URL}/v/{row['id']}"
    return {
        "id": row["id"],
        "folder_id": row["folder_id"],
        "name": row["name"],
        "size": row["size"],
        "sha256": row["sha256"],
        "mime": row["mime"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "view_url": view_url,
        "embed_html": f'<iframe src="{view_url}" width="100%" height="700" style="border:0"></iframe>',
    }


def get_file(db, file_id: str):
    row = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Файл не найден")
    return row


def clean_name(raw: str) -> str:
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:255] or "document.pdf"


def fmt_size(n: int) -> str:
    return f"{n / GB:.2f} ГБ" if n >= GB / 10 else f"{n / 1024 / 1024:.1f} МБ"


def check_quota(db, folder, extra: int, minus: int = 0) -> None:
    quota = folder["quota_bytes"]
    if quota is None:
        return
    used = folder_used(db, folder["id"])
    if used - minus + extra > quota:
        raise HTTPException(413, f"Не хватает места в папке: занято {fmt_size(used)} из {fmt_size(quota)}, "
                                 f"файл {fmt_size(extra)}")


def stage_upload(upload: UploadFile, folder_id: int) -> tuple[Path, int, str]:
    head = upload.file.read(1024)
    if b"%PDF-" not in head:
        raise HTTPException(415, "Это не PDF-файл")
    folder_dir = FILES_DIR / str(folder_id)
    folder_dir.mkdir(exist_ok=True)
    tmp = folder_dir / f".upload-{secrets.token_hex(8)}"
    digest = hashlib.sha256()
    size = 0
    try:
        with open(tmp, "wb") as out:
            chunk = head
            while chunk:
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise HTTPException(413, f"Файл больше {fmt_size(MAX_FILE_BYTES)}")
                digest.update(chunk)
                out.write(chunk)
                chunk = upload.file.read(1024 * 1024)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, size, digest.hexdigest()


def new_file_id(db) -> str:
    while True:
        file_id = "".join(secrets.choice(ID_ALPHABET) for _ in range(10))
        if db.execute("SELECT 1 FROM files WHERE id = ?", (file_id,)).fetchone() is None:
            return file_id


@app.get("/api/files", tags=["files"])
def list_files(folder_id: int | None = None, q: str | None = Query(None, description="Поиск по имени"),
               user=Depends(require_user), db=Depends(get_db)):
    sql, args = "SELECT * FROM files WHERE 1 = 1", []
    if folder_id is not None:
        sql += " AND folder_id = ?"
        args.append(folder_id)
    if q:
        sql += " AND name LIKE ? ESCAPE '\\'"
        args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    return [file_out(r) for r in db.execute(sql + " ORDER BY created_at DESC", args)]


@app.post("/api/folders/{folder_id}/files", status_code=201, tags=["files"])
def upload_file(folder_id: int, file: UploadFile = File(...),
                name: str | None = Form(None, description="Имя для показа; по умолчанию имя файла"),
                user=Depends(require_user), db=Depends(get_db)):
    folder = get_folder(db, folder_id)
    tmp, size, sha = stage_upload(file, folder_id)
    try:
        with transaction(db):
            check_quota(db, folder, size)
            file_id = new_file_id(db)
            t = now()
            db.execute("INSERT INTO files (id, folder_id, name, size, sha256, mime, created_at, updated_at) "
                       "VALUES (?, ?, ?, ?, ?, 'application/pdf', ?, ?)",
                       (file_id, folder_id, clean_name(name or file.filename or ""), size, sha, t, t))
            os.replace(tmp, file_path(folder_id, file_id))
    finally:
        tmp.unlink(missing_ok=True)
    return file_out(get_file(db, file_id))


@app.get("/api/files/{file_id}", tags=["files"])
def read_file(file_id: str, user=Depends(require_user), db=Depends(get_db)):
    return file_out(get_file(db, file_id))


@app.put("/api/files/{file_id}", tags=["files"])
def replace_file(file_id: str, file: UploadFile = File(...),
                 name: str | None = Form(None, description="Новое имя; по умолчанию прежнее"),
                 user=Depends(require_user), db=Depends(get_db)):
    row = get_file(db, file_id)
    folder = get_folder(db, row["folder_id"])
    tmp, size, sha = stage_upload(file, folder["id"])
    try:
        with transaction(db):
            check_quota(db, folder, size, minus=row["size"])
            db.execute("UPDATE files SET size = ?, sha256 = ?, name = ?, updated_at = ? WHERE id = ?",
                       (size, sha, clean_name(name) if name else row["name"], now(), file_id))
            os.replace(tmp, file_path(folder["id"], file_id))
    finally:
        tmp.unlink(missing_ok=True)
    return file_out(get_file(db, file_id))


class FilePatch(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@app.patch("/api/files/{file_id}", tags=["files"])
def rename_file(file_id: str, body: FilePatch, user=Depends(require_user), db=Depends(get_db)):
    get_file(db, file_id)
    db.execute("UPDATE files SET name = ?, updated_at = ? WHERE id = ?", (clean_name(body.name), now(), file_id))
    return file_out(get_file(db, file_id))


@app.delete("/api/files/{file_id}", tags=["files"])
def delete_file(file_id: str, user=Depends(require_user), db=Depends(get_db)):
    row = get_file(db, file_id)
    db.execute("DELETE FROM files WHERE id = ?", (file_id,))
    file_path(row["folder_id"], file_id).unlink(missing_ok=True)
    return {"ok": True}



def message_page(status: int, text: str, lang: str = "ru") -> HTMLResponse:
    body = (f'<!doctype html><html lang="{lang}"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{status}</title>'
            f'<body style="margin:0;display:grid;place-items:center;min-height:100vh;'
            f'font:16px system-ui,sans-serif;color:#555;background:#f4f4f4">'
            f'<p style="padding:16px;text-align:center">{html.escape(text)}</p></body></html>')
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


def localized_page(status: int, key: str, lang: str) -> HTMLResponse:
    return message_page(status, texts.text(key, lang), lang)


def browser_lang(request: Request) -> str:
    return texts.lang_from_header(request.headers.get("accept-language"))


_viewer_template: str | None = None


def viewer_template() -> str:
    global _viewer_template
    if _viewer_template is None:
        page = (PDFJS_DIR / "web" / "viewer.html").read_text(encoding="utf-8")
        _viewer_template = page.replace("<head>", '<head>\n<base href="/pdfjs/web/">\n'
                                        '<script src="/static/viewer-setup.js"></script>\n'
                                        '<link rel="stylesheet" href="/static/viewer-setup.css">', 1)
    return _viewer_template


@app.get("/v/{file_id}", include_in_schema=False)
def view(file_id: str, request: Request, db=Depends(get_db)):
    lang = browser_lang(request)
    if "file" in request.query_params:
        return localized_page(400, "bad_link", lang)
    row = db.execute("SELECT f.id, f.folder_id, d.allow_direct FROM files f JOIN folders d ON d.id = f.folder_id "
                     "WHERE f.id = ?", (file_id,)).fetchone()
    if row is None:
        return localized_page(404, "not_found", lang)
    if (not row["allow_direct"] and request.headers.get("sec-fetch-dest") == "document"
            and current_user(request, db) is None):
        return localized_page(403, "only_on_site", lang)
    return HTMLResponse(viewer_template(), headers={
        "Content-Security-Policy": f"frame-ancestors {frame_ancestors(folder_domains(db, row['folder_id']))}",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex",
    })


@app.get("/f/{file_id}", include_in_schema=False)
def file_content(file_id: str, request: Request, db=Depends(get_db)):
    row = db.execute("SELECT id, folder_id, name FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise HTTPException(404)
    if current_user(request, db) is None:
        site = request.headers.get("sec-fetch-site")
        if site and site != "same-origin":
            raise HTTPException(403)
        referer = request.headers.get("referer")
        if referer:
            ref = urlsplit(referer)
            if ref.netloc != PUBLIC_HOST or ref.path != f"/v/{file_id}":
                raise HTTPException(403)
    return Response(headers={
        "X-Accel-Redirect": f"/_files/{row['folder_id']}/{file_id}.pdf",
        "Content-Type": "application/pdf",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(row['name'])}",
        "Cache-Control": "private, no-cache",
    })



def _render_headers(extra_csp: str = "") -> dict:
    ancestors = " ".join(["'self'", *render.ODOO_ORIGINS])
    return {
        "Content-Security-Policy": f"frame-ancestors {ancestors}{extra_csp}",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex",
    }


@app.post("/api/render", tags=["render"])
async def render_create(request: Request):
    auth = request.headers.get("authorization", "")
    if not render.RENDER_TOKEN or not hmac.compare_digest(auth.encode(), f"Bearer {render.RENDER_TOKEN}".encode()):
        raise HTTPException(401, "Неверный ключ")
    raw_name = request.headers.get("x-filename", "")
    try:
        raw_name = raw_name.encode("latin-1").decode("utf-8")
    except UnicodeError:
        pass
    name = clean_name(unquote(raw_name))
    if render.kind_for(name) is None:
        raise HTTPException(415, "Этот тип файлов не поддерживается")
    if int(request.headers.get("content-length") or 0) > render.MAX_INPUT:
        raise HTTPException(413, "Файл слишком большой для просмотра")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > render.MAX_INPUT:
            raise HTTPException(413, "Файл слишком большой для просмотра")
    lang = texts.normalize_lang(request.headers.get("x-lang")) or "en"
    ticket = render.create_ticket(name, bytes(data), lang)
    return {"view_url": f"{PUBLIC_URL}/r/{ticket}", "expires_in": render.TTL}


@app.get("/r/{ticket}", include_in_schema=False)
def render_view(ticket: str, request: Request):
    t = render.get_ticket(ticket)
    if t is None:
        return localized_page(410, "expired", browser_lang(request))
    try:
        page = render.convert(t)
    except render.ConversionError as e:
        return localized_page(422, str(e), t.lang)
    if t.kind == "pdf":
        return HTMLResponse(viewer_template(), headers=_render_headers())
    csp = ("; default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src data:; "
           "base-uri 'none'; form-action 'none'")
    return HTMLResponse(page, headers=_render_headers(csp))


@app.get("/r/{ticket}/file", include_in_schema=False)
def render_file(ticket: str, request: Request):
    t = render.get_ticket(ticket)
    if t is None or t.kind != "pdf":
        raise HTTPException(404)
    site = request.headers.get("sec-fetch-site")
    if site and site != "same-origin":
        raise HTTPException(403)
    try:
        pdf = render.convert(t)
    except render.ConversionError as e:
        raise HTTPException(422, str(e))
    stem = t.name.rsplit(".", 1)[0] or "document"
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(stem + '.pdf')}",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/admin/")


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")
