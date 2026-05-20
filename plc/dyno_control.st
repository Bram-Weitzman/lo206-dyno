(*
  dyno_control.st  -  LO206 dyno control logic (IEC 61131-3 Structured Text)

  Runs on OpenPLC. I/O-agnostic: every value below crosses the Modbus boundary
  defined in register_map.md. This program does NOT know whether the other end
  is the Python simulator or real hardware.

  Modbus mapping (configure these in the OpenPLC slave/master setup so the
  located variables below land on the right registers):

    Holding registers (this PLC WRITES):
      40001 VALVE_POSITION_CMD  -> rValveCmd        (0-10000 = 0.0-100.0%)
      40002 TARGET_RPM          -> rTargetRPM
      40003 CONTROL_MODE        -> iControlMode     (0 manual,1 PID,2 sweep)
      40004 SAFETY_ENABLE       -> bSafetyEnable    (0 estop,1 run)

    Input registers (this PLC READS):
      30001 ENGINE_RPM          -> rActualRPM
      30002 TORQUE_FTLBS_x10    -> iTorqueX10
      30003 HYDRAULIC_PSI       -> iHydraulicPSI
      30004 HEAD_TEMP_C         -> iHeadTempC
      30005 VALVE_POSITION_ACT  -> rValveActual
      30006 AFR_x10             -> iAfrX10          (reserved)
      30007 SIM_STATUS          -> iSimStatus
*)

PROGRAM dyno_control
VAR
    (* setpoint / feedback *)
    rTargetRPM   : REAL := 0.0;
    rActualRPM   : REAL := 0.0;

    (* PID gains - TODO: tune against the simulator first *)
    rKp          : REAL := 0.0;   (* TODO: proportional gain *)
    rKi          : REAL := 0.0;   (* TODO: integral gain *)
    rKd          : REAL := 0.0;   (* TODO: derivative gain *)

    (* PID working vars *)
    rError       : REAL := 0.0;
    rIntegral    : REAL := 0.0;
    rDerivative  : REAL := 0.0;
    rLastError   : REAL := 0.0;
    rValveCmd    : REAL := 0.0;   (* output, 0-100% (scale to 0-10000 on write) *)
    rValveActual : REAL := 0.0;   (* feedback from 30005 *)

    (* mode + safety *)
    iControlMode : INT := 0;
    bSafetyEnable: BOOL := FALSE;
    iSimStatus   : INT := 0;

    (* sensed values *)
    iTorqueX10   : INT := 0;
    iHydraulicPSI: INT := 0;
    iHeadTempC   : INT := 0;
    iAfrX10      : INT := 0;

    (* loop timing *)
    rDt          : REAL := 0.05;  (* s; match the task scan period *)

    (* safety limits - TODO: review against real hydraulic circuit *)
    RPM_TRIP     : REAL := 6500.0;
    PSI_TRIP     : INT  := 1200;
END_VAR

(* ---------------- SAFETY INTERLOCK (highest priority) ---------------- *)
(* If disabled, overspeed, or over-pressure: slam the valve shut and bail. *)
IF (bSafetyEnable = FALSE)
   OR (rActualRPM > RPM_TRIP)
   OR (iHydraulicPSI > PSI_TRIP) THEN

    rValveCmd  := 0.0;
    rIntegral  := 0.0;   (* dump integral so we don't wind up while tripped *)
    rLastError := 0.0;
    (* fall through to output write below *)

ELSE
    (* ---------------- CONTROL MODES ---------------- *)
    CASE iControlMode OF

        0: (* MANUAL - VALVE_POSITION_CMD is driven externally; pass-through.
              In manual the operator/dashboard owns rValveCmd. *)
            ;

        1: (* PID HOLD - drive valve to hold rTargetRPM *)
            rError      := rTargetRPM - rActualRPM;
            rIntegral   := rIntegral + (rError * rDt);
            rDerivative := (rError - rLastError) / rDt;

            (* TODO: real PID math + anti-windup clamp on rIntegral *)
            rValveCmd   := (rKp * rError)
                         + (rKi * rIntegral)
                         + (rKd * rDerivative);

            rLastError  := rError;

        2: (* SWEEP - ramp rTargetRPM across a band, log torque vs rpm *)
            (* TODO: implement RPM sweep schedule (ramp setpoint over time)
               then run the same PID as mode 1 to track it. *)
            ;

    END_CASE;
END_IF;

(* ---------------- OUTPUT CLAMP ---------------- *)
(* Valve command is a physical 0-100%. Clamp before it leaves the PLC. *)
IF rValveCmd > 100.0 THEN
    rValveCmd := 100.0;
END_IF;
IF rValveCmd < 0.0 THEN
    rValveCmd := 0.0;
END_IF;

(* NOTE: rValveCmd is 0-100% here. The Modbus mapping writes it to 40001 as
   0-10000 (x100). Apply that scale in the I/O mapping or just before write. *)

END_PROGRAM
