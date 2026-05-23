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

# --- Clutch reference-data tests ----------------------------------------
# The clutch model was BYPASSED in the physics loop (2026-05-22) so the bench
# dyno measures the engine directly. clutch_torque_fraction() is RETAINED as
# validated drivetrain reference data, so these tests still verify that math.
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


def test_pump_loads_engine_directly_no_clutch():
    """Clutch removed (2026-05-22): the pump brakes the engine DIRECTLY at all
    RPMs, including below the OLD clutch-engagement RPM (3400). A 100% valve at
    low RPM now applies real braking torque -- there is no disengaged region."""
    sim = DynoEngine()
    sim.set_engine_enable(True)
    sim.set_valve_position(100)        # maximum braking commanded
    sim._rpm = 3000                    # below the OLD clutch engagement (3400)
    sim.tick(0.01)
    assert sim._pump_load > 0.0        # pump is coupled and loading the engine


def test_full_brake_settles_at_floor_under_raised_trip():
    """Full throttle + valve 100% with the brake model AND the raised trip.

    The overpressure trip was raised 900 -> 1700 PSI (2026-05-23) for the
    corrected brake model, so the ordering is working ~1128 < trip 1700 < relief
    ~2000 < rating 3000. Because the steady working pressure (~1141 PSI at the
    floor) and the start-up transient (~1290 PSI peak) both stay BELOW 1700, full
    braking no longer faults: the engine now settles at the torque-balance
    brake-capacity floor (~2510 RPM), which is the whole point of raising the
    trip. (Under the old 900 PSI trip this faulted and ran up to the limiter.)
    """
    sim = DynoEngine()
    sim.set_engine_enable(True)
    sim.set_control_mode(0)
    sim.set_valve_position(100)
    peak_dev_psi = 0.0
    for _ in range(3000):              # 30 s settle at 10 ms/step
        sim.tick(0.01)
        peak_dev_psi = max(peak_dev_psi, sim._pressure_dev_psi)

    # No fault: working + transient pressure stayed under the raised trip.
    assert sim.fault is False
    assert sim.get_status() == mb.STATUS_RUNNING
    assert peak_dev_psi < mb.OVERPRESSURE_TRIP_PSI   # transient rode under the trip
    # Settled at the torque-balance floor, brake torque == engine torque.
    assert 2350.0 < sim._rpm < 2700.0
    assert abs(sim._pump_load - sim.engine_torque()) < 0.5


def test_brake_capacity_floor_with_trips_raised(monkeypatch):
    """The TRUE torque-balance brake floor of the new model, with the pressure
    trips conceptually raised (the next-session state).

    With overpressure trips lifted, full throttle + valve 100% settles where the
    pump brake torque equals the engine torque. The new model lands at ~2510 RPM
    (developed pressure ~1140 PSI, brake torque ~11.1 ft-lb = engine torque at
    the low end) -- lower than the old placeholder's ~3360 RPM because the spec'd
    pump is far stronger. This pins the floor for next session's SWEEP_START_RPM
    review. NOTE: this is the only test that touches the trips, and only via
    monkeypatch (restored automatically); the committed trips are NOT changed.
    """
    monkeypatch.setattr(mb, "OVERPRESSURE_TRIP_PSI", 1.0e9)
    monkeypatch.setattr(mb, "PSI_REG_MAX", 1.0e9)
    sim = DynoEngine()
    sim.set_engine_enable(True)
    sim.set_control_mode(0)
    sim.set_valve_position(100)
    for _ in range(4000):              # 40 s settle at 10 ms/step
        sim.tick(0.01)
    assert sim.fault is False                  # trips raised: no fault
    assert 2350.0 < sim._rpm < 2700.0          # torque-balance floor ~2510 RPM
    # at the floor the brake torque matches the engine torque (within noise)
    assert abs(sim._pump_load - sim.engine_torque()) < 0.5
