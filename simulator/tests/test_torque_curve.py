"""Basic tests for the LO206 torque-curve interpolation.

Run from the simulator/ directory:  pytest
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from torque_curve import BLACK_SLIDE_CURVE, interpolate_torque


def test_exact_points_match_table():
    """At a tabulated RPM, interpolation returns the tabulated torque."""
    for rpm, torque in BLACK_SLIDE_CURVE:
        assert interpolate_torque(rpm) == torque


def test_midpoint_is_between_neighbors():
    """3250 rpm sits between 3000 (5.31) and 3500 (5.96)."""
    val = interpolate_torque(3250)
    assert 5.31 < val < 5.96
    # linear midpoint
    assert abs(val - (5.31 + 5.96) / 2) < 1e-6


def test_clamps_below_and_above_range():
    """numpy.interp clamps to the endpoints outside the table range."""
    assert interpolate_torque(1000) == BLACK_SLIDE_CURVE[0][1]
    assert interpolate_torque(9000) == BLACK_SLIDE_CURVE[-1][1]


def test_peak_torque_region():
    """Published peak torque is around 3500 rpm for the Black Slide."""
    peak_rpm, peak_torque = max(BLACK_SLIDE_CURVE, key=lambda p: p[1])
    assert peak_rpm == 3500
    assert interpolate_torque(peak_rpm) >= interpolate_torque(peak_rpm + 1000)
