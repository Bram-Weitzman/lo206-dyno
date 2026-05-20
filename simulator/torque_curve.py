"""LO206 torque curve: published lookup table + interpolation.

Source
------
Torque values digitized from official Briggs & Stratton dyno sheets for the
LO206 in the **Black Slide (.520 opening)** configuration — the unrestricted
club/senior setup. Torque is in ft-lbs at the crank. This curve peaks near
9.8 ft-lbs around 3500 RPM, consistent with the project's ~10 ft-lbs / 8.8 HP
hardware target (see README).

Other slide/restrictor configurations (Purple, Red, Green, Blue, Yellow, Stock,
and the older .440 Black Slide) are documented in ``docs/bom.md`` and can be
swapped in by replacing the lookup table below.

NOTE: Replace this curve with measured data once the real dyno is built. The
simulator uses this same table, so improving the data here improves both the
sim and the baseline we compare real runs against.

This module is the single home of the torque lookup (engine_sim.py imports
``interpolate_torque`` from here rather than duplicating the table).
"""

import numpy as np

# Black Slide (.520 opening) — parallel lists (rpm, torque_ftlbs) from B&S sheets.
# AUDIT (Task 1/6, 2026-05-20): the table spans 2500..6000 RPM. The rev limiter
# threshold (6100 RPM) is NOT in the tabulated data — queries at or above 6100
# fall into the clamp branch below, not a tabulated interpolation point.
TORQUE_CURVE_RPM = [2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000]
TORQUE_CURVE_FT_LBS = [9.06, 9.39, 9.83, 9.18, 7.38, 6.62, 5.37, 4.96]

# Convenience zipped view of the active curve.
ACTIVE_CURVE = list(zip(TORQUE_CURVE_RPM, TORQUE_CURVE_FT_LBS))

# Clamp behaviour outside the tabulated range:
#   below this RPM the engine makes no usable torque (treated as stalled / sub-idle)
RPM_TORQUE_ZERO_BELOW = 2000.0
#   above this RPM (rev-limiter region) hold the last tabulated value; the sim
#   should never operate here in normal control.
# AUDIT (Task 1/6): "hold the last tabulated value" means the function returns
# 4.96 ft-lbs (the 6000 RPM value) for any rpm > 6100. This is WRONG when the
# real spark cut has fired — true engine torque at that point is 0.0 ft-lbs, not
# ~5 ft-lbs. Task 2/6 will replace this clamp with a 0.0 return.
RPM_TORQUE_CLAMP_ABOVE = 6100.0

_RPM_POINTS = np.array(TORQUE_CURVE_RPM, dtype=float)
_TORQUE_POINTS = np.array(TORQUE_CURVE_FT_LBS, dtype=float)


def interpolate_torque(rpm: float) -> float:
    """Return interpolated engine torque (ft-lbs) at the given ``rpm``.

    - Below ``RPM_TORQUE_ZERO_BELOW`` (2000): returns 0.0 (engine sub-idle/stalled).
    - Above ``RPM_TORQUE_CLAMP_ABOVE`` (6100): clamps to the last tabulated value.
    - In between: linear interpolation (numpy.interp), which clamps to the first
      tabulated value (2500 RPM) for the 2000-2500 gap.
    """
    # AUDIT (Task 1/6) — answers to the three audit questions for this module:
    #   (a) RPM range of data points: 2500..6000. 6100 (the rev-limiter
    #       threshold) is NOT a tabulated data point.
    #   (b) What does interpolation return above the last point?
    #       Two layers behave the same way today:
    #         - 6000 < rpm <= 6100 falls through to np.interp, which (for
    #           x > xp[-1]) clamps to yp[-1] = 4.96 ft-lbs.
    #         - rpm > 6100 hits the explicit branch below and also returns 4.96.
    #       Neither path extrapolates a slope and neither errors.
    #   (c) Is there a dedicated path for queries above the limiter? Yes — the
    #       ``rpm > RPM_TORQUE_CLAMP_ABOVE`` branch — but it returns the last
    #       tabulated value (4.96), not 0.0. With a fired spark cut the real
    #       engine produces 0 torque; this branch lies to the rest of the sim.
    #       Fixed in Task 2/6.
    if rpm < RPM_TORQUE_ZERO_BELOW:
        return 0.0
    if rpm > RPM_TORQUE_CLAMP_ABOVE:
        return float(_TORQUE_POINTS[-1])
    return float(np.interp(rpm, _RPM_POINTS, _TORQUE_POINTS))


if __name__ == "__main__":
    for test_rpm in (1500, 2000, 2500, 3500, 4250, 5500, 6000, 6500):
        print(f"{test_rpm:5d} rpm -> {interpolate_torque(test_rpm):.2f} ft-lbs")
