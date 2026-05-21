"""Tests for the DynoEngine physics model: valve lag and safety trips.

Run from the simulator/ directory:  pytest
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import modbus_map as mb  # noqa: E402
from engine_sim import DynoEngine, TAU_VALVE, clutch_torque_fraction  # noqa: E402


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


# --- Clutch model tests ---

def test_clutch_fraction_below_engagement():
    assert clutch_torque_fraction(0) == 0.0
    assert clutch_torque_fraction(3399) == 0.0


def test_clutch_fraction_at_lockup():
    assert clutch_torque_fraction(4200) == 1.0
    assert clutch_torque_fraction(6200) == 1.0


def test_clutch_fraction_midpoint():
    mid = (3400 + 4200) / 2  # 3800
    fraction = clutch_torque_fraction(mid)
    assert 0.45 < fraction < 0.55  # should be ~0.5


def test_clutch_fraction_is_monotonic():
    rpms = range(3400, 4201, 50)
    fractions = [clutch_torque_fraction(r) for r in rpms]
    assert fractions == sorted(fractions)


def test_pump_unloaded_below_engagement():
    """Pump load must be zero below clutch engagement RPM.

    With the clutch fully open (RPM < CLUTCH_ENGAGEMENT_RPM) the hydraulic pump
    is disconnected, so even a 100% valve command applies no braking torque to
    the engine. RPM is therefore driven by engine torque alone and must not be
    pulled down by pump load. (DynoEngine.tick is the physics step; get_rpm
    carries +/-RPM_NOISE_BAND output noise, well within the 2800 margin.)
    """
    sim = DynoEngine()
    sim.set_engine_enable(True)
    sim.set_valve_position(100)  # maximum braking commanded
    # Step at low RPM -- pump should apply no load
    sim._rpm = 3000  # force RPM below engagement (CLUTCH_ENGAGEMENT_RPM = 3400)
    for _ in range(10):
        sim.tick(0.01)
    # RPM should not decrease significantly -- pump is disconnected
    assert sim.get_rpm() > 2800  # allow for idle dynamics, not pump braking
