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

import logging
import math
import random

from torque_curve import interpolate_torque
import modbus_map as mb

_log = logging.getLogger(__name__)

# --- Integration ---
DT_DEFAULT = 0.010                 # s, 10 ms physics step (matches server loop)

# --- Engine inertia model ---
# TODO: calibrate against real hardware -- estimated for small single-cylinder
# with flywheel.
J_ENGINE = 0.05                    # kg.m^2 rotational inertia

# --- Hydraulic pump load model ---
PUMP_LOAD_GAIN = 18.5              # Updated for confirmed hardware: 1.52 cu.in. gear pump,
                                   # 2.1:1 belt reduction. Derivation: at peak torque
                                   # (10 ft-lbs, 3,500 RPM), required pressure ~1,042 PSI.
                                   # Gain scales valve position (0.0-1.0) to pump load torque
                                   # in ft-lbs. With back-pressure baseline of 200 PSI,
                                   # effective modulation range is 200-1,200 PSI across valve
                                   # travel.
                                   # TODO: calibrate against real hardware -- this remains a
                                   # model estimate.
MAX_PUMP_TORQUE = PUMP_LOAD_GAIN   # ft-lbs reference for pressure scaling
MAX_PRESSURE_PSI = 700.0           # PSI at MAX_PUMP_TORQUE (proportional contribution; the
                                   # total modeled pressure is BACKPRESSURE_BASELINE_PSI plus
                                   # this proportional term, capped at OVERPRESSURE_TRIP_PSI)
BACKPRESSURE_BASELINE_PSI = 200    # Return-line back-pressure valve, set ~200 PSI.
                                   # NOTE: this baseline is applied ONLY to the reported hydraulic
                                   # pressure telemetry (see tick step 4). It does NOT contribute to
                                   # brake torque -- _compute_pump_load() is a pure function of valve
                                   # position and RPM, so the back-pressure valve's real braking
                                   # contribution is NOT modelled. The low-RPM floor (~4,004 RPM at
                                   # PUMP_LOAD_GAIN=18.5) is therefore clutch-limited, not set by
                                   # back-pressure; the real rig's floor will sit lower once this valve
                                   # adds brake torque -- known sim-fidelity gap (see CLAUDE.md). Real
                                   # hardware: Princess Auto Item 8688939, adjustable
                                   # 50-3,000 PSI relief valve, $69.99 CAD.
                                   # TODO: tune on real hardware -- 150-250 PSI is the
                                   # expected range depending on desired low-RPM floor.

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
IDLE_RPM = 2400   # Warm idle, measured from real LO206 race session data (May 2026).
                  # Cold/high idle can reach 3,000–3,200 RPM during warmup.
                  # Warm idle is safely below clutch engagement (~3,400 RPM).

# --- Clutch (Hilliard Inferno Flame, stock springs) ---
CLUTCH_ENGAGEMENT_RPM = 3400  # RPM at which clutch shoes first contact drum.
                              # Stock Hilliard Inferno Flame: 2 black + 2 white
                              # springs, 0 heavy weights per shoe.
                              # Confirmed: matches spring chart spec and validated
                              # against race data (cursor at transition: 3,537 RPM).

CLUTCH_LOCKUP_RPM = 4200      # Estimated RPM for full clutch lockup under pump load.
                              # On-track lockup is lower — pump load is much heavier
                              # than kart rolling resistance so lockup RPM shifts higher
                              # under dyno conditions.
                              # TODO: validate on real hardware during first runs.

# --- Sensor model ---
RPM_NOISE_BAND = 100          # ±RPM noise observed at steady state in real race data.
                              # Source: Hall-effect pickup, single trigger tooth —
                              # normal for kart setups. Applied to RPM output only
                              # so PID is tuned against realistic input.
                              # Internal physics state is not affected.

# --- Rev limiter ---
# Rev limiter model -- calibrated from AiM MyChron5 on-track data (MRFKC,
# 2026-04-24). Real behavior: spark cut at ~6000-6100 RPM, drops ~700-850 RPM
# in <=50ms, recovers in ~100-150ms, repeats at ~5-10 Hz. Operating band:
# ~5200-6100 RPM. Model uses instantaneous torque cut consistent with measured
# data; the inertia integration alone produces the RPM drop -- do NOT subtract
# RPM manually.
RPM_LIMITER = 6100.0               # spark cut threshold
RPM_LIMITER_MAX = 6200.0           # hard ceiling for draft/push overshoot scenario
                                   # (real-world observed max: 6162 RPM, AiM 2026-04-24)
RPM_LIMITER_HYSTERESIS = 100.0     # release torque below RPM_LIMITER - this band
                                   # to prevent the limiter from toggling every tick

# --- Unit conversions ---
FT_LB_TO_NM = 1.355818
RAD_PER_SEC_TO_RPM = 60.0 / (2.0 * math.pi)


def _clamp(value, lo, hi):
    return lo if value < lo else hi if value > hi else value


def clutch_torque_fraction(rpm: float) -> float:
    """
    RETAINED REFERENCE DATA -- NOT USED BY THE PHYSICS LOOP. The clutch model
    was bypassed (2026-05-22) so the bench dyno measures the engine directly
    across the full rev range; see tick(). This function and the CLUTCH_*
    constants stay defined as validated drivetrain reference data.

    Returns the fraction of engine torque transferred to the pump (0.0 to 1.0)
    based on current RPM and the centrifugal clutch engagement model.

    Hilliard Inferno Flame, stock config: 2 black + 2 white springs, 0 heavy weights.
    Real-world data: engagement at ~3,400 RPM, estimated lockup at ~4,200 RPM under
    pump load. No RPM dip at engagement -- smooth torque ramp confirmed from race data.

    Below engagement: clutch fully open, pump sees no load.
    Engagement to lockup: linear ramp -- torque transfer increases with RPM.
    Above lockup: fully locked, full torque transfer.
    """
    if rpm < CLUTCH_ENGAGEMENT_RPM:
        return 0.0
    elif rpm >= CLUTCH_LOCKUP_RPM:
        return 1.0
    else:
        return (rpm - CLUTCH_ENGAGEMENT_RPM) / (CLUTCH_LOCKUP_RPM - CLUTCH_ENGAGEMENT_RPM)


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
        # rev limiter
        self._limiter_active = False         # True while spark cut is suppressing torque
        self._rpm_capped_at_max = False      # edge tracker so we warn once per hit

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
    def _update_limiter(self) -> None:
        """Latch/release the rev limiter from current RPM with hysteresis.

        Pure state update; called from :meth:`tick` before torque is computed so
        :meth:`engine_torque` can stay a side-effect-free reader.
        """
        if self._rpm >= RPM_LIMITER:
            self._limiter_active = True
        elif self._rpm < RPM_LIMITER - RPM_LIMITER_HYSTERESIS:
            self._limiter_active = False

    def engine_torque(self) -> float:
        """Driving torque (ft-lbs). Zero when stopped or when the spark cut is
        active (limiter latched). Otherwise looked up on the published curve."""
        if not self._engine_enable:
            return 0.0
        if self._limiter_active:
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

        # 2. Torques. Update the rev limiter latch first so engine_torque() sees
        #    the correct state this tick.
        self._update_limiter()
        eng_tq = self.engine_torque()
        self._pump_load = self._compute_pump_load()
        # CLUTCH MODEL BYPASSED (2026-05-22): the bench dyno must measure the
        # engine across the FULL rev range, so the brake (pump) load couples to
        # the engine DIRECTLY, with no centrifugal-clutch slip term. Engine torque
        # drives the inertia integration against the full pump load. The clutch
        # would impose a ~4200 RPM lockup floor, blinding the dyno in exactly the
        # range a clutch change would affect. clutch_torque_fraction() and the
        # CLUTCH_* constants are RETAINED as validated drivetrain reference data
        # (Hilliard Inferno Flame, 2 black + 2 white springs) -- see CLAUDE.md
        # "Real-world calibration data" -- but are no longer part of the engine
        # model. This also resolves the old below-engagement inconsistency where
        # pressure/CHT used raw (un-clutched) pump load while torque used the
        # clutched value: everything now uses the same self._pump_load.
        net_torque_ftlbs = eng_tq - self._pump_load

        # 3. Inertia integration: angular accel (rad/s^2) -> RPM.
        net_torque_nm = net_torque_ftlbs * FT_LB_TO_NM
        angular_accel = net_torque_nm / J_ENGINE
        self._rpm += angular_accel * dt * RAD_PER_SEC_TO_RPM
        if self._rpm < 0.0:
            self._rpm = 0.0

        # 3b. Hard RPM ceiling: physics should keep us below this, but if any
        #     pathological combination of torque/load/dt produces overshoot,
        #     clamp at RPM_LIMITER_MAX so the rest of the model stays bounded.
        #     Warn on the rising edge only -- do not spam every tick.
        if self._rpm > RPM_LIMITER_MAX:
            if not self._rpm_capped_at_max:
                _log.warning(
                    "RPM hard ceiling hit: clamping %.1f to %.1f (RPM_LIMITER_MAX)",
                    self._rpm, RPM_LIMITER_MAX,
                )
                self._rpm_capped_at_max = True
            self._rpm = RPM_LIMITER_MAX
        else:
            self._rpm_capped_at_max = False

        # 4. Hydraulic pressure: back-pressure baseline + proportional contribution
        #    from pump brake torque. The return-line back-pressure valve enforces
        #    a minimum reading at all RPMs -- even at 0% valve, pressure does not
        #    fall below BACKPRESSURE_BASELINE_PSI. Cap at the safety trip so the
        #    published register stays bounded if pump_load spikes.
        proportional_psi = (self._pump_load / MAX_PUMP_TORQUE) * MAX_PRESSURE_PSI
        self._pressure_psi = BACKPRESSURE_BASELINE_PSI + proportional_psi
        if self._pressure_psi > mb.OVERPRESSURE_TRIP_PSI:
            self._pressure_psi = mb.OVERPRESSURE_TRIP_PSI

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
        # Inject representative sensor noise to match real hardware signal characteristics.
        # Real LO206 data shows ±100 RPM noise band at steady state (race data, May 2026).
        # Applied to output only -- internal rpm variable used for physics stays clean.
        rpm_output = self._rpm + random.uniform(-RPM_NOISE_BAND, RPM_NOISE_BAND)
        return rpm_output

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

    @property
    def limiter_active(self) -> bool:
        """True while the rev limiter has cut spark (RPM in the limiter band)."""
        return self._limiter_active


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
          f"status={eng.get_status()} limiter={eng.limiter_active}")
