"""Time helpers built on skyfield's timescale.

All internal time arithmetic is done in TT seconds so that leap seconds
never appear as discontinuities inside a propagation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from skyfield.api import load
from skyfield.timelib import Time, Timescale

from simcore.constants import SECONDS_PER_DAY

# builtin=True uses skyfield's bundled leap-second / Delta-T tables,
# so no network access is needed.
_TS: Timescale = load.timescale(builtin=True)


def timescale() -> Timescale:
    return _TS


def from_datetime(dt: datetime) -> Time:
    """Convert a datetime to a skyfield Time. Naive datetimes are taken as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _TS.from_datetime(dt)


def seconds_between(t0: Time, t: Time) -> np.ndarray | float:
    """Elapsed TT seconds from t0 to t (vectorized over t)."""
    return ((t.whole - t0.whole) + (t.tt_fraction - t0.tt_fraction)) * SECONDS_PER_DAY


def offset(t0: Time, seconds) -> Time:
    """Time(s) `seconds` TT seconds after t0 (vectorized over seconds)."""
    return _TS.tt_jd(t0.whole, t0.tt_fraction + np.asarray(seconds) / SECONDS_PER_DAY)
