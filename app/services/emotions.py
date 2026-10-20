"""Справочник эмоций: загрузка data/emotions.json в таблицу emotions."""
import json
from pathlib import Path

import sqlalchemy as sa

from ..config import settings


def load_file(path: Path = None) -> dict:
    with open(path or settings.emotions_file, encoding="utf-8") as f:
        return json.load(f)


def sync_emotions(conn, path: Path = None) -> int:
    """Вставляет новые слова и обновляет существующие.

    Слова, которых больше нет в файле, не удаляются (на них могут ссылаться записи),
    а помечаются hidden. Вызывается из миграций: правка справочника = правка
    emotions.json + новая миграция, которая снова вызывает эту функцию.
    """
    data = load_file(path)
    table = sa.table(
        "emotions",
        sa.column("id", sa.String), sa.column("name", sa.String),
        sa.column("quadrant", sa.String), sa.column("energy", sa.Integer),
        sa.column("pleasantness", sa.Integer), sa.column("intensity", sa.Integer),
        sa.column("description", sa.Text), sa.column("hidden", sa.Boolean),
    )
    existing = {row[0] for row in conn.execute(sa.select(table.c.id))}
    in_file = set()
    for e in data["emotions"]:
        values = {
            "name": e["name"], "quadrant": e["quadrant"], "energy": e["energy"],
            "pleasantness": e["pleasantness"], "intensity": e["intensity"],
            "description": e.get("description", ""), "hidden": False,
        }
        in_file.add(e["id"])
        if e["id"] in existing:
            conn.execute(table.update().where(table.c.id == e["id"]).values(**values))
        else:
            conn.execute(table.insert().values(id=e["id"], **values))
    gone = existing - in_file
    if gone:
        conn.execute(table.update().where(table.c.id.in_(gone)).values(hidden=True))
    return len(in_file)


def quadrants() -> list:
    return load_file()["quadrants"]
