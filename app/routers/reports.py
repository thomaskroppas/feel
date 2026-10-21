"""Аналитика и выгрузка в xlsx."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import current_user
from ..services import analytics, export
from ..timeutil import local_date_of, utcnow

router = APIRouter(prefix="/api", tags=["reports"])


def _period(period: str) -> str:
    if period not in analytics.PERIODS:
        raise HTTPException(status_code=422, detail="Неизвестный период")
    return period


@router.get("/analytics")
def get_analytics(period: str = "month", month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
                  db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    st = db.get(models.UserSettings, user.id)
    today = local_date_of(utcnow(), st.timezone)
    month_date = date(int(month[:4]), int(month[5:]), 1) if month else None
    return analytics.compute(db, user, st.timezone, _period(period), today, month_date)


@router.get("/export.xlsx")
def export_xlsx(period: str = "all", db: Session = Depends(get_db),
                user: models.User = Depends(current_user)):
    st = db.get(models.UserSettings, user.id)
    today = local_date_of(utcnow(), st.timezone)
    start, end = analytics.period_bounds(db, user.id, _period(period), today)
    data = export.build(db, user, st.timezone, start, end)
    filename = f"feel-{start.isoformat()}-{end.isoformat()}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
