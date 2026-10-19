import render
import texts
from conftest import PASSWORD, PDF_BYTES

import main



def test_normalize_domain():
    assert main.normalize_domain("https://WWW.Example.com/page?x=1") == "example.com"
    assert main.normalize_domain("сайт.md") == "xn--80aswg.md"
    assert main.display_domain("xn--80aswg.md") == "сайт.md"


def test_frame_ancestors_include_www_and_both_schemes():
    value = main.frame_ancestors(["example.com"])
    for source in ("'self'", "https://example.com", "http://example.com", "https://www.example.com"):
        assert source in value


def test_language_selection():
    assert texts.normalize_lang("ro_RO") == "ro"
    assert texts.normalize_lang("de_DE") is None
    assert texts.lang_from_header("de-DE,ru;q=0.8,en;q=0.5") == "ru"
    assert texts.lang_from_header(None) == "en"


def test_kind_for():
    assert render.kind_for("report.DOCX") == ("pdf", "docx")
    assert render.kind_for("table.xlsx") == ("sheet", "xlsx")
    assert render.kind_for("data.csv") == ("csv", "csv")
    assert render.kind_for("photo.png") is None


def test_sheet_page_splits_libreoffice_sheets(tmp_path):
    lo_html = ('<html><body><hr><p><center><h1>Overview</h1></center></p><hr>'
               '<A NAME="table0"><h1>Sheet 1: <em>First</em></h1></A><table><tr><td onclick="x()">1</td></tr></table><hr>'
               '<A NAME="table1"><h1>Sheet 2: <em>Second</em></h1></A><table><tr><td>2</td></tr></table>'
               '<script>alert(1)</script></body></html>')
    page = render.sheet_page("book.xlsx", lo_html, tmp_path)
    assert page.count('class="sv-sheet"') == 2
    assert ">First</button>" in page and ">Second</button>" in page
    assert "onclick" not in page and "<script>alert" not in page


def test_csv_page_escapes_and_detects_delimiter():
    page = render.csv_page("x.csv", "name;value\n<b>a</b>;1\n".encode())
    assert "<td>&lt;b&gt;a&lt;/b&gt;</td><td>1</td>" in page



def test_api_requires_login(client):
    assert client.get("/api/folders").status_code == 401


def test_wrong_password_rejected(client):
    r = client.post("/api/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401


def test_password_rules(admin):
    short = admin.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422
    with_login = admin.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "my-admin-password"})
    assert with_login.status_code == 422


def test_username_rules(admin):
    r = admin.post("/api/me/username", json={"current_password": PASSWORD, "new_username": "bad name"})
    assert r.status_code == 422



def test_upload_and_embed_protection(admin):
    folder = admin.post("/api/folders", json={"name": "client.example.com", "quota_gb": 0.001}).json()
    assert folder["domains"] == ["client.example.com"]

    not_pdf = admin.post(f"/api/folders/{folder['id']}/files", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert not_pdf.status_code == 415

    up = admin.post(f"/api/folders/{folder['id']}/files", files={"file": ("doc.pdf", PDF_BYTES, "application/pdf")})
    assert up.status_code == 201
    file_id = up.json()["id"]
    assert up.json()["embed_html"].startswith('<iframe src="https://testserver/v/')
    admin.post("/api/logout")

    framed = admin.get(f"/v/{file_id}", headers={"sec-fetch-dest": "iframe"})
    assert framed.status_code == 200
    assert "https://client.example.com" in framed.headers["content-security-policy"]

    assert admin.get(f"/v/{file_id}", headers={"sec-fetch-dest": "document"}).status_code == 403
    assert admin.get(f"/v/{file_id}?file=/f/other").status_code == 400

    own = {"sec-fetch-site": "same-origin", "referer": f"https://testserver/v/{file_id}"}
    ok = admin.get(f"/f/{file_id}", headers=own)
    assert ok.status_code == 200 and ok.headers["x-accel-redirect"].endswith(f"{file_id}.pdf")
    assert admin.get(f"/f/{file_id}", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert admin.get(f"/f/{file_id}", headers={"sec-fetch-site": "same-origin",
                                               "referer": "https://testserver/v/other"}).status_code == 403



def test_render_requires_key(client):
    r = client.post("/api/render", content=b"a,b", headers={"x-filename": "t.csv"})
    assert r.status_code == 401


def test_render_csv_ticket(client):
    headers = {"authorization": "Bearer test-render-token", "x-filename": "t%C3%A9st.csv", "x-lang": "ro_RO"}
    r = client.post("/api/render", content=b"a,b\n1,2\n", headers=headers)
    assert r.status_code == 200
    path = r.json()["view_url"].replace("https://testserver", "")
    page = client.get(path)
    assert page.status_code == 200
    assert "<td>1</td>" in page.text
    assert "https://odoo.example.com" in page.headers["content-security-policy"]


def test_expired_ticket_is_localized(client):
    r = client.get("/r/does-not-exist", headers={"accept-language": "ro"})
    assert r.status_code == 410
    assert "Linkul a expirat" in r.text
