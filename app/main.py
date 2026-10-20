"""FastAPI-приложение: API и раздача PWA из папки static."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth, journal, prefs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("feel")

if not settings.secret_key:
    raise RuntimeError("SECRET_KEY не задан: скопируйте .env.example в .env и заполните его")

app = FastAPI(title="feel", docs_url=None, redoc_url=None, openapi_url=None)

CSP = ("default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
       "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'self'")

NO_CACHE = {"/", "/index.html", "/sw.js", "/manifest.webmanifest"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if settings.force_https and request.headers.get("x-forwarded-proto", "https") == "http":
        return RedirectResponse(str(request.url.replace(scheme="https")), status_code=301)
    response = await call_next(request)
    h = response.headers
    h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "same-origin"
    h["X-Frame-Options"] = "DENY"
    h["Content-Security-Policy"] = CSP
    h["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    path = request.url.path
    if path.startswith("/api/"):
        h["Cache-Control"] = "no-store"
    elif path in NO_CACHE:
        h["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # В журнал — только метод, путь и тип ошибки: тела запросов (заметки) туда не попадают.
    log.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path,
              exc_info=(type(exc), exc, None))
    return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)


app.include_router(auth.router)
app.include_router(journal.router)
app.include_router(prefs.router)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # Отдельно от StaticFiles, чтобы явно разрешить область действия «/».
    return FileResponse(settings.static_dir / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(settings.static_dir / "manifest.webmanifest",
                        media_type="application/manifest+json")


app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
