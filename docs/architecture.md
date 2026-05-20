# Architecture

## System overview

The LO206 dyno is a closed-loop speed/load control system. An engine spins
against a **hydraulic brake**; a **proportional valve** sets how much the brake
resists; a **controller** modulates that valve to hold a target RPM (or sweep
across a band) while measuring torque. Everything is orchestrated by a Raspberry
Pi running **OpenPLC**.

```
            commands (Modbus holding regs 40001-40004)
   +-----------+  ------------------------------------------>  +-----------+
   |  OpenPLC  |                                                | Sim or HW |
   | (control) |  <------------------------------------------  |  (I/O)    |
   +-----------+   telemetry (Modbus input regs 30001-30007)    +-----------+
        ^                                                             |
        | Modbus TCP read                                  physical / modeled
        |                                                  engine + hydraulics
        v
   +-----------+
   | Dashboard |  (live view, run control, logging)
   +-----------+
```

## The sim-to-real swap principle

The single most important design decision: **the control logic is
I/O-agnostic, and the Modbus register map is the only contract.** During
development the "I/O" box above is a Python physics simulator. When hardware is
built, that box becomes real ADCs, sensors, and a valve driver. The OpenPLC
control program is **byte-for-byte unchanged** across that swap — it only ever
reads and writes Modbus registers.

This de-risks the project: we tune the PID, exercise the safety interlocks, and
shake out the register mapping against a sim that can be run thousands of times,
fault-injected, and reset instantly — long before spending money on a valve.

## Why Modbus TCP

- **Ubiquitous in industrial control** and natively supported by OpenPLC.
- **Dead simple**: 16-bit registers, well-understood function codes, trivial to
  implement on the simulator side with `pymodbus`.
- **Decouples sim from hardware**: the same register addresses serve both, which
  is exactly the contract we want.
- **Network-transparent**: sim can run on the same Pi or a separate dev box; the
  dashboard can read the same registers.

The cost — Modbus has no built-in security and modest throughput — is a non-issue
on an isolated lab network at our update rates.

## Why OpenPLC

- Implements the **IEC 61131-3** standard (Structured Text, Ladder, etc.), so
  the control logic is written in a real, portable PLC language rather than ad
  hoc scripts.
- **Runs on a Raspberry Pi** and on plain Linux for development.
- **Free and open source.**
- Built-in Modbus master/slave and a web UI for upload/compile/monitor.

## Real-time limitations (and why they are acceptable)

Linux + the Pi + OpenPLC is **soft** real-time, not hard real-time. Scan timing
can jitter by milliseconds under load. That would be disqualifying for, say,
motor commutation — but here the **actuator is slow**: a hydraulic proportional
valve responds in roughly **50-200 ms**. Control decisions at a 20-50 ms scan
with occasional jitter are comfortably faster than the plant can move. The
safety interlock runs every scan and fails closed, and a hardwired physical
e-stop (independent of software) is the real backstop. So soft real-time is
acceptable for this application.

## Data flow

```
  [engine physics] --tick--> [model state] --write--> [input registers 30001-30007]
                                                              |
                                                        Modbus TCP
                                                              v
                                                     [OpenPLC reads sensors]
                                                              |
                                                      PID + safety logic
                                                              v
                                                  [OpenPLC writes 40001-40004]
                                                              |
                                                        Modbus TCP
                                                              v
   [model reads valve cmd] <--read-- [holding registers] <---+
```

## Open design decisions

- **Valve driver**: 0-10V analog amp card vs PWM + MOSFET. See
  `sim_to_real.md`. Affects the analog-out signal chain.
- **Dashboard data path**: direct Modbus reads vs a logging service to
  SQLite/PostgreSQL.
- **Scan rate**: target 20-50 ms; to be confirmed once the PID is tuned.
- **Sensor fusion / filtering**: how much smoothing on RPM and torque before the
  PID sees them.
- **Slide-config library**: digitizing the non-Black-Slide torque curves (see
  `bom.md`).
