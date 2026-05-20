"""Tests for the DynoEngine physics model: valve lag and safety trips.

Run from the simulator/ directory:  pytest
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import modbus_map as mb  # noqa: E402
from engine_sim import DynoEngine, TAU_VALVE  # noqa: E402


def test_valve_lag():
    """A step change in valve_cmd must not appear instantly in valve_actual.

    After one 10 ms tick the change must be less than 10% of the step magnitude
    (first-order lag with tau=120 ms gives ~8.3% per 10 ms step).
    """
    eng = DynoEngine(dt=0.010)
    assert eng.get_valve_actual() == 0.0

    step = 100.0
    eng.set_valve_position(step)   # command a 0 -> 100% step
    eng.tick(0.010)

    moved = eng.get_valve_actual()
    assert moved > 0.0, "valve should begin moving"
    assert moved < 0.10 * step, "valve must lag, not jump instantly"
    # sanity: matches the analytic first-order step response within tolerance
    expected = step * (0.010 / TAU_VALVE)
    assert abs(moved - expected) < 1e-6


def test_safety_trips():
    """Exceeding the pressure threshold sets the overpressure trip, latches a
    fault, and clamps the commanded valve to zero."""
    eng = DynoEngine()
    eng.set_engine_enable(True)
    eng.set_valve_position(50.0)
    assert eng.valve_cmd == 50.0
    assert not eng.overpressure and not eng.fault

    # Force pressure above the trip limit, then evaluate safety directly.
    eng._pressure_psi = mb.OVERPRESSURE_TRIP_PSI + 50.0
    eng.evaluate_safety()

    assert eng.overpressure is True
    assert eng.fault is True
    assert eng.valve_cmd == 0.0, "valve command must be clamped to zero on trip"
    assert eng.get_status() == mb.STATUS_FAULT


def test_overtemp_trip():
    """Exceeding the CHT threshold also latches a fault and closes the valve."""
    eng = DynoEngine()
    eng.set_engine_enable(True)
    eng.set_valve_position(75.0)

    eng._cht = mb.OVERTEMP_TRIP_C + 5.0
    eng.evaluate_safety()

    assert eng.overtemp is True
    assert eng.fault is True
    assert eng.valve_cmd == 0.0
