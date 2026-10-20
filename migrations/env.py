from alembic import context

from app import models  # noqa: F401  — регистрирует таблицы в Base.metadata
from app import db as app_db
from app.config import settings

config = context.config
target_metadata = app_db.Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    if url == settings.database_url:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = app_db.make_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
