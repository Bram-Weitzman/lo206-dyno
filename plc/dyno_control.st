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
  MODE_SWEEP supervises that PID to walk RPM up the rev range in steps.

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
      40002 (1) TARGET_RPM         -> iTargetRpmRaw      RPM, 1:1 (operator in PID;
                                                          PLC writes sweep target in SWEEP)
      40003 (2) CONTROL_MODE       -> iControlMode       0 manual/1 PID/2 sweep
      40004 (3) SAFETY_ENABLE      -> iSafetyEnable      0 stop/1 run (operator)

    SWEEP REGISTERS (MODE_SWEEP; PLC <-> dashboard via :502, NOT sim-mirrored):
      40005 (104) SWEEP_START_RPM  -> iSweepStartRaw     RPM (operator)
      40006 (105) SWEEP_END_RPM    -> iSweepEndRaw       RPM (operator)
      40007 (106) SWEEP_STEP_RPM   -> iSweepStepRaw      RPM/step (operator)
      40008 (107) SWEEP_DWELL_MS   -> iSweepDwellRaw     ms/step (operator)
      40009 (108) SWEEP_STATE      -> iSweepState        0 idle/1 run/2 done (PLC out)

  NOTE on ownership: TARGET_RPM, CONTROL_MODE, SAFETY_ENABLE and the four
  SWEEP_* params are operator commands set via the OpenPLC HMI / dashboard; this
  program consumes them and may OVERRIDE SAFETY_ENABLE -> 0 (from the safety
  interlock, or by itself at the end of a sweep). TARGET_RPM is also
  mode-scoped: in SWEEP the program WRITES the current stepping target back into
  it (see MODE_SWEEP below) so the dashboard/logger can track it. The valve
  command VALVE_POSITION_CMD and SWEEP_STATE are this program's computed outputs.
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
    (* PSI_TRIP_PSI: raised 750 -> 1700 (2026-05-23) for the corrected brake
       model + three-tier pressure scheme. Ordering: working ~1128 < trip 1700
       < mechanical relief ~2000 < pump rating 3000. 1700 sits ~570 PSI (~50%)
       above the ~1128 PSI steady working point to ride out PID transients, yet
       ~300 PSI below the ~2000 PSI relief so the software trip fires first.
       Must equal OVERPRESSURE_TRIP_PSI in simulator/modbus_map.py. *)
    PSI_TRIP_PSI  : REAL := 1700.0;
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

    (* Sweep state word values (SWEEP_STATE / %QW108). *)
    SWEEP_IDLE     : INT := 0;
    SWEEP_RUNNING  : INT := 1;
    SWEEP_COMPLETE : INT := 2;

    (* Sweep guard rails (defense-in-depth; the dashboard and /api/command clamp
       too). SWEEP_START_RPM is clamped into [SWEEP_FLOOR_RPM .. SWEEP_MAX_RPM].
       With the clutch model removed (2026-05-22) the brake-capacity floor is
       ~3135 RPM; SWEEP_FLOOR_RPM is set just above warm idle (2400) so the
       operator can sweep the full usable range down toward that floor. Starting
       below the brake floor is allowed -- the PID just saturates at full valve
       on those low steps (RPM sits at the floor), which the state machine
       tolerates. SWEEP_MAX caps at the limiter. STEP_MIN guarantees the target
       advances (a 0 step would hang the state machine); DWELL_MIN guarantees
       forward progress on the dwell timer. *)
    SWEEP_FLOOR_RPM    : REAL := 2500.0;
    SWEEP_MAX_RPM      : REAL := 6100.0;
    SWEEP_STEP_MIN     : REAL := 50.0;
    SWEEP_DWELL_MIN_MS : REAL := 100.0;
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

    (* Sweep params (operator-set via :502) + sweep status word (PLC output).
       Located in %QW but NOT in the slave-device sim mirror; served by OpenPLC's
       built-in :502 server. SWEEP_DWELL fits INT (contract caps it at 30000 ms). *)
    iSweepStartRaw   AT %QW104 : INT;   (* 40005 RPM (operator) *)
    iSweepEndRaw     AT %QW105 : INT;   (* 40006 RPM (operator) *)
    iSweepStepRaw    AT %QW106 : INT;   (* 40007 RPM/step (operator) *)
    iSweepDwellRaw   AT %QW107 : INT;   (* 40008 ms/step (operator) *)
    iSweepState      AT %QW108 : INT;   (* 40009 0 idle/1 run/2 done (PLC output) *)
END_VAR

(* --------------------------------------------------------------------
   ENGINEERING VALUES + PID / SAFETY / SWEEP STATE
   -------------------------------------------------------------------- *)
VAR
    (* Scaled-to-engineering process values *)
    rActualRpm    : REAL := 0.0;   (* RPM *)
    rTargetRpm    : REAL := 0.0;   (* RPM *)
    rHydraulicPsi : REAL := 0.0;   (* PSI *)
    rHeadTempC    : REAL := 0.0;   (* degC *)

    (* PID working set *)
    rEffectiveSetpoint : REAL := 0.0; (* SP fed to the PID: TARGET_RPM (PID) or
                                         the stepped target (SWEEP) *)
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
    bPidActive     : BOOL := FALSE;  (* closed loop running this scan (PID or sweep) *)
    bPidActivePrev : BOOL := FALSE;  (* for disabled->enabled edge detection *)
    bOutputSaturated : BOOL := FALSE;

    (* Sweep supervisor state *)
    rSweepStart        : REAL := 0.0;   (* clamped start RPM (latched at entry) *)
    rSweepEnd          : REAL := 0.0;   (* clamped end RPM *)
    rSweepStep         : REAL := 0.0;   (* clamped step RPM *)
    rSweepDwellMs      : REAL := 0.0;   (* clamped dwell, ms *)
    rSweepTarget       : REAL := 0.0;   (* current step's target RPM *)
    rSweepDwellElapsed : REAL := 0.0;   (* ms dwelled at this step (scan-counted) *)
    bSweepActivePrev   : BOOL := FALSE; (* sweeping last scan? -> entry-edge detect *)
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
    bSweepActivePrev := FALSE;        (* a fault aborts any sweep in progress *)

ELSIF NOT bSafetyEnabled THEN
    (* OPERATOR STOP (software e-stop): valve closed, integrator reset, but
       NOT latched - operator can re-run immediately by setting SAFETY_ENABLE=1.
       This is also how Stop / E-stop ends a sweep mid-run. *)
    iValveCmdRaw  := VALVE_REG_MIN;
    rValveCmdPct  := VALVE_MIN_PCT;
    rIntegral     := 0.0;
    bPidActive    := FALSE;
    rLastActualRpm := rActualRpm;
    bSweepActivePrev := FALSE;

ELSE
    (* ================================================================
       STEP 3 - MODE GATING + CONTROL
       A closed loop runs in PID mode (1) and SWEEP mode (2). SWEEP is a
       SUPERVISOR that steps an internal setpoint and reuses the SAME PID to
       hold each step - it does NOT reimplement valve control. MANUAL (0)
       passes the operator valve command straight through.
       (No ENGINE_ENABLE register: SAFETY_ENABLE = master run/stop,
        CONTROL_MODE selects how the valve is driven.)
       ================================================================ *)
    bPidActive := (iControlMode = MODE_PID) OR (iControlMode = MODE_SWEEP);

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
            bSweepActivePrev := FALSE;

        1: (* PID HOLD - hold the operator setpoint TARGET_RPM. *)
            rEffectiveSetpoint := rTargetRpm;
            bSweepActivePrev := FALSE;

        2: (* SWEEP - stepped acceleration sweep, supervising the PID. Steps an
              internal target from SWEEP_START_RPM up to SWEEP_END_RPM in
              SWEEP_STEP_RPM increments, dwelling SWEEP_DWELL_MS at each step.
              The shared PID below holds each step. The dwell is counted off the
              PLC scan (DT_S), NEVER wall-clock, because the runtime is only
              soft-real-time. *)

            (* Entry edge: first sweep scan since (re)enable. Latch the operator
               params (clamped) and arm the state machine. *)
            IF NOT bSweepActivePrev THEN
                rSweepStart   := INT_TO_REAL(iSweepStartRaw);
                rSweepEnd     := INT_TO_REAL(iSweepEndRaw);
                rSweepStep    := INT_TO_REAL(iSweepStepRaw);
                rSweepDwellMs := INT_TO_REAL(iSweepDwellRaw);

                IF rSweepStart < SWEEP_FLOOR_RPM THEN rSweepStart := SWEEP_FLOOR_RPM; END_IF;
                IF rSweepStart > SWEEP_MAX_RPM   THEN rSweepStart := SWEEP_MAX_RPM;   END_IF;
                IF rSweepEnd   > SWEEP_MAX_RPM   THEN rSweepEnd   := SWEEP_MAX_RPM;   END_IF;
                IF rSweepEnd   < rSweepStart     THEN rSweepEnd   := rSweepStart;     END_IF;
                IF rSweepStep  < SWEEP_STEP_MIN  THEN rSweepStep  := SWEEP_STEP_MIN;  END_IF;
                IF rSweepDwellMs < SWEEP_DWELL_MIN_MS THEN rSweepDwellMs := SWEEP_DWELL_MIN_MS; END_IF;

                rSweepTarget       := rSweepStart;
                rSweepDwellElapsed := 0.0;
                iSweepState        := SWEEP_RUNNING;
            END_IF;

            (* Dwell timer: accumulate scan time at the current step. *)
            rSweepDwellElapsed := rSweepDwellElapsed + (DT_S * 1000.0);

            IF rSweepDwellElapsed >= rSweepDwellMs THEN
                IF rSweepTarget >= rSweepEnd THEN
                    (* FINAL step's dwell done. End the sweep ourselves: this is
                       the ONLY place the control logic ends a run on its own and
                       NOT on a fault. Mark complete, drop the run command so the
                       engine coasts down (the safe end state), and command zero
                       brake this scan. The dashboard polls SWEEP_STATE=2 to
                       auto-close the run row. *)
                    iSweepState    := SWEEP_COMPLETE;
                    iSafetyEnable  := SAFETY_STOP;
                    bSafetyEnabled := FALSE;
                    iValveCmdRaw   := VALVE_REG_MIN;
                    rValveCmdPct   := VALVE_MIN_PCT;
                    rIntegral      := 0.0;
                    bPidActive     := FALSE;   (* skip PID + output scaling this scan *)
                ELSE
                    (* Advance to the next step and restart the dwell timer. *)
                    rSweepTarget := rSweepTarget + rSweepStep;
                    IF rSweepTarget > rSweepEnd THEN rSweepTarget := rSweepEnd; END_IF;
                    rSweepDwellElapsed := 0.0;
                END_IF;
            END_IF;

            rEffectiveSetpoint := rSweepTarget;
            (* Mirror sweep target to %QW101 (TARGET_RPM) so the dashboard
               setpoint line tracks the staircase and the logger records it.
               Mode-scoped ownership: the sweep owns TARGET_RPM while in SWEEP,
               overwriting any operator value (see register_map.md). *)
            iTargetRpmRaw := REAL_TO_INT(rSweepTarget);
            bSweepActivePrev := bPidActive;   (* TRUE unless we just completed *)

    ELSE
        (* Unknown mode: safest defined behavior is operator pass-through. *)
        rIntegral := 0.0;
        rValveCmdPct := INT_TO_REAL(iValveCmdRaw) / VALVE_SCALE;
        bSweepActivePrev := FALSE;
    END_CASE;

    (* ----------------------------------------------------------------
       SHARED PID - runs for PID hold (mode 1) and for each sweep step
       (mode 2). Drives the valve to hold rEffectiveSetpoint. Skipped when a
       sweep just completed (bPidActive was cleared above).
       ---------------------------------------------------------------- *)
    IF bPidActive THEN
        (* WHY error = PV - SP (not the usual SP - PV): the valve is a BRAKE.
           Raising it lowers RPM, so the loop is reverse-acting. Using
           (actual - target) keeps all gains POSITIVE: actual too high ->
           error>0 -> more valve -> more braking -> slows down. *)
        rError := rActualRpm - rEffectiveSetpoint;

        (* Derivative ON MEASUREMENT, not on error: differentiate the PV so a
           step change in the setpoint produces no derivative kick. This matters
           at every sweep step boundary too. *)
        rMeasDeriv := (rActualRpm - rLastActualRpm) / DT_S;

        (* Provisional output using the EXISTING integral (anti-windup decides
           below whether to accumulate this scan). *)
        rOutputPct := (KP * rError) + (KI * rIntegral) + (KD * rMeasDeriv);

        (* ANTI-WINDUP via conditional integration: integrate normally in the
           linear region; while saturated, only integrate in the direction that
           pulls the output back out of saturation. *)
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
    END_IF;

    rLastActualRpm := rActualRpm;   (* store PV for next scan's derivative *)
END_IF;

(* ====================================================================
   STEP 4 - OUTPUT CLAMP + SCALE TO WIRE (skipped when faulted/stopped, or
   when a sweep just completed: those branches already wrote a safe 0). Hard
   clamp is the last line of defense regardless of how rValveCmdPct was made.
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
