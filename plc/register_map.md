# Modbus Register Map — THE CONTRACT

This document defines the Modbus TCP register contract between the **simulator**
(or, later, the **real hardware I/O**) and the **OpenPLC control logic**.

> **This register map is the contract. It is mirrored in code by
> `simulator/modbus_map.py`. Neither the simulator nor the PLC control logic may
> be changed without updating this document and `modbus_map.py` together.**

Transport: **Modbus TCP.** The simulator hosts the server; OpenPLC is the
master/client. The server prefers the standard port **502** and automatically
falls back to **5020** when 502 is not bindable by an unprivileged process
(see `simulator/modbus_server.py`). **Point the OpenPLC Modbus master at
whichever port the simulator logged on startup** — 5020 in the common
(non-root) case.

A note on the addressing convention: addresses are written in the classic
4xxxx / 3xxxx "data model" notation. On the wire these are zero-based offsets
(e.g. `40001` = holding register offset `0`, `30001` = input register offset
`0`). Confirm the offset convention in the OpenPLC slave configuration when
wiring this up.

---

## Holding Registers — PLC writes, simulator reads

These carry commands *from* the controller *to* the engine/load model.
**Owner: PLC** (the PLC is the only writer; the sim must treat these as
read-only inputs).

| Address | Name               | Type   | Range       | Units / scaling                          |
|---------|--------------------|--------|-------------|------------------------------------------|
| 40001   | VALVE_POSITION_CMD | uint16 | 0 - 10000   | Commanded valve position, scaled 0.0-100.0% (10000 = 100.00%) |
| 40002   | TARGET_RPM         | uint16 | 0 - 6500    | Target engine RPM for PID/sweep modes    |
| 40003   | CONTROL_MODE       | uint16 | 0 - 2       | 0 = manual, 1 = PID hold, 2 = sweep      |
| 40004   | SAFETY_ENABLE      | uint16 | 0 - 1       | 0 = e-stop (force valve closed), 1 = run |

### Notes
- **40001 VALVE_POSITION_CMD** — the single actuator output, and the only
  holding register the PLC *computes*. Scaled x100 so the controller can command
  0.01% resolution without floats on the wire. The sim applies valve *lag*
  before this becomes the actual position (see 30005).
- **40002 TARGET_RPM** — operator setpoint; only meaningful in modes 1 and 2.
  Capped at 6500 to stay below the safety RPM limit.
- **40003 CONTROL_MODE** — operator-selected. Manual passes VALVE_POSITION_CMD
  straight through; PID hold drives the valve to hold TARGET_RPM; sweep ramps
  RPM across a band. There is no separate "engine enable" register —
  SAFETY_ENABLE is the master run/stop.
- **40004 SAFETY_ENABLE** — master run/stop. When 0, the PLC safety interlock
  forces the valve to 0 regardless of mode. The PLC interlock will also **drive
  this to 0 itself** on a latched fault. This is software e-stop; a hardware
  e-stop is a separate, non-negotiable circuit on the real rig.

---

## Input Registers — simulator writes, PLC reads

These carry sensed values *from* the engine/load model *to* the controller.
**Owner: simulator** (on real hardware, owner becomes the sensor I/O layer).
The PLC must treat these as read-only.

| Address | Name               | Type   | Range       | Units / scaling                                   |
|---------|--------------------|--------|-------------|---------------------------------------------------|
| 30001   | ENGINE_RPM         | uint16 | 0 - 7000    | Engine speed, RPM (1:1)                           |
| 30002   | TORQUE_FTLBS_x10   | uint16 | 0 - 150     | Torque, scaled x10 (105 = 10.5 ft-lbs)            |
| 30003   | HYDRAULIC_PSI      | uint16 | 0 - 1500    | Hydraulic brake pressure, PSI (1:1)               |
| 30004   | HEAD_TEMP_C        | uint16 | 0 - 300     | Cylinder head temperature, degrees C (1:1)        |
| 30005   | VALVE_POSITION_ACT | uint16 | 0 - 10000   | Actual valve position, scaled 0.0-100.0% (reflects lag) |
| 30006   | AFR_x10            | uint16 | 100 - 200   | Air/fuel ratio, scaled x10 (147 = 14.7) — reserved |
| 30007   | SIM_STATUS         | uint16 | 0 - 2       | 0 = stopped, 1 = running, 2 = fault               |
| 30008   | LIMITER_ACTIVE     | uint16 | 0 - 1       | 0 = limiter released, 1 = rev limiter cutting spark |

### Notes
- **30001 ENGINE_RPM** — the **process variable** the speed PID closes on.
  Range extends to 7000 (above the 6500 command cap and 6100 nominal max) so the
  controller can *see* an overspeed condition and act on it. Do not clamp this at
  the command limit.
- **30002 TORQUE_FTLBS_x10** — scaled x10 to carry one decimal place. The sim
  derives this from the torque curve at the current RPM and load. Logged by the
  PLC; not used in the control law.
- **30003 HYDRAULIC_PSI** — brake circuit pressure. Feeds the safety interlock
  (over-pressure trip).
- **30004 HEAD_TEMP_C** — thermal model output; slow-moving (degC, 1:1 — **not**
  scaled). Feeds the over-temperature trip.
- **30005 VALVE_POSITION_ACT** — the *actual* valve position after lag, distinct
  from the commanded 40001. Telemetry today; available as feedback for an
  optional inner valve-position loop (not implemented — the speed loop closes on
  30001, not on this).
- **30006 AFR_x10** — **reserved.** No wideband O2 sensor in Phase 1; the sim
  may emit a nominal 147 (14.7:1) placeholder. Do not build control logic that
  depends on this yet.
- **30007 SIM_STATUS** — health/heartbeat. `2 = fault` causes the PLC to latch a
  fault, close the valve, and clear SAFETY_ENABLE.
- **30008 LIMITER_ACTIVE** — read-only limiter telemetry. `1` while the sim's
  rev limiter is cutting spark (RPM in the 6100+ limiter band, released below
  6000 with hysteresis — see `simulator/engine_sim.py`). The PLC must treat
  this as read-only and **must not** branch its control law on it; it exists
  so the host/logger can flag and exclude limiter-active samples from the
  power curve. Not a fault — distinct from SIM_STATUS.

---

## Safety trip limits (PLC- and sim-enforced)

These are physical-plant limits, not registers. They live in
`simulator/modbus_map.py` as the single source of truth and are enforced **on
both sides**: the sim trips and sets `SIM_STATUS = 2`, and the PLC interlock
independently trips on the same thresholds (defense-in-depth — the PLC does not
trust the status word alone).

| Limit                  | Value     | Source constant         | Checked against |
|------------------------|-----------|-------------------------|-----------------|
| Overspeed              | 6500 RPM  | (PLC `RPM_TRIP_RPM`)    | 30001 ENGINE_RPM |
| Over-pressure          | 750 PSI   | `OVERPRESSURE_TRIP_PSI` | 30003 HYDRAULIC_PSI |
| Over-temperature       | 250 °C    | `OVERTEMP_TRIP_C`       | 30004 HEAD_TEMP_C |

> The PLC trip thresholds are flagged `(* TODO: calibrate against real hardware *)`
> in `dyno_control.st`. Tune them on the sim, then verify against the real rig.

---

## How the implemented control logic uses these

`plc/dyno_control.st` binds:

| Role             | Register                 |
|------------------|--------------------------|
| Process variable | 30001 ENGINE_RPM         |
| Setpoint         | 40002 TARGET_RPM         |
| Control output   | 40001 VALVE_POSITION_CMD |
| Mode select      | 40003 CONTROL_MODE       |
| Master enable    | 40004 SAFETY_ENABLE      |
| Fault input      | 30007 SIM_STATUS         |
| Trip inputs      | 30003 PSI, 30004 CHT, 30001 RPM |

---

## Ownership summary

| Direction          | Registers      | Writer        | Reader |
|--------------------|----------------|---------------|--------|
| Commands (out)     | 40001 - 40004  | PLC           | Sim/HW |
| Telemetry (in)     | 30001 - 30008  | Sim/HW        | PLC    |

Any change to address, scaling, range, or ownership above is a **contract
change**: update this file and `simulator/modbus_map.py` first, then update both
sides to match.
