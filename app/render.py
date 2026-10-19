"""Просмотр файлов из Odoo: офисные документы конвертируются на лету, ничего не пишется на диск.

Odoo присылает файл (POST /api/render) и получает одноразовую ссылку /r/<ticket>, живущую TTL секунд.
Исходник и результат конвертации лежат только в оперативной памяти; LibreOffice работает в /dev/shm
(tmpfs), рабочий каталог удаляется сразу после конвертации.
"""
import base64
import csv
import hashlib
import html
import io
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

RENDER_TOKEN = os.environ.get("PD_RENDER_TOKEN", "")
# Сайты (Odoo), которым можно встраивать просмотр в iframe.
ODOO_ORIGINS = os.environ.get("PD_ODOO_ORIGINS", "").split()
TTL = 300
MAX_INPUT = 100 * 1024 * 1024
MAX_CACHE = 300 * 1024 * 1024
CONVERT_TIMEOUT = 120
WORK_ROOT = Path("/dev/shm/pdfdisplay")
LO_PROFILE = WORK_ROOT / "lo-profile"

# Что показываем как PDF (через LibreOffice) и что как таблицу.
PDF_EXT = {"doc", "docx", "docm", "dot", "dotx", "odt", "ott", "rtf", "wpd", "wps",
           "ppt", "pptx", "pptm", "pps", "ppsx", "pot", "potx", "odp", "otp", "odg", "vsd", "vsdx"}
SHEET_EXT = {"xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "ods", "ots"}
CSV_EXT = {"csv"}


class ConversionError(Exception):
    """Текст исключения — ключ сообщения из texts.MESSAGES."""


@dataclass
class Ticket:
    name: str
    kind: str  # "pdf" | "sheet" | "csv"
    ext: str
    data: bytes
    sha: str
    expires: float
    lang: str = "en"


_tickets: dict[str, Ticket] = {}
_results: dict[tuple[str, str], tuple[bytes, float]] = {}
_lock = threading.Lock()
# Один LibreOffice за раз: на сервере одно ядро, параллельные конвертации только мешают друг другу.
_convert_lock = threading.Lock()


def kind_for(filename: str) -> tuple[str, str] | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in PDF_EXT:
        return "pdf", ext
    if ext in SHEET_EXT:
        return "sheet", ext
    if ext in CSV_EXT:
        return "csv", ext
    return None


def _purge() -> None:
    now = time.time()
    with _lock:
        for key in [k for k, t in _tickets.items() if t.expires < now]:
            del _tickets[key]
        for key in [k for k, (_, exp) in _results.items() if exp < now]:
            del _results[key]
        # Если кэш разросся, выкидываем самые старые результаты.
        total = sum(len(v) for v, _ in _results.values())
        for key, (value, _) in sorted(_results.items(), key=lambda kv: kv[1][1]):
            if total <= MAX_CACHE:
                break
            total -= len(value)
            del _results[key]


def create_ticket(name: str, data: bytes, lang: str = "en") -> str:
    kind = kind_for(name)
    if kind is None:
        raise ValueError("unsupported")
    _purge()
    ticket = secrets.token_urlsafe(24)
    with _lock:
        _tickets[ticket] = Ticket(name=name, kind=kind[0], ext=kind[1], data=data,
                                  sha=hashlib.sha256(data).hexdigest(), expires=time.time() + TTL,
                                  lang=lang)
    return ticket


def get_ticket(ticket: str) -> Ticket | None:
    _purge()
    with _lock:
        return _tickets.get(ticket)


def convert(ticket: Ticket) -> bytes:
    """PDF для документов, готовая HTML-страница для таблиц. Результат кэшируется в памяти на TTL."""
    key = (ticket.sha, ticket.kind)
    with _lock:
        cached = _results.get(key)
    if cached:
        return cached[0]
    if ticket.kind == "csv":
        out = csv_page(ticket.name, ticket.data).encode()
    else:
        with _convert_lock:
            with _lock:
                cached = _results.get(key)
            if cached:
                return cached[0]
            out = _libreoffice(ticket)
    with _lock:
        _results[key] = (out, time.time() + TTL)
    return out


def _libreoffice(ticket: Ticket) -> bytes:
    WORK_ROOT.mkdir(mode=0o700, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=WORK_ROOT))
    try:
        src = work / f"input.{ticket.ext}"
        src.write_bytes(ticket.data)
        target = "pdf" if ticket.kind == "pdf" else "html"
        out_dir = work / "out"
        cmd = ["soffice", f"-env:UserInstallation=file://{LO_PROFILE}", "--headless", "--norestore",
               "--nolockcheck", "--nodefault", "--convert-to", target, "--outdir", str(out_dir), str(src)]
        proc = subprocess.Popen(cmd, env={**os.environ, "HOME": str(work)}, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.wait(timeout=CONVERT_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise ConversionError("timeout")
        result = out_dir / f"input.{target}"
        if not result.exists():
            raise ConversionError("broken")
        if target == "pdf":
            return result.read_bytes()
        return sheet_page(ticket.name, result.read_text(encoding="utf-8", errors="replace"), out_dir).encode()
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------- таблицы ----------

_SHEET_SPLIT = re.compile(r'<A NAME="table\d+">\s*<h1>Sheet \d+: <em>(.*?)</em></h1>\s*</A>', re.S | re.I)
_IMG_SRC = re.compile(r'src="([^"/\\]+\.(png|jpe?g|gif|svg))"', re.I)
_DROP_ATTR = re.compile(r'\s(?:data-sheets-[a-z-]+|on[a-z]+)="[^"]*"', re.I)
_SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.I)
_IMG_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "svg": "image/svg+xml"}


def _clean(fragment: str, out_dir: Path) -> str:
    fragment = _SCRIPT.sub("", fragment)
    fragment = _DROP_ATTR.sub("", fragment)

    def inline(m):
        path = out_dir / m.group(1)
        if not path.is_file():
            return 'src=""'
        data = base64.b64encode(path.read_bytes()).decode()
        return f'src="data:{_IMG_MIME[m.group(2).lower()]};base64,{data}"'

    return _IMG_SRC.sub(inline, fragment)


def sheet_page(title: str, lo_html: str, out_dir: Path) -> str:
    body = re.split(r"<body[^>]*>", lo_html, maxsplit=1, flags=re.I)[-1]
    body = re.split(r"</body>", body, maxsplit=1, flags=re.I)[0]
    parts = _SHEET_SPLIT.split(body)
    sheets = []
    if len(parts) > 1:
        # parts: [обзор, имя1, содержимое1, имя2, содержимое2, ...]; имена LibreOffice уже экранировал.
        for i in range(1, len(parts), 2):
            content = re.sub(r"(\s*<hr>\s*)+$", "", parts[i + 1].strip(), flags=re.I)
            sheets.append((parts[i], content))
    else:
        sheets.append((html.escape(title), body))
    return _page(title, [(name, _clean(content, out_dir)) for name, content in sheets])


def csv_page(title: str, data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))[:20000]
    out = ['<table cellspacing="0" border="0">']
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>")
    out.append("</table>")
    return _page(title, [(html.escape(title), "\n".join(out))])


def _page(title: str, sheets: list[tuple[str, str]]) -> str:
    sections = "\n".join(f'<section class="sv-sheet" data-index="{i}"{"" if i == 0 else " hidden"}>{content}</section>'
                         for i, (_, content) in enumerate(sheets))
    tabs = "".join(f'<button type="button" class="sv-tab{" active" if i == 0 else ""}" data-index="{i}">{name}</button>'
                   for i, (name, _) in enumerate(sheets))
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><base target="_blank">'
            f'<link rel="stylesheet" href="/static/sheet-viewer.css"></head>'
            f'<body{" class=single" if len(sheets) == 1 else ""}><main class="sv-sheets">{sections}</main>'
            f'<nav class="sv-tabs">{tabs}</nav>'
            f'<script src="/static/sheet-viewer.js"></script></body></html>')
