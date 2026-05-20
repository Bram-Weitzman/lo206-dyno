"""LO206 torque curve: published lookup table + interpolation.

Source
------
The torque values below are digitized from official Briggs & Stratton dyno
sheets for the LO206 in the **Black Slide (.440 opening)** configuration, the
standard senior-class restriction. Torque is in ft-lbs at the crank.

The Black Slide is one of several slide/restrictor configurations used across
LO206 racing classes (Purple, Red, Green, Blue, Yellow, and Stock are the
others). Those alternate configurations are documented in ``docs/bom.md`` and
can be swapped in here by replacing the lookup table.

NOTE: Replace this curve with measured data once the real dyno is built. The
simulator uses this same table, so improving the data here improves both the
sim and (eventually) the baseline we compare real runs against.
"""

import numpy as np

# Black Slide (.440 opening) — (rpm, torque_ftlbs) from B&S dyno sheets.
BLACK_SLIDE_CURVE = [
    (2500, 4.73),
    (3000, 5.31),
    (3500, 5.96),
    (4000, 5.82),
    (4500, 5.40),
    (5000, 4.97),
    (5500, 4.54),
    (6000, 4.14),
]

# Active curve. Swap this out to model a different slide configuration.
ACTIVE_CURVE = BLACK_SLIDE_CURVE

_RPM_POINTS = np.array([p[0] for p in ACTIVE_CURVE], dtype=float)
_TORQUE_POINTS = np.array([p[1] for p in ACTIVE_CURVE], dtype=float)


def interpolate_torque(rpm: float) -> float:
    """Return interpolated torque (ft-lbs) at the given engine ``rpm``.

    Linear interpolation across the published points. Below the lowest point or
    above the highest point, ``numpy.interp`` clamps to the endpoint value.
    """
    return float(np.interp(rpm, _RPM_POINTS, _TORQUE_POINTS))


if __name__ == "__main__":
    for test_rpm in (2000, 2500, 3250, 4000, 5750, 6000, 6500):
        print(f"{test_rpm:5d} rpm -> {interpolate_torque(test_rpm):.2f} ft-lbs")
