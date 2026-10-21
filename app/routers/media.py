"""Загрузка, выдача и удаление медиа. Файлы отдаются только владельцу."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import current_user
from ..services import media as svc

router = APIRouter(prefix="/api", tags=["media"])
CHUNK = 1024 * 1024


def _own_media(db: Session, user: models.User, media_id: int) -> models.Media:
    m = db.get(models.Media, media_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return m


@router.post("/media", status_code=201)
def upload(kind: str = Form(...), checkin_id: Optional[int] = Form(None),
           day_log_date: Optional[date] = Form(None), duration_s: Optional[float] = Form(None),
           file: UploadFile = File(...), db: Session = Depends(get_db),
           user: models.User = Depends(current_user)):
    if kind not in svc.ALLOWED:
        raise HTTPException(status_code=422, detail="Неизвестный тип файла")
    if (checkin_id is None) == (day_log_date is None):
        raise HTTPException(status_code=422, detail="Файл прикрепляется к записи или к дню")
    mime = svc.normalize_mime(file.content_type)
    ext = svc.ALLOWED[kind].get(mime)
    if ext is None:
        raise HTTPException(status_code=415, detail="Такой формат файла не поддерживается")
    if kind == "audio" and duration_s is not None and duration_s > svc.MAX_AUDIO_SECONDS + 5:
        raise HTTPException(status_code=422, detail="Голосовая заметка — до 3 минут")

    # К чему прикрепляем и что заменяем.
    replaced = []
    if checkin_id is not None:
        c = db.get(models.Checkin, checkin_id)
        if c is None or c.user_id != user.id:
            raise HTTPException(status_code=404, detail="Запись не найдена")
        same = [m for m in c.media if m.kind == kind]
        if kind == "photo" and len(same) >= svc.MAX_PHOTOS:
            raise HTTPException(status_code=422, detail="К записи — не больше 4 фото")
        if kind == "audio":
            replaced = same  # одна голосовая заметка на запись: новая заменяет старую
    else:
        if db.get(models.DayLog, (user.id, day_log_date)) is None:
            db.add(models.DayLog(user_id=user.id, local_date=day_log_date))
            db.flush()
        same = list(db.scalars(select(models.Media).where(
            models.Media.user_id == user.id, models.Media.day_log_date == day_log_date,
            models.Media.kind == kind)))
        if kind == "photo" and len(same) >= svc.MAX_PHOTOS:
            raise HTTPException(status_code=422, detail="К дню — не больше 4 фото")
        if kind == "audio":
            replaced = same

    # Пишем файл частями, проверяя размер и квоту.
    rel = svc.new_relative_path(user.id, ext)
    path = svc.user_dir(user.id) / rel.split("/", 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    limit = svc.MAX_BYTES[kind]
    free = svc.quota_bytes() - svc.used_bytes(db, user.id) + sum(m.size for m in replaced)
    size = 0
    try:
        with open(path, "wb") as out:
            while True:
                chunk = file.file.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="Файл слишком большой")
                if size > free:
                    raise HTTPException(status_code=413, detail="Закончилось место для файлов")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="Пустой файл")
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    m = models.Media(user_id=user.id, checkin_id=checkin_id, day_log_date=day_log_date,
                     kind=kind, path=rel, mime=mime, size=size,
                     duration_s=round(duration_s, 1) if duration_s else None)
    for old in replaced:
        db.delete(old)
    db.add(m)
    db.commit()
    svc.remove_files(replaced)
    return svc.serialize(m)


@router.get("/media/{media_id}")
def download(media_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    m = _own_media(db, user, media_id)
    path = svc.absolute(m)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    # FileResponse поддерживает Range — без этого Safari не проигрывает аудио.
    return FileResponse(path, media_type=m.mime, headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/media/{media_id}")
def remove(media_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    m = _own_media(db, user, media_id)
    db.delete(m)
    db.commit()
    svc.remove_files([m])
    return {"ok": True}


@router.get("/media-usage")
def usage(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    return {"used": svc.used_bytes(db, user.id), "quota": svc.quota_bytes()}
