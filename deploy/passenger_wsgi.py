"""Точка входа для Passenger на reg.ru (shared).

Скопируйте этот файл в корневую папку сайта (например, ~/www/feel.meowtreach.com/)
и поправьте FEEL_HOME, если проект лежит не в ~/feel. Сам проект, база и медиа
лежат вне публичной папки сайта.

Passenger умеет только WSGI, а FastAPI — ASGI-приложение, поэтому оно
оборачивается в a2wsgi.
"""
import os
import sys

FEEL_HOME = os.path.expanduser(os.environ.get("FEEL_HOME", "~/feel"))
INTERP = os.path.join(FEEL_HOME, "venv", "bin", "python")

# Перезапускаемся под Python из виртуального окружения проекта.
if sys.executable != INTERP and os.path.exists(INTERP):
    os.execl(INTERP, INTERP, *sys.argv)

# Проверочные файлы Let's Encrypt панель кладёт в папку сайта, а все запросы
# получает приложение — сообщаем ему, где их искать.
SITE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("ACME_DIR", os.path.join(SITE_DIR, ".well-known", "acme-challenge"))

sys.path.insert(0, FEEL_HOME)
os.chdir(FEEL_HOME)

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import app  # noqa: E402

application = ASGIMiddleware(app)
