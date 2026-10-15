import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import audit, require_role
from app.models import OrganizationLead, User
from app.services.export import build_rows, to_csv, to_xlsx

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/companies")
def export_companies(request: Request, format: str = Query("xlsx", pattern="^(csv|xlsx)$"), job_id: uuid.UUID | None = None,
                     min_fit: float | None = None, ids: list[uuid.UUID] = Query(default=[]), include_synthetic: bool = False,
                     user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    rows, stats = build_rows(db, user.org_id, company_ids=ids or None, job_id=job_id, min_fit=min_fit, include_synthetic=include_synthetic)
    now = datetime.now(UTC)
    for lead in db.scalars(select(OrganizationLead).where(OrganizationLead.org_id == user.org_id,
                                                          OrganizationLead.company_id.in_([uuid.UUID(r["company_id"]) for r in rows]))):
        lead.exported_at = now
    audit(db, user, "export.companies", details={"format": format, "rows": len(rows), **stats, "job_id": str(job_id) if job_id else None},
          request=request)
    db.commit()
    stamp = now.strftime("%Y%m%d-%H%M")
    headers = {"X-Export-Rows": str(stats["exported"]), "X-Export-Withheld-Fields": str(stats["withheld_fields"]),
               "X-Export-Excluded-Companies": str(stats["excluded_companies"]),
               "Access-Control-Expose-Headers": "X-Export-Rows, X-Export-Withheld-Fields, X-Export-Excluded-Companies, Content-Disposition"}
    if format == "csv":
        headers["Content-Disposition"] = f'attachment; filename="leads-{stamp}.csv"'
        return Response(to_csv(rows), media_type="text/csv; charset=utf-8", headers=headers)
    meta = {"exported_at": now.isoformat(), "rows": len(rows), "withheld_fields_due_to_source_licences": stats["withheld_fields"],
            "companies_excluded_due_to_source_licences": stats["excluded_companies"], "synthetic_included": include_synthetic,
            "note": "Fields known only from sources that prohibit export (e.g. Google Places content) are withheld."}
    headers["Content-Disposition"] = f'attachment; filename="leads-{stamp}.xlsx"'
    return Response(to_xlsx(rows, meta), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
