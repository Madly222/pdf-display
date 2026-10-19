import mimetypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PD_DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("PD_PDFJS_DIR", str(ROOT / "pdfjs"))
os.environ.setdefault("PD_PUBLIC_URL", "http://localhost:8000")
sys.path.insert(0, str(ROOT / "app"))

from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import core
import main

mimetypes.add_type("text/javascript", ".mjs")


def create_app():
    for sub in ("db", "files", "tmp"):
        (core.DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    app = main.app

    @app.middleware("http")
    async def accel_redirect(request: Request, call_next):
        response = await call_next(request)
        target = response.headers.get("x-accel-redirect")
        if target and target.startswith("/_files/"):
            path = core.FILES_DIR / target.removeprefix("/_files/")
            return FileResponse(path, media_type=response.headers.get("content-type"), headers={
                "Content-Disposition": response.headers.get("content-disposition", "inline"),
                "Cache-Control": "private, no-cache",
            })
        return response

    app.mount("/admin", StaticFiles(directory=ROOT / "admin", html=True), name="admin")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    app.mount("/pdfjs", StaticFiles(directory=core.PDFJS_DIR), name="pdfjs")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("PD_PORT", "8000")))
