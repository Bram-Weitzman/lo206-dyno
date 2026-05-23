"""Tests for the DynoEngine physics model: valve lag and safety trips.

Run from the simulator/ directory:  pytest
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import modbus_map as mb  # noqa: E402
from engine_sim import (  # noqa: E402
    DynoEngine, TAU_VALVE, clutch_torque_fraction,
    RPM_LIMITER, RPM_LIMITER_HYSTERESIS,
)


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


def test_full_brake_trips_overpressure_under_current_cap():
    """Full throttle + valve 100% with the NEW physically-grounded brake model.

    REPLACES the old ~3135 RPM brake-floor assertion. With the spec'd 2.14 cu
    in/rev pump on the 2.909:1 gear set, full restriction develops well over
    1000 PSI (the design working pressure is ~1128 PSI). The sim overpressure
    trip is UNCHANGED this session (OVERPRESSURE_TRIP_PSI = 900), so the pump
    crosses it almost immediately at full braking: the model latches a fault,
    the interlock forces the valve shut, and with no brake the engine runs up to
    the rev limiter. So there is NO low-RPM 'floor' under the current trip --
    that is the point. The brake-capacity floor only becomes reachable once the
    trips are raised to the new ~2000 PSI relief scheme (next session); see
    test_brake_capacity_floor_with_trips_raised for the torque-balance floor.
    """
    sim = DynoEngine()
    sim.set_engine_enable(True)
    sim.set_control_mode(0)
    sim.set_valve_position(100)
    peak_dev_psi = 0.0
    for _ in range(2000):              # 20 s settle at 10 ms/step
        sim.tick(0.01)
        peak_dev_psi = max(peak_dev_psi, sim._pressure_dev_psi)

    # Developed pressure exceeded the (unchanged) sim overpressure trip...
    assert peak_dev_psi > mb.OVERPRESSURE_TRIP_PSI
    # ...so a fault latched and the engine ran up to the limiter rather than
    # holding a low brake floor.
    assert sim.fault is True
    assert sim.get_status() == mb.STATUS_FAULT
    assert sim._rpm > RPM_LIMITER - RPM_LIMITER_HYSTERESIS  # ran up, not braked down


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
