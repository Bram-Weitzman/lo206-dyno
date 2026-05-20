# Modbus Register Map — THE CONTRACT

This document defines the Modbus TCP register contract between the **simulator**
(or, later, the **real hardware I/O**) and the **OpenPLC control logic**.

> **This register map is the contract. Neither the simulator nor the PLC
> control logic may be changed without updating this document first.**

Transport: **Modbus TCP, port 502.** The simulator hosts the server; OpenPLC is
the master/client.

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
- **40001 VALVE_POSITION_CMD** — the single actuator output. Scaled x100 so the
  controller can command 0.01% resolution without floats on the wire. The sim
  applies valve *lag* before this becomes the actual position (see 30005).
- **40002 TARGET_RPM** — only meaningful in modes 1 and 2. Capped at 6500 to
  stay below the safety RPM limit.
- **40003 CONTROL_MODE** — manual passes VALVE_POSITION_CMD straight through;
  PID hold drives the valve to hold TARGET_RPM; sweep ramps RPM across a band.
- **40004 SAFETY_ENABLE** — master run/stop. When 0, the PLC safety interlock
  forces the valve to 0 regardless of mode. This is software e-stop; a hardware
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

### Notes
- **30001 ENGINE_RPM** — range extends to 7000 (above the 6500 command cap and
  6100 nominal max) so the controller can *see* an overspeed condition and act
  on it. Do not clamp this at the command limit.
- **30002 TORQUE_FTLBS_x10** — scaled x10 to carry one decimal place. The sim
  derives this from the torque curve at the current RPM and load.
- **30003 HYDRAULIC_PSI** — brake circuit pressure. Feeds the safety interlock
  (over-pressure trip).
- **30004 HEAD_TEMP_C** — thermal model output; slow-moving. Future thermal
  derate logic may use this.
- **30005 VALVE_POSITION_ACT** — the *actual* valve position after lag/hysteresis,
  distinct from the commanded 40001. The control loop should close on this.
- **30006 AFR_x10** — **reserved.** No wideband O2 sensor in Phase 1; the sim
  may emit a nominal 147 (14.7:1) placeholder. Do not build control logic that
  depends on this yet.
- **30007 SIM_STATUS** — health/heartbeat. `2 = fault` should cause the PLC to
  treat the run as invalid.

---

## Ownership summary

| Direction          | Registers      | Writer        | Reader |
|--------------------|----------------|---------------|--------|
| Commands (out)     | 40001 - 40004  | PLC           | Sim/HW |
| Telemetry (in)     | 30001 - 30007  | Sim/HW        | PLC    |

Any change to address, scaling, range, or ownership above is a **contract
change**: update this file first, then update both sides to match.
