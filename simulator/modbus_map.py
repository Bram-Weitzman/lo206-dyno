"""Modbus register map — single source of truth in code.

This module mirrors the authoritative contract documented in
``plc/register_map.md``. Both the simulator and any future tooling import
addresses, scale factors, mode constants, and safety limits from here so that
there are NO magic numbers elsewhere in the codebase.

Layout (per plc/register_map.md — addresses are zero-based wire offsets, which
map 1:1 to Modbus client addresses):

  Input Registers   (fc 4): sensors   — simulator writes, PLC reads   (30001+)
  Holding Registers (fc 3): commands  — PLC writes, simulator reads   (40001+)

The simulator owns the input registers; the PLC owns the holding registers.

NOTE: This is the *committed* contract from the previous session. This session's
brief proposed a different, richer layout (coils, discrete inputs, FLAGS bitmask,
timestamp registers, torque x1000). Per an explicit decision, the simulator
conforms to THIS contract. The richer layout was intentionally not adopted to
avoid two competing register maps. See the session notes / commit message.
"""

# --- Modbus function codes (used for datastore access + client calls) ---
FC_COILS = 1
FC_DISCRETE_INPUTS = 2
FC_HOLDING_REGISTERS = 3   # commands: PLC writes, sim reads
FC_INPUT_REGISTERS = 4     # sensors: sim writes, PLC reads

# Device/unit id. Clients may address unit 1; the server's single context maps
# any unit id to device 0, so both work. Internal datastore access uses 0.
UNIT_ID = 1
INTERNAL_DEVICE_ID = 0

# --- Input Registers: sensors (simulator writes, PLC reads) --- 3000x notation
IR_ENGINE_RPM      = 0   # 30001  RPM, 1:1
IR_TORQUE_X10      = 1   # 30002  ft-lbs x10  (105 = 10.5 ft-lbs)
IR_HYDRAULIC_PSI   = 2   # 30003  PSI, 1:1
IR_HEAD_TEMP_C     = 3   # 30004  degC, 1:1
IR_VALVE_POS_ACT   = 4   # 30005  % x100      (10000 = 100.00%)
IR_AFR_X10         = 5   # 30006  AFR x10      (147 = 14.7) — reserved
IR_SIM_STATUS      = 6   # 30007  0=stopped 1=running 2=fault
IR_LIMITER_ACTIVE  = 7   # 30008  0=released 1=rev limiter cutting spark
INPUT_REGISTER_COUNT = 8

# --- Holding Registers: commands (PLC writes, simulator reads) --- 4000x
HR_VALVE_POS_CMD   = 0   # 40001  % x100      (5000 = 50.00%)
HR_TARGET_RPM      = 1   # 40002  RPM — logged only, NOT used by physics
HR_CONTROL_MODE    = 2   # 40003  0=manual 1=PID 2=sweep
HR_SAFETY_ENABLE   = 3   # 40004  0=estop/stop 1=run
HOLDING_REGISTER_COUNT = 4

# --- Coils: binary commands (PLC writes, simulator reads) --- 0000x
COIL_THROTTLE = 0        # 00001  binary throttle: 0=idle (no drive), 1=wide-open
COIL_COUNT    = 1

# --- Scale factors (engineering value * scale = raw register value) ---
RPM_SCALE      = 1       # RPM 1:1
TORQUE_SCALE   = 10      # ft-lbs x10
PRESSURE_SCALE = 1       # PSI 1:1
CHT_SCALE      = 1       # degC 1:1
VALVE_SCALE    = 100     # %    x100
AFR_SCALE      = 10      # AFR  x10

# --- Control mode constants (HR_CONTROL_MODE) ---
MODE_MANUAL = 0
MODE_PID    = 1
MODE_SWEEP  = 2

# --- Safety enable constants (HR_SAFETY_ENABLE) ---
SAFETY_ESTOP = 0   # stop / e-stop
SAFETY_RUN   = 1   # run

# --- Throttle coil constants (COIL_THROTTLE) ---
THROTTLE_IDLE = 0   # engine makes no drive torque
THROTTLE_WOT  = 1   # wide-open throttle (full torque curve)

# --- Sim status constants (IR_SIM_STATUS) ---
STATUS_STOPPED = 0
STATUS_RUNNING = 1
STATUS_FAULT   = 2

# --- Limiter-active constants (IR_LIMITER_ACTIVE) ---
LIMITER_RELEASED = 0
LIMITER_ACTIVE   = 1

# --- Reserved / placeholder values ---
AFR_NOMINAL_X10 = 147   # 14.7:1 stoich placeholder (no wideband O2 in Phase 1)

# --- Register engineering ranges (clamp before publishing, per contract) ---
RPM_REG_MAX    = 7000    # 30001 range 0-7000 (extends past 6100 so overspeed is visible)
TORQUE_REG_MAX = 150     # 30002 range 0-150  (= 15.0 ft-lbs x10)
PSI_REG_MAX    = 3000    # 30003 range 0-3000 (3-tier scheme: working ~1128 /
                         # relief ~2000 / pump rating 3000; see register_map.md).
                         # Behavior-neutral under the unchanged trips (sim 900 /
                         # PLC 750), which cap/fault pressure well below 1500.
CHT_REG_MAX    = 300     # 30004 range 0-300
VALVE_REG_MAX  = 10000   # 30005 range 0-10000 (= 100.00%)
AFR_REG_MIN    = 100     # 30006 range 100-200
AFR_REG_MAX    = 200

# --- Safety trip limits (physical plant limits; enforced by the sim and PLC) ---
# Kept here so the contract module is the single source of truth for limits.
OVERPRESSURE_TRIP_PSI = 1700.0  # Raised 900 -> 1700 (2026-05-23) for the corrected
                                 # brake model (2.14 cu in/rev, 2.909:1) + three-tier
                                 # pressure scheme. Ordering: working ~1128 < trip 1700
                                 # < mechanical relief ~2000 < pump rating 3000. 1700 is
                                 # ~570 PSI (~50%) above the ~1128 PSI steady working
                                 # point (rides out PID transients) and ~300 PSI below
                                 # the ~2000 PSI relief (software trip fires first).
                                 # MUST equal PSI_TRIP_PSI in plc/dyno_control.st.
                                 # Below PSI_REG_MAX (3000) so an over-trip reading is
                                 # representable. History: 900 (#219 chain 3.5:1), 1200
                                 # (belt 2.1:1).
                                 # TODO: confirm with pressure transducer on real hardware.
OVERTEMP_TRIP_C       = 250.0
