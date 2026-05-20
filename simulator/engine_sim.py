"""LO206 engine + hydraulic-load physics model.

Self-contained physics for the engine under test coupled to a hydraulic brake.
It produces the telemetry the PLC reads (RPM, torque, pressure, CHT, actual
valve position, status) and consumes the command the PLC writes (valve position,
run/stop). ``modbus_server.py`` wraps this and maps state onto the register
contract in ``plc/register_map.md`` / ``modbus_map.py``.

This module performs NO Modbus I/O. It imports a few *named constants* from
``modbus_map`` (the contract module) only so safety limits and status codes have
a single source of truth -- there are no sockets or protocol concerns here.

CONTRACT MAPPING NOTE
---------------------
The committed contract (plc/register_map.md) has a single run/stop input,
HR_SAFETY_ENABLE (40004), and no separate engine-kill input. This model treats
SAFETY_ENABLE as engine run/stop:
  - SAFETY_ENABLE = RUN  -> engine produces curve torque; valve tracks command.
  - SAFETY_ENABLE = STOP -> engine driving torque = 0; the hydraulic pump keeps
    braking at the commanded valve, so RPM decays to zero (and pressure with it).
A safety TRIP (overpressure / overtemp) latches a fault, forces the valve fully
closed, and reports STATUS_FAULT -- this is the contract's "force valve to 0"
interlock. The fault clears on a STOP->RUN re-enable once conditions are normal.

Physics parameters that need real measurement are flagged
``# TODO: calibrate against real hardware`` with the rationale for the
placeholder value.
"""

import math

from torque_curve import interpolate_torque
import modbus_map as mb

# --- Integration ---
DT_DEFAULT = 0.010                 # s, 10 ms physics step (matches server loop)

# --- Engine inertia model ---
# TODO: calibrate against real hardware -- estimated for small single-cylinder
# with flywheel.
J_ENGINE = 0.05                    # kg.m^2 rotational inertia

# --- Hydraulic pump load model ---
# TODO: calibrate against real pump curve. At 100% valve and RPM_MAX the pump
# absorbs slightly more than peak engine torque (~9.8 ft-lbs), so the PID has
# authority to stall the engine if misconfigured -- this is intentional.
PUMP_LOAD_GAIN = 12.0              # ft-lbs at 100% valve, RPM_MAX
MAX_PUMP_TORQUE = PUMP_LOAD_GAIN   # ft-lbs reference for pressure scaling
MAX_PRESSURE_PSI = 700.0           # PSI at MAX_PUMP_TORQUE

# --- Proportional valve lag (first order) ---
TAU_VALVE = 0.120                  # s, 120 ms -- midpoint of the 50-200 ms hardware spec

# --- CHT thermal model ---
# TODO: calibrate against real hardware. The brief THERMAL_SCALE=0.8 with the
# (pump_load * raw_rpm) formula diverges (+200 degC/tick); 1e-4 gives a physical
# response: ~85 degC equilibrium at 50% load, ~170 degC worst case, so overtemp
# only trips under abnormal load. COOLING_COEFF kept as specified.
THERMAL_SCALE = 1.0e-4
COOLING_COEFF = 0.05
AMBIENT_TEMP_C = 25.0

# --- Speed references ---
RPM_MAX = 6100.0                   # nominal governed max; pump-load normalisation
# Starter brings the engine to ~idle on enable; cranking is not modelled, so on
# the RUN rising edge we seed RPM to the lowest tabulated curve point.
# TODO: calibrate against real hardware (true idle speed).
IDLE_RPM = 2500.0

# --- Unit conversions ---
FT_LB_TO_NM = 1.355818
RAD_PER_SEC_TO_RPM = 60.0 / (2.0 * math.pi)


def _clamp(value, lo, hi):
    return lo if value < lo else hi if value > hi else value


class DynoEngine:
    """Lumped model of the LO206 engine coupled to a hydraulic brake.

    Advance with :meth:`tick`. Commands come in via the setters; telemetry comes
    out via the getters. Torques from the curve are in ft-lbs and converted to
    SI for the inertia integration.
    """

    def __init__(self, dt: float = DT_DEFAULT):
        self.dt = dt
        # state
        self._rpm = 0.0
        self._valve_cmd = 0.0          # commanded valve %, as written by the PLC
        self._valve_act = 0.0          # actual valve % after first-order lag
        self._cht = AMBIENT_TEMP_C     # cylinder head temp, degC
        self._pressure_psi = 0.0
        self._pump_load = 0.0          # ft-lbs, last computed brake torque
        # inputs
        self._engine_enable = False
        self._prev_enable = False
        self._control_mode = mb.MODE_MANUAL
        self._target_rpm = 0.0         # logged only, not used by physics
        # safety
        self._fault = False            # latched
        self._overpressure = False
        self._overtemp = False

    # ------------------------------------------------------------------ inputs
    def set_valve_position(self, percent: float) -> None:
        """Set the commanded valve position (0-100 %)."""
        self._valve_cmd = _clamp(float(percent), 0.0, 100.0)

    def set_engine_enable(self, enabled: bool) -> None:
        """Run/stop (maps to HR_SAFETY_ENABLE: RUN=enabled, STOP=killed)."""
        self._engine_enable = bool(enabled)

    def set_control_mode(self, mode: int) -> None:
        """Record control mode. The PLC owns the control strategy; the sim only
        applies the resulting valve command, so this is informational here."""
        self._control_mode = int(mode)

    def set_target_rpm(self, rpm: float) -> None:
        """Record the operator/HMI target RPM. Logged only -- not used by physics."""
        self._target_rpm = float(rpm)

    # ----------------------------------------------------------------- physics
    def engine_torque(self) -> float:
        """Driving torque (ft-lbs). Zero unless the engine is enabled (running)."""
        if not self._engine_enable:
            return 0.0
        return interpolate_torque(self._rpm)

    def _compute_pump_load(self) -> float:
        """Hydraulic brake (resisting) torque, ft-lbs, from actual valve & RPM."""
        return PUMP_LOAD_GAIN * (self._valve_act / 100.0) * (self._rpm / RPM_MAX)

    def tick(self, dt: float = None) -> None:
        """Advance the model by one time step ``dt`` (seconds)."""
        if dt is None:
            dt = self.dt

        # Cranking: on the RUN rising edge, seed RPM up to idle (starter).
        if self._engine_enable and not self._prev_enable and not self._fault:
            self._rpm = max(self._rpm, IDLE_RPM)
        self._prev_enable = self._engine_enable

        # 1. Valve first-order lag. On a latched fault the valve is driven shut.
        target_valve = 0.0 if self._fault else self._valve_cmd
        self._valve_act += (target_valve - self._valve_act) * (dt / TAU_VALVE)
        self._valve_act = _clamp(self._valve_act, 0.0, 100.0)

        # 2. Torques.
        eng_tq = self.engine_torque()
        self._pump_load = self._compute_pump_load()
        net_torque_ftlbs = eng_tq - self._pump_load

        # 3. Inertia integration: angular accel (rad/s^2) -> RPM.
        net_torque_nm = net_torque_ftlbs * FT_LB_TO_NM
        angular_accel = net_torque_nm / J_ENGINE
        self._rpm += angular_accel * dt * RAD_PER_SEC_TO_RPM
        if self._rpm < 0.0:
            self._rpm = 0.0

        # 4. Hydraulic pressure from brake torque.
        self._pressure_psi = (self._pump_load / MAX_PUMP_TORQUE) * MAX_PRESSURE_PSI

        # 5. CHT thermal model.
        heat_input = self._pump_load * self._rpm * THERMAL_SCALE
        cooling = (self._cht - AMBIENT_TEMP_C) * COOLING_COEFF
        self._cht += (heat_input - cooling) * dt

        # 6. Safety evaluation (may latch fault and clamp valve command).
        self.evaluate_safety()

    def evaluate_safety(self) -> None:
        """Evaluate trips against current pressure/CHT. Latches a fault and forces
        the valve command to zero on overpressure or overtemp. Separated from
        :meth:`tick` so it can be exercised directly in tests."""
        self._overpressure = self._pressure_psi > mb.OVERPRESSURE_TRIP_PSI
        self._overtemp = self._cht > mb.OVERTEMP_TRIP_C

        if self._overpressure or self._overtemp:
            self._fault = True

        if self._fault:
            # Force the valve fully closed regardless of what the PLC wrote.
            self._valve_cmd = 0.0
            # Fault clears only on a STOP->RUN re-enable with conditions normal.
            if not self._engine_enable and not self._overpressure and not self._overtemp:
                self._fault = False

    # ----------------------------------------------------------------- outputs
    def get_rpm(self) -> float:
        return self._rpm

    def get_torque(self) -> float:
        """Current engine driving torque (ft-lbs) at present RPM/enable state."""
        return self.engine_torque()

    def get_valve_actual(self) -> float:
        return self._valve_act

    def get_hydraulic_psi(self) -> float:
        return self._pressure_psi

    def get_head_temp_c(self) -> float:
        return self._cht

    def get_status(self) -> int:
        if self._fault:
            return mb.STATUS_FAULT
        if self._engine_enable:
            return mb.STATUS_RUNNING
        return mb.STATUS_STOPPED

    # convenience accessors for tests / diagnostics
    @property
    def overpressure(self) -> bool:
        return self._overpressure

    @property
    def overtemp(self) -> bool:
        return self._overtemp

    @property
    def fault(self) -> bool:
        return self._fault

    @property
    def valve_cmd(self) -> float:
        return self._valve_cmd


# OBSERVED VALUES (smoke test, Black Slide .520, 50% valve, J=0.05, gain=12.0):
#   - Standalone settling (4 s @ 50% valve): rpm ~5392, torque ~5.64 ft-lbs,
#     valve_act 50.0%, psi ~309, cht ~33 C, status running.
#   - Live Modbus TCP (2 s after enable @ 50%): rpm 4863, torque 6.80 ft-lbs
#     (on-curve), psi 279, cht 28 C, valve_act 50.00%, status running.
#   - Equilibrium settles near ~5400 rpm at 50% valve; RPM lands in the
#     expected 3000-6000 band. Higher valve % => lower equilibrium rpm (more
#     braking), as intended.

if __name__ == "__main__":
    # Quick standalone settling demo at 50% valve.
    eng = DynoEngine()
    eng.set_engine_enable(True)
    eng.set_valve_position(50.0)
    for _step in range(400):  # 4 s at 10 ms
        eng.tick()
    print(f"after 4s @50% valve: rpm={eng.get_rpm():.0f} "
          f"torque={eng.get_torque():.2f} ft-lbs "
          f"valve_act={eng.get_valve_actual():.1f}% "
          f"psi={eng.get_hydraulic_psi():.1f} cht={eng.get_head_temp_c():.1f} "
          f"status={eng.get_status()}")
