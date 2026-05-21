(*
  =====================================================================
  dyno_control.st  -  LO206 hydraulic dyno control logic
  IEC 61131-3 Structured Text  /  OpenPLC Runtime
  =====================================================================

  WHAT THIS DOES
  --------------
  Closes a speed-control loop on a Briggs & Stratton LO206 kart engine
  loaded by a hydraulic pump brake. A proportional valve modulates pump
  restriction; raising the valve raises braking torque, which lowers RPM.
  A hand-rolled PID drives the valve to hold a target RPM at full throttle.

  I/O-AGNOSTIC BY DESIGN
  ----------------------
  Every value below crosses the Modbus boundary defined in register_map.md
  (the contract, mirrored in simulator/modbus_map.py). This program does NOT
  know whether the far end is the Python simulator or the real hydraulic rig.

  >>> THE ONE THING THAT CHANGES SIM -> REAL HARDWARE <<<
  Nothing in THIS file. Only the OpenPLC "Slave Devices" / Modbus master
  configuration changes: today it points at the simulator (TCP, port 502 with
  automatic fallback to 5020); on the real build it points at the field I/O
  that exposes the identical register map. The control + safety logic here is
  reused byte-for-byte. Keep it that way.

  REGISTER MAPPING (authoritative copy in register_map.md / modbus_map.py)
  -----------------------------------------------------------------------
  Bind these named variables onto the registers below in the OpenPLC Slave
  Device config. Addresses use 3xxxx/4xxxx data-model notation; on the wire
  they are the zero-based offsets shown in parentheses.

    INPUT REGISTERS  (sim writes, PLC reads):
      30001 (0) ENGINE_RPM         -> iEngineRpmRaw      RPM, 1:1
      30002 (1) TORQUE_FTLBS_x10   -> iTorqueRaw         ft-lbs x10
      30003 (2) HYDRAULIC_PSI      -> iHydraulicPsiRaw   PSI, 1:1
      30004 (3) HEAD_TEMP_C        -> iHeadTempRaw       degC, 1:1
      30005 (4) VALVE_POSITION_ACT -> iValveActRaw       % x100 (reflects lag)
      30006 (5) AFR_x10            -> iAfrRaw            AFR x10  (RESERVED)
      30007 (6) SIM_STATUS         -> iSimStatus         0 stop/1 run/2 fault

    HOLDING REGISTERS (PLC writes, sim reads):
      40001 (0) VALVE_POSITION_CMD -> iValveCmdRaw       % x100 (0-10000)
      40002 (1) TARGET_RPM         -> iTargetRpmRaw      RPM, 1:1 (operator)
      40003 (2) CONTROL_MODE       -> iControlMode       0 manual/1 PID/2 sweep
      40004 (3) SAFETY_ENABLE      -> iSafetyEnable      0 stop/1 run (operator)

  NOTE on ownership: TARGET_RPM, CONTROL_MODE and SAFETY_ENABLE are operator
  commands set via the OpenPLC HMI / dashboard; this program consumes them and
  may OVERRIDE SAFETY_ENABLE -> 0 from the safety interlock. VALVE_POSITION_CMD
  is this program's only computed actuator output.
*)

PROGRAM dyno_control

(* --------------------------------------------------------------------
   TUNING + CALIBRATION CONSTANTS  (no magic numbers anywhere below)
   -------------------------------------------------------------------- *)
VAR CONSTANT
    (* PID gains. Starting values for sim tuning; re-tune, then calibrate
       on the real rig where valve gain and inertia differ. *)
    KP : REAL := 0.2;    (* TODO: calibrate against real hardware *)
    KI : REAL := 0.05;   (* TODO: calibrate against real hardware *)
    KD : REAL := 0.01;   (* TODO: calibrate against real hardware *)

    (* Loop period. MUST match the OpenPLC task cycle time, because the
       integral/derivative use it as dt. Sim valve lag (tau ~120 ms) is far
       slower than this, so OpenPLC's soft-real-time scan jitter is harmless. *)
    DT_S : REAL := 0.05;   (* s; TODO: keep equal to the OpenPLC cycle setting *)

    (* Actuator range, in engineering percent (the PID works in %). *)
    VALVE_MIN_PCT : REAL := 0.0;
    VALVE_MAX_PCT : REAL := 100.0;

    (* Wire scaling: register counts per engineering unit (see register_map). *)
    VALVE_SCALE   : REAL := 100.0;     (* % x100  -> 10000 counts = 100.00%  *)
    VALVE_REG_MIN : INT  := 0;
    VALVE_REG_MAX : INT  := 10000;

    (* PLC-side safety trip limits (defense-in-depth; the contract states these
       are "enforced by the sim AND PLC"). Mirror simulator/modbus_map.py. *)
    (* OVERSPEED_TRIP: 6500 RPM. Limiter fires at 6100; real-world max 6162 RPM
       (draft, AiM data 2026-04-24). 340 RPM margin prevents false trips.
       Do not lower this threshold. *)
    RPM_TRIP_RPM  : REAL := 6500.0;
    PSI_TRIP_PSI  : REAL := 750.0;   (* = OVERPRESSURE_TRIP_PSI; TODO: calibrate *)
    CHT_TRIP_C    : REAL := 250.0;   (* = OVERTEMP_TRIP_C; TODO: calibrate *)

    (* Enumerations from the contract (modbus_map.py). *)
    MODE_MANUAL    : INT := 0;
    MODE_PID       : INT := 1;
    MODE_SWEEP     : INT := 2;

    STATUS_STOPPED : INT := 0;
    STATUS_RUNNING : INT := 1;
    STATUS_FAULT   : INT := 2;

    SAFETY_STOP    : INT := 0;
    SAFETY_RUN     : INT := 1;
END_VAR

(* --------------------------------------------------------------------
   I/O IMAGE  (raw register values; bound to Modbus in OpenPLC config)
   -------------------------------------------------------------------- *)
VAR
    (* Inputs read from the sim/hardware (raw register counts) *)
    iEngineRpmRaw    AT %IW100 : INT;   (* 30001 RPM, 1:1 *)
    iTorqueRaw       AT %IW101 : INT;   (* 30002 ft-lbs x10 (logging only) *)
    iHydraulicPsiRaw AT %IW102 : INT;   (* 30003 PSI, 1:1 *)
    iHeadTempRaw     AT %IW103 : INT;   (* 30004 degC, 1:1 *)
    iValveActRaw     AT %IW104 : INT;   (* 30005 % x100 (actual, post-lag) *)
    iAfrRaw          AT %IW105 : INT;   (* 30006 AFR x10 (reserved, unused) *)
    iSimStatus       AT %IW106 : INT;   (* 30007 0 stop/1 run/2 fault *)

    (* Commands. Operator-set ones arrive via HMI; PLC publishes to holding regs. *)
    iValveCmdRaw     AT %QW100 : INT;   (* 40001 % x100 -> the actuator output *)
    iTargetRpmRaw    AT %QW101 : INT;   (* 40002 RPM, 1:1 (operator setpoint) *)
    iControlMode     AT %QW102 : INT;   (* 40003 mode (operator) *)
    iSafetyEnable    AT %QW103 : INT;   (* 40004 run/stop (operator; PLC may force 0) *)
END_VAR

(* --------------------------------------------------------------------
   ENGINEERING VALUES + PID / SAFETY STATE
   -------------------------------------------------------------------- *)
VAR
    (* Scaled-to-engineering process values *)
    rActualRpm    : REAL := 0.0;   (* RPM *)
    rTargetRpm    : REAL := 0.0;   (* RPM *)
    rHydraulicPsi : REAL := 0.0;   (* PSI *)
    rHeadTempC    : REAL := 0.0;   (* degC *)

    (* PID working set *)
    rError        : REAL := 0.0;   (* RPM; sense = PV - SP (see WHY below) *)
    rIntegral     : REAL := 0.0;   (* accumulated error*dt *)
    rMeasDeriv    : REAL := 0.0;   (* d(PV)/dt -> derivative on measurement *)
    rLastActualRpm: REAL := 0.0;   (* previous-scan PV for the derivative *)
    rOutputPct    : REAL := 0.0;   (* PID output, 0-100 % *)
    rValveCmdPct  : REAL := 0.0;   (* committed valve command, 0-100 % *)

    (* Safety / sequencing state *)
    bSafetyEnabled : BOOL := FALSE;  (* operator run command, normalized *)
    bFaultActive   : BOOL := FALSE;  (* any hard-fault condition THIS scan *)
    bFaultLatched  : BOOL := FALSE;  (* latched until fault clears + operator re-arms *)
    bPidActive     : BOOL := FALSE;  (* closed loop running this scan *)
    bPidActivePrev : BOOL := FALSE;  (* for disabled->enabled edge detection *)
    bOutputSaturated : BOOL := FALSE;
END_VAR

(* ====================================================================
   STEP 1 - SCALE INPUTS TO ENGINEERING UNITS
   ==================================================================== *)
rActualRpm    := INT_TO_REAL(iEngineRpmRaw);     (* 1:1 *)
rTargetRpm    := INT_TO_REAL(iTargetRpmRaw);     (* 1:1 *)
rHydraulicPsi := INT_TO_REAL(iHydraulicPsiRaw);  (* 1:1 *)
rHeadTempC    := INT_TO_REAL(iHeadTempRaw);      (* 1:1 *)
bSafetyEnabled := (iSafetyEnable = SAFETY_RUN);

(* ====================================================================
   STEP 2 - SAFETY INTERLOCK  (highest priority, runs EVERY scan before
   any PID output is applied)

   *** This same logic becomes the hardware safety interlock on the real
       rig. On real hardware it does NOT replace a hardwired physical
       e-stop; that is a separate, non-negotiable circuit. ***
   ==================================================================== *)

(* Hard faults: sim/HW reported a fault, OR a PLC-side limit was crossed.
   Defense-in-depth: we do not trust the status word alone. *)
bFaultActive := (iSimStatus = STATUS_FAULT)
             OR (rActualRpm    > RPM_TRIP_RPM)
             OR (rHydraulicPsi > PSI_TRIP_PSI)
             OR (rHeadTempC    > CHT_TRIP_C);

(* Latch on any fault. The latch only releases once the condition is gone;
   because we also force SAFETY_ENABLE -> 0 below, the operator must then
   re-command run to resume. A momentary spike therefore still stops the rig. *)
IF bFaultActive THEN
    bFaultLatched := TRUE;
ELSIF NOT bFaultActive THEN
    bFaultLatched := FALSE;
END_IF;

IF bFaultLatched THEN
    (* FAULT: slam the valve shut, drop the run command, dump PID state. *)
    iValveCmdRaw  := VALVE_REG_MIN;   (* 0% -> no braking command *)
    rValveCmdPct  := VALVE_MIN_PCT;
    iSafetyEnable := SAFETY_STOP;     (* clear run command (no ENGINE_ENABLE reg exists) *)
    bSafetyEnabled := FALSE;
    rIntegral     := 0.0;             (* prevent windup while tripped *)
    bPidActive    := FALSE;
    rLastActualRpm := rActualRpm;     (* keep derivative continuous on recovery *)

ELSIF NOT bSafetyEnabled THEN
    (* OPERATOR STOP (software e-stop): valve closed, integrator reset, but
       NOT latched - operator can re-run immediately by setting SAFETY_ENABLE=1. *)
    iValveCmdRaw  := VALVE_REG_MIN;
    rValveCmdPct  := VALVE_MIN_PCT;
    rIntegral     := 0.0;
    bPidActive    := FALSE;
    rLastActualRpm := rActualRpm;

ELSE
    (* ================================================================
       STEP 3 - MODE GATING + CONTROL
       PID closes the loop only in PID mode while enabled and not faulted.
       (No ENGINE_ENABLE register in this contract: SAFETY_ENABLE = master
        run/stop, CONTROL_MODE selects how the valve is driven.)
       ================================================================ *)
    bPidActive := (iControlMode = MODE_PID);

    (* Bumpless-ish start: on the disabled->enabled (or mode-entry) edge,
       zero the integrator and seed the derivative so we don't kick. *)
    IF bPidActive AND (NOT bPidActivePrev) THEN
        rIntegral      := 0.0;
        rLastActualRpm := rActualRpm;
    END_IF;

    CASE iControlMode OF
        0: (* MANUAL: operator owns iValveCmdRaw via HMI; pass it through.
              Keep the integrator cleared so re-entering PID is bumpless. *)
            rIntegral := 0.0;
            rValveCmdPct := INT_TO_REAL(iValveCmdRaw) / VALVE_SCALE;

        1: (* PID HOLD - drive the valve to hold rTargetRpm *)

            (* WHY error = PV - SP (not the usual SP - PV): the valve is a
               BRAKE. Raising it lowers RPM, so the loop is reverse-acting.
               Using (actual - target) keeps all gains POSITIVE: actual too
               high -> error>0 -> more valve -> more braking -> slows down. *)
            rError := rActualRpm - rTargetRpm;

            (* Derivative ON MEASUREMENT, not on error: differentiate the PV so
               a step change in TARGET_RPM does not produce a derivative kick. *)
            rMeasDeriv := (rActualRpm - rLastActualRpm) / DT_S;

            (* Provisional output using the EXISTING integral (anti-windup
               decides below whether to accumulate this scan). *)
            rOutputPct := (KP * rError) + (KI * rIntegral) + (KD * rMeasDeriv);

            (* ANTI-WINDUP via conditional integration: integrate normally in
               the linear region; while saturated, only integrate in the
               direction that pulls the output back out of saturation. *)
            IF (rOutputPct > VALVE_MIN_PCT) AND (rOutputPct < VALVE_MAX_PCT) THEN
                rIntegral := rIntegral + (rError * DT_S);
            ELSIF (rOutputPct >= VALVE_MAX_PCT) AND (rError < 0.0) THEN
                rIntegral := rIntegral + (rError * DT_S);   (* unwind from high stop *)
            ELSIF (rOutputPct <= VALVE_MIN_PCT) AND (rError > 0.0) THEN
                rIntegral := rIntegral + (rError * DT_S);   (* unwind from low stop *)
            END_IF;

            (* Recompute with the possibly-updated integral. *)
            rOutputPct := (KP * rError) + (KI * rIntegral) + (KD * rMeasDeriv);
            rValveCmdPct := rOutputPct;

        2: (* SWEEP - ramp the setpoint across an RPM band and log torque vs RPM.
              Not implemented this session. Fall back to manual pass-through so
              behavior is defined and never auto-commands an unsafe valve move. *)
            rIntegral := 0.0;
            rValveCmdPct := INT_TO_REAL(iValveCmdRaw) / VALVE_SCALE;
            (* TODO: implement sweep schedule (ramp rTargetRpm over time) then
               reuse the mode-1 PID to track it. *)

    ELSE
        (* Unknown mode: safest defined behavior is operator pass-through. *)
        rIntegral := 0.0;
        rValveCmdPct := INT_TO_REAL(iValveCmdRaw) / VALVE_SCALE;
    END_CASE;

    rLastActualRpm := rActualRpm;   (* store PV for next scan's derivative *)
END_IF;

(* ====================================================================
   STEP 4 - OUTPUT CLAMP + SCALE TO WIRE (skipped when faulted/stopped:
   those branches already wrote a safe 0). Hard clamp is the last line of
   defense regardless of how rValveCmdPct was produced.
   ==================================================================== *)
IF bPidActive OR (iControlMode = MODE_MANUAL) THEN

    IF rValveCmdPct > VALVE_MAX_PCT THEN
        rValveCmdPct := VALVE_MAX_PCT;
        bOutputSaturated := TRUE;
    ELSIF rValveCmdPct < VALVE_MIN_PCT THEN
        rValveCmdPct := VALVE_MIN_PCT;
        bOutputSaturated := TRUE;
    ELSE
        bOutputSaturated := FALSE;
    END_IF;

    (* Scale engineering % -> register counts (% x100), clamp to wire range. *)
    iValveCmdRaw := REAL_TO_INT(rValveCmdPct * VALVE_SCALE);
    IF iValveCmdRaw > VALVE_REG_MAX THEN
        iValveCmdRaw := VALVE_REG_MAX;
    ELSIF iValveCmdRaw < VALVE_REG_MIN THEN
        iValveCmdRaw := VALVE_REG_MIN;
    END_IF;
END_IF;

(* Remember whether the loop was active, for next scan's enable-edge detection. *)
bPidActivePrev := bPidActive;

END_PROGRAM

(* --------------------------------------------------------------------
   OPENPLC RESOURCE BINDING
   --------------------------------------------------------------------
   Required by the OpenPLC v3 build script (which moves Config0.c / Res0.c
   into place after iec2c). The task interval here MUST equal DT_S above —
   the integral and derivative use DT_S as dt; if they disagree the
   effective Ki / Kd are wrong.
*)
CONFIGURATION Config0
    RESOURCE Res0 ON PLC
        TASK Main(INTERVAL := T#50ms, PRIORITY := 0);
        PROGRAM Inst0 WITH Main : dyno_control;
    END_RESOURCE
END_CONFIGURATION
