"""LO206 torque curve: published lookup table + interpolation.

Source
------
Torque values are the published Briggs & Stratton 206 Racing data for the
Stock/Unrestricted 206 slide (part #555590, commonly called the black slide)
-- the unrestricted club/senior setup. Torque is in ft-lbs at the crank. This
curve makes strong low-end torque (~11.1 ft-lbs at 2500-3000 RPM) and holds
~9.4 ft-lbs into the upper midrange, so HP (= torque * RPM / 5252, computed
downstream in the logger) RISES across the band and peaks near the top --
consistent with the LO206's ~8.8 HP rating (chart reads ~8.59 HP at 6000 RPM).

NOTE on the 6000-RPM point (7.52 ft-lbs): this is a real top-end dip on the
published Stock-206 chart, not a gentle taper. It is corroborated by the chart's
own HP column (7.52 * 6000 / 5252 = 8.59 HP at 6000) and by the engine's rated
power -- a flat ~9.45 ft-lbs to 6000 would imply ~10.8 HP, well above rating.

Other slide/restrictor configurations (Purple, Red, Green, Blue, Yellow, and
the restricted .440 slide) are documented in ``docs/bom.md`` and can be swapped
in by replacing the lookup table below.

NOTE: Replace this curve with measured data once the real dyno is built. The
simulator uses this same table, so improving the data here improves both the
sim and the baseline we compare real runs against. Load ONLY torque here -- HP
is derived downstream in the logger, never tabulated.

This module is the single home of the torque lookup (engine_sim.py imports
``interpolate_torque`` from here rather than duplicating the table).
"""

import numpy as np

# Stock/Unrestricted 206 slide (#555590, "black slide") -- parallel lists
# (rpm, torque_ftlbs) from the published B&S 206 Racing slide chart. The table
# spans 2500..6000 RPM. The rev-limiter threshold (6100 RPM) is NOT in the
# tabulated data; queries at or above 6100 are forced to 0.0 ft-lbs by the
# explicit clamp below (spark cut has fired, no engine torque).
TORQUE_CURVE_RPM = [2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000]
TORQUE_CURVE_FT_LBS = [11.13, 11.12, 9.83, 9.76, 9.09, 9.45, 9.45, 7.52]

# Convenience zipped view of the active curve.
ACTIVE_CURVE = list(zip(TORQUE_CURVE_RPM, TORQUE_CURVE_FT_LBS))

# Clamp behaviour outside the tabulated range:
#   below this RPM the engine makes no usable torque (treated as stalled / sub-idle)
RPM_TORQUE_ZERO_BELOW = 2000.0
#   at or above this RPM the spark cut has fired -- engine torque is 0.0 ft-lbs.
RPM_TORQUE_CLAMP_ABOVE = 6100.0

_RPM_POINTS = np.array(TORQUE_CURVE_RPM, dtype=float)
_TORQUE_POINTS = np.array(TORQUE_CURVE_FT_LBS, dtype=float)


def interpolate_torque(rpm: float) -> float:
    """Return interpolated engine torque (ft-lbs) at the given ``rpm``.

    - Below ``RPM_TORQUE_ZERO_BELOW`` (2000): returns 0.0 (engine sub-idle/stalled).
    - At or above ``RPM_TORQUE_CLAMP_ABOVE`` (6100): returns 0.0 (spark cut fired).
    - In between: linear interpolation (numpy.interp), which clamps to the first
      tabulated value (2500 RPM) for the 2000-2500 gap.
    """
    if rpm < RPM_TORQUE_ZERO_BELOW:
        return 0.0
    # Above 6100 RPM the spark cut has fired and there is no engine torque.
    # Return 0.0 rather than extrapolating. RPM can reach ~6200 in a draft
    # (observed in on-track data, AiM MyChron5, MRFKC 2026-04-24); that
    # scenario is handled by the limiter model in engine_sim.py.
    if rpm >= RPM_TORQUE_CLAMP_ABOVE:
        return 0.0
    return float(np.interp(rpm, _RPM_POINTS, _TORQUE_POINTS))


if __name__ == "__main__":
    for test_rpm in (1500, 2000, 2500, 3500, 4250, 5500, 6000, 6100, 6500):
        print(f"{test_rpm:5d} rpm -> {interpolate_torque(test_rpm):.2f} ft-lbs")
