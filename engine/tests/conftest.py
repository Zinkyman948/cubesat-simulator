from pathlib import Path

import pytest

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"

# ISS TLE from January 2014 (skyfield documentation example).
ISS_LINE1 = "1 25544U 98067A   14020.93268519  .00009878  00000-0  18200-3 0  5082"
ISS_LINE2 = "2 25544  51.6498 109.4756 0003572  55.9686 274.8005 15.49815350868473"


@pytest.fixture
def scenarios_dir() -> Path:
    return SCENARIOS
