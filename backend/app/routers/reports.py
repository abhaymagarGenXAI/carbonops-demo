from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Response

from app.core.deps import CurrentUser, Db
from app.schemas.common import CamelModel
from app.services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"])
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class InventoryOut(CamelModel):
    scope: dict[str, Any]
    summary: dict[str, Any]
    warnings: list[str]


def _build(db, from_month, to_month, basis, facility_id):
    return svc.build(db, from_month, to_month, basis, facility_id)


@router.get("/inventory", response_model=InventoryOut, summary="GHG inventory summary (preview; nothing is exported)")
def inventory(db: Db, _: CurrentUser, from_month: str | None = Query(None, alias="from", pattern=MONTH),
              to_month: str | None = Query(None, alias="to", pattern=MONTH), basis: str = "approved", facility_id: str | None = None):
    return _build(db, from_month, to_month, basis, facility_id)


def _file(maker, media: str):
    def endpoint(db: Db, user: CurrentUser, from_month: str | None = Query(None, alias="from", pattern=MONTH),
                 to_month: str | None = Query(None, alias="to", pattern=MONTH), basis: str = "approved", facility_id: str | None = None):
        data, name = maker(db, user, _build(db, from_month, to_month, basis, facility_id))
        return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return endpoint


router.add_api_route("/inventory.xlsx", _file(svc.to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), methods=["GET"], summary="Excel workbook")
router.add_api_route("/inventory.csv", _file(svc.to_csv, "text/csv; charset=utf-8"), methods=["GET"], summary="Calculation trace as CSV")
router.add_api_route("/inventory.pdf", _file(svc.to_pdf, "application/pdf"), methods=["GET"], summary="PDF report")
