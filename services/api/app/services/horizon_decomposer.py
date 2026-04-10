import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def decompose(
    t: list[float],
) -> list[float]:
    """
    Smooth raw 2h-window predictions into per-slot 30-min estimates.

    t: [t1, t2, ..., t10] — raw model predictions (target_2h per horizon).
    Each t_i covers 4 consecutive 30-min slots ending at slot i: {i-3, i-2, i-1, i}.
    We spread t_i / 4 into each valid slot (indices in [1, 10]).
    Overlapping windows produce a smoothed estimate per slot.
    """
    assert len(t) == 10

    # Pad with t10 repeated so that trailing slots f8/f9/f10
    # receive the full 4 contributions instead of 3/2/1.
    t_ext = t + [t[-1]] * 3

    f = [0.0] * 10
    for i in range(1, len(t_ext) + 1):
        quarter = t_ext[i - 1] / 4.0
        for j in (i - 3, i - 2, i - 1, i):
            if 1 <= j <= 10:
                f[j - 1] += quarter

    return [max(0.0, v) for v in f]


async def decompose_route_forecasts(
    session: AsyncSession,
    route_id: str,
    run_ts: datetime,
    raw_predictions: list[float],
) -> list[float]:
    future = decompose(raw_predictions)

    logger.info(
        "Decomposed route %s at %s: smoothed=%s",
        route_id,
        run_ts.isoformat(),
        future,
        extra={"route_id": route_id, "run_ts": run_ts.isoformat()},
    )

    return future
