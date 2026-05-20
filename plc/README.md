# PLC — OpenPLC control logic

This directory holds the dyno control program in IEC 61131-3 Structured Text
and the Modbus register contract it depends on.

| File               | Role                                                    |
|--------------------|---------------------------------------------------------|
| `dyno_control.st`  | PID speed control + safety interlocks (Structured Text) |
| `register_map.md`  | **The contract** — Modbus register definitions          |

## Prerequisites

- OpenPLC runtime installed and running on `dyno-dev` (service `openplc`).
- Web UI reachable at `http://10.20.99.55:8080`.
- The simulator (or real hardware) running and reachable as a Modbus TCP slave.

## Load and run

1. Open the OpenPLC web UI: `http://10.20.99.55:8080`
   (default credentials are OpenPLC's `openplc` / `openplc` — change them).
2. **Programs -> Upload Program** -> select `dyno_control.st`, give it a name,
   then **Compile**. Fix any compile errors before continuing.
3. **Settings** -> enable Modbus, then configure the master so the located
   variables map onto the registers documented in `register_map.md`:
   - Holding registers 40001-40004 are written by the PLC.
   - Input registers 30001-30007 are read by the PLC.
   - Point the master at the simulator host/IP, port 502.
4. **Run** the program. Watch the **Monitoring** page to confirm live values.

## Wiring the contract

The variable-to-register mapping is documented at the top of `dyno_control.st`
and authoritatively in `register_map.md`. If a value does not appear or reads
zero, check the offset convention (4xxxx/3xxxx vs zero-based wire offsets) in
the OpenPLC slave config first — that is the most common gotcha.

## Safety note

The Structured Text safety interlock (software e-stop, overspeed, over-pressure)
is the *first* block evaluated each scan and forces the valve closed. On real
hardware this software interlock does **not** replace a hardwired physical
e-stop — that is a separate, non-negotiable circuit.
