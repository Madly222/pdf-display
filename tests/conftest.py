import os
import sys
import tempfile
from pathlib import Path

import pytest

_DATA = Path(tempfile.mkdtemp(prefix="pdfdisplay-test-"))
(_DATA / "db").mkdir()
(_DATA / "files").mkdir()
(_DATA / "pdfjs" / "web").mkdir(parents=True)
(_DATA / "pdfjs" / "web" / "viewer.html").write_text("<html><head><title>viewer</title></head><body></body></html>")
os.environ.update({
    "PD_DATA_DIR": str(_DATA),
    "PD_PDFJS_DIR": str(_DATA / "pdfjs"),
    "PD_PUBLIC_URL": "https://testserver",
    "PD_RENDER_TOKEN": "test-render-token",
    "PD_ODOO_ORIGINS": "https://odoo.example.com",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import core
import main
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture(scope="session")
def client():
    core.init_db()
    db = core.connect()
    db.execute("INSERT OR REPLACE INTO users (id, username, password_hash, created_at) VALUES (1, 'admin', ?, 0)",
               (core.hash_password(PASSWORD),))
    db.close()
    with TestClient(main.app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/api/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200
    yield client
    client.post("/api/logout")
