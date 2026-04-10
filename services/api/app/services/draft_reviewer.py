import logging
import re

from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.transport_order import TransportOrder
from ..models.vehicle_state import VehicleState

logger = logging.getLogger(__name__)

_WARNING_RE = re.compile(r'⚠️\s*Нехватка ТС:[^|]*(?:\|\s*)?')
_SHORTAGE_RE = re.compile(
    r'(?:фур|газелей):\s*нужно\s*\d+,\s*свободно\s*\d+[;\s]*'
)


def _extract_user_notes(raw: str | None) -> str:
    """Strip all auto-generated shortage fragments, keep only user text."""
    if not raw:
        return ""
    clean = _WARNING_RE.sub("", raw)
    clean = _SHORTAGE_RE.sub("", clean)
    return clean.strip(" |;")


async def review_warehouse_drafts(session: AsyncSession, warehouse_id: str) -> list[dict]:
    """
    Compare each draft to the current free fleet at the warehouse (instantaneous).

    A shortage is reported only if this draft alone needs more vehicles of a type
    than are currently free — not a cumulative simulation across all drafts.
    That matches the UI: «Парк» shows physical free counts; a draft is warnable
    only if it cannot be approved right now for lack of that type.
    """
    free_gazel_q = await session.execute(
        select(func.count())
        .where(VehicleState.warehouse_id == warehouse_id)
        .where(VehicleState.vehicle_type == "gazel")
        .where(VehicleState.status == "free")
    )
    free_gazel = free_gazel_q.scalar() or 0

    free_fura_q = await session.execute(
        select(func.count())
        .where(VehicleState.warehouse_id == warehouse_id)
        .where(VehicleState.vehicle_type == "fura")
        .where(VehicleState.status == "free")
    )
    free_fura = free_fura_q.scalar() or 0

    drafts_q = await session.execute(
        select(TransportOrder)
        .where(TransportOrder.office_from_id == warehouse_id)
        .where(TransportOrder.status == "draft")
        .order_by(
            nulls_last(TransportOrder.optimizer_score.desc()),
            TransportOrder.scheduled_departure.desc(),
        )
    )
    drafts = drafts_q.scalars().all()

    warnings: list[dict] = []

    for d in drafts:
        needed_fura = d.fura_count or 0
        needed_gazel = d.gazel_count or 0
        has_shortage = False
        shortage_parts = []

        if needed_fura > 0 and needed_fura > free_fura:
            has_shortage = True
            shortage_parts.append(
                f"фур: нужно {needed_fura}, свободно {free_fura}"
            )
        if needed_gazel > 0 and needed_gazel > free_gazel:
            has_shortage = True
            shortage_parts.append(
                f"газелей: нужно {needed_gazel}, свободно {free_gazel}"
            )

        user_notes = _extract_user_notes(d.notes)

        if has_shortage:
            warning_text = "⚠️ Нехватка ТС: " + "; ".join(shortage_parts)
            d.notes = warning_text + (f" | {user_notes}" if user_notes else "")
            warnings.append({
                "order_id": str(d.id),
                "route_id": d.route_id,
                "warning": warning_text,
            })
        else:
            d.notes = user_notes or None

    await session.flush()

    logger.info(
        "Reviewed %d drafts for warehouse %s: free gazel=%d fura=%d, %d shortage warnings",
        len(drafts), warehouse_id, free_gazel, free_fura, len(warnings),
    )
    return warnings
