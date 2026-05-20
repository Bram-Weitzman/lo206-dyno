"""Tests for the LO206 torque-curve interpolation (Black Slide .520).

Run from the simulator/ directory:  pytest
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from torque_curve import (  # noqa: E402
    ACTIVE_CURVE,
    RPM_TORQUE_CLAMP_ABOVE,
    RPM_TORQUE_ZERO_BELOW,
    TORQUE_CURVE_FT_LBS,
    TORQUE_CURVE_RPM,
    interpolate_torque,
)


def test_exact_points_match_table():
    """At a tabulated RPM, interpolation returns the tabulated torque."""
    for rpm, torque in ACTIVE_CURVE:
        assert interpolate_torque(rpm) == torque


def test_midpoint_is_between_neighbors():
    """3250 rpm sits between 3000 (9.39) and 3500 (9.83)."""
    val = interpolate_torque(3250)
    assert 9.39 < val < 9.83
    assert abs(val - (9.39 + 9.83) / 2) < 1e-6


def test_zero_below_2000():
    """Below RPM_TORQUE_ZERO_BELOW the engine makes no usable torque."""
    assert RPM_TORQUE_ZERO_BELOW == 2000.0
    assert interpolate_torque(0) == 0.0
    assert interpolate_torque(1500) == 0.0
    assert interpolate_torque(1999.9) == 0.0
    # At exactly 2000 we are in-range; numpy.interp clamps to the first point.
    assert interpolate_torque(2000) == TORQUE_CURVE_FT_LBS[0]


def test_zero_at_and_above_6100():
    """At or above RPM_TORQUE_CLAMP_ABOVE the spark cut has fired — torque is 0."""
    assert RPM_TORQUE_CLAMP_ABOVE == 6100.0
    assert interpolate_torque(6100) == 0.0
    assert interpolate_torque(6200) == 0.0  # draft/push overshoot scenario
    assert interpolate_torque(6500) == 0.0
    assert interpolate_torque(9000) == 0.0
    # Just below the limiter we still interpolate from the table (6000 = 4.96).
    assert interpolate_torque(6099.9) == TORQUE_CURVE_FT_LBS[-1]


def test_peak_torque_region():
    """Published peak torque is at 3500 rpm for the .520 Black Slide."""
    peak_rpm, _ = max(ACTIVE_CURVE, key=lambda p: p[1])
    assert peak_rpm == 3500
    assert interpolate_torque(3500) >= interpolate_torque(4500)


def test_curve_lengths_match():
    """The parallel lookup lists must stay the same length."""
    assert len(TORQUE_CURVE_RPM) == len(TORQUE_CURVE_FT_LBS)
