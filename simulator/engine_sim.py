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

# --- Engine internal friction / overrun braking (coastdown) ---
# Internal friction + pumping + compression braking that decelerates the engine
# when it is NOT making combustion power (engine disabled, or -- once the throttle
# register exists -- at idle throttle / overrun). It is a real, always-present
# phenomenon, but the PUBLISHED WOT torque curve (torque_curve.py) is already the
# NET, friction-subtracted, dyno-measured output, so this term is applied ONLY
# off-power -- adding it again at WOT would double-count and shift the validated
# WOT sweep. See tick() for the gating.
#
# Modelled as viscous (rises with RPM: friction/pumping/windage all grow with
# speed) plus a small static term. Calibration target: an LO206 has a small
# flywheel and coasts ~6000 -> ~2500 RPM in under ~2 s when unloaded off-throttle.
# TODO: calibrate against the real engine (coastdown test: WOT to redline, chop
# throttle, time the 6000->2500 decay).
FRICTION_VISCOUS_FTLB_PER_RPM = 0.0016   # ft-lb of braking per RPM
FRICTION_STATIC_FTLB          = 1.5      # ft-lb constant breakaway/seal drag

# --- Hydraulic brake model (physically grounded from the spec'd hardware) ---
# Re-derived 2026-05-22 from the locked brake hardware (docs/bom.md), replacing
# the old linear PUMP_LOAD_GAIN placeholder (which was tuned to a 3.5:1 chain /
# 1.52 cu.in. pump that is no longer the design). The chain of physics is:
#
#   pump_rpm        = engine_rpm / GEAR_RATIO
#   pump_flow_gpm   = PUMP_DISP_CUIN * pump_rpm / 231          (231 cu in / gallon)
#   pump_pressure   = orifice model of (valve restriction, flow)   [see below]
#   pump_torque_inlb = pump_pressure * PUMP_DISP_CUIN / (2*pi)  (positive-disp pump)
#   engine_brake_ftlb = (pump_torque_inlb / 12) / GEAR_RATIO    (reflected to crank)
#
# Torque -> pressure is SPEED-INDEPENDENT (a positive-displacement pump develops
# torque = pressure * disp / 2pi regardless of RPM); only the FLOW varies with
# RPM, which is what the orifice pressure model below keys off.
GEAR_RATIO = 64.0 / 22.0           # = 2.909:1 reduction (22T engine gear / 64T pump gear).
                                   # The pump is the SLOW, high-torque side: it spins at
                                   # engine_rpm / GEAR_RATIO and develops GEAR_RATIO x the
                                   # crank's reflected brake torque. Hence engine brake torque
                                   # = pump_shaft_torque / GEAR_RATIO.
                                   # NOTE: the session brief's prose said "engine = pump-shaft
                                   # torque * 2.909", which is INVERTED relative to its OWN worked
                                   # example (11 ft-lb engine <-> 32 ft-lb pump <-> 1128 PSI). This
                                   # model is built to the physically correct direction (/GEAR_RATIO),
                                   # which reproduces that worked point exactly.
PUMP_DISP_CUIN = 2.14              # cu in/rev, fixed-displacement gear pump, 3000 PSI rated
                                   # (docs/bom.md). VERIFY exact displacement before purchase.

# Worked-point anchor (docs/bom.md): at FULL restriction (valve 100%) and the
# engine's low end (~2500 RPM -> ~7.96 GPM pump flow), the non-compensated valve
# develops ~1128 PSI, the pressure that absorbs the engine's ~11 ft-lb low-end
# torque. That single anchor calibrates the lumped orifice constant below.
#
# Non-compensated proportional throttle/pressure valve: it builds back-pressure by
# RESTRICTING outlet flow. Orifice pressure rises with FLOW (Q^2, classic orifice
# dP ~ Q^2) and with CLOSURE (more command = smaller area = more restriction). We
# lump area-vs-command into a simple restriction^2 term:
#
#   pump_pressure_psi = VALVE_ORIFICE_K * restriction_frac^2 * flow_gpm^2
#
# where restriction_frac = valve_act/100 in [0,1] (0 = open, 1 = full closure).
VALVE_ORIFICE_K = 17.8             # PSI / (GPM^2 * restriction_frac^2). Lumps the orifice
                                   # discharge coefficient, fluid density, and the valve's
                                   # (unknown) flow-area-vs-command curve into one constant,
                                   # pinned to the 1128 PSI @ valve100%/7.96 GPM worked point
                                   # (1128 / (1.0^2 * 7.96^2) = 17.8).
                                   # BENCH-MEASURE: the real restriction->pressure curve depends
                                   # on the chosen valve's area-vs-command profile. The flow term
                                   # is the VERIFIED operating window 8.0-19.4 GPM (8.0 at 2500
                                   # engine RPM, 19.4 at 6100), computed below as 2.14*pump_rpm/231
                                   # -- an earlier 0.8-2.0 GPM figure was wrong by ~10x and is
                                   # superseded (see docs/bom.md). Both exponents (restriction^2,
                                   # flow^2) are the physically expected shape but not yet fit to data.

# Pre-derived: engine-shaft brake torque (ft-lb) per PSI of pump pressure.
#   = PUMP_DISP_CUIN / (2*pi)  [in-lb/PSI at pump] / 12 [->ft-lb] / GEAR_RATIO [->crank]
# At 1128 PSI this is 1128 * PSI_TO_ENGINE_FTLB = ~11.0 ft-lb (matches worked point).
PSI_TO_ENGINE_FTLB = PUMP_DISP_CUIN / (2.0 * math.pi * 12.0 * GEAR_RATIO)

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
RPM_MAX = 6100.0                   # nominal governed max (reference only; the brake
                                   # model no longer normalises pump load against it)
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
        self._pressure_dev_psi = 0.0   # PSI, last developed (uncapped) pump pressure
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

    def _pump_flow_gpm(self) -> float:
        """Pump volumetric flow (GPM) at the current engine RPM.

        Fixed-displacement pump on the 2.909:1 gear set: pump turns at
        engine_rpm / GEAR_RATIO and pumps PUMP_DISP_CUIN per rev. 231 cu in/gal.
        """
        pump_rpm = self._rpm / GEAR_RATIO
        return PUMP_DISP_CUIN * pump_rpm / 231.0

    def _pump_brake_pressure_psi(self) -> float:
        """Pressure (PSI) the non-compensated valve develops at the pump outlet.

        Orifice model: pressure rises with flow (Q^2) and with closure
        (restriction^2). restriction = actual valve position / 100 (0 = open,
        1 = full closure). See VALVE_ORIFICE_K for the worked-point calibration
        and the bench-measurement caveat.
        """
        restriction = self._valve_act / 100.0
        flow_gpm = self._pump_flow_gpm()
        return VALVE_ORIFICE_K * (restriction ** 2) * (flow_gpm ** 2)

    def _compute_pump_load(self) -> float:
        """Hydraulic brake (resisting) torque at the ENGINE shaft, ft-lbs.

        Derived from the developed pump pressure (stored for the pressure
        telemetry, uncapped): brake torque = pressure * PSI_TO_ENGINE_FTLB,
        where PSI_TO_ENGINE_FTLB folds in the pump displacement, the in-lb->ft-lb
        conversion, and the 2.909:1 reduction back to the crank. Speed-independent
        for a given pressure; the speed dependence enters via the flow term in the
        pressure model above.
        """
        self._pressure_dev_psi = self._pump_brake_pressure_psi()
        return self._pressure_dev_psi * PSI_TO_ENGINE_FTLB

    def _friction_torque(self) -> float:
        """Engine internal friction + pumping/compression braking, ft-lb (>=0,
        opposes rotation). Viscous (rises with RPM) + small static term. Applied
        only off-power by tick() (see FRICTION_* constants for why)."""
        return FRICTION_VISCOUS_FTLB_PER_RPM * self._rpm + FRICTION_STATIC_FTLB

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
        #
        # COASTDOWN FRICTION (2026-05-23): the engine's internal friction/pumping
        # braking decelerates it whenever it is NOT making combustion power. The
        # published curve is already net-of-friction, so we apply this term ONLY
        # off-power to avoid double-counting -- which keeps the WOT path below
        # byte-identical to the validated sweep. "Firing" here == engine enabled
        # (Step 3 will additionally require the throttle wide-open). Without this
        # term a disabled-but-spinning engine coasts forever (the run-43 bug).
        firing = self._engine_enable
        friction_tq = 0.0 if firing else self._friction_torque()
        net_torque_ftlbs = eng_tq - self._pump_load - friction_tq

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

        # 4. Hydraulic pressure: the pressure the valve develops at the pump outlet
        #    (computed in _compute_pump_load and stored uncapped in
        #    self._pressure_dev_psi). The new design has NO return-line back-pressure
        #    valve, so there is no additive baseline -- at 0% command the valve is
        #    open and outlet pressure is ~0. Cap the PUBLISHED register at PSI_REG_MAX
        #    (3000, the transducer range) -- NOT at the overpressure trip -- so that
        #    an overpressure is actually VISIBLE to the trip (mirrors how ENGINE_RPM
        #    extends past the overspeed trip so the controller can see it). The old
        #    model capped at the trip, which masked overpressure entirely; that was
        #    harmless only because the old plant never developed >900 PSI.
        self._pressure_psi = self._pressure_dev_psi
        if self._pressure_psi > mb.PSI_REG_MAX:
            self._pressure_psi = float(mb.PSI_REG_MAX)

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


# OBSERVED VALUES (new physically-grounded brake model, Stock-206 curve, J=0.05):
#   - Worked-point anchor reproduces exactly: valve 100% @ 2500 RPM (7.96 GPM)
#     -> 1128 PSI developed -> 11.0 ft-lb brake torque at the crank.
#   - Developed-pressure magnitudes are in the design ballpark (NOT 10x off):
#     valve 50% @ 5000 RPM -> 1128 PSI; valve 60% @ 4000 RPM -> 1040 PSI.
#     Full restriction higher in the band climbs steeply (Q^2): ~4500 PSI at
#     5000 RPM, ~6700 PSI at 6100 RPM (these would open relief / fault for real).
#   - Full throttle + valve 100% UNDER THE CURRENT 900 PSI SIM TRIP: pressure
#     crosses 900 at ~2749 RPM, the model faults, the valve is forced shut, and
#     the engine runs up to the ~6100 limiter. No low-RPM floor is holdable until
#     the trips are raised to the ~2000 PSI relief scheme (NEXT SESSION).
#   - Torque-balance floor with trips raised: ~2510 RPM (1141 PSI, brake 11.1 =
#     engine 11.1 ft-lb). This is the true brake-capacity floor of the new pump
#     (vs the old placeholder's ~3360); pins next session's SWEEP_START_RPM review.

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
