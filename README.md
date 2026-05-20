# LO206 Dyno

A hybrid hydraulic/mechanical engine dynamometer for the **Briggs & Stratton
LO206** kart racing engine, built around a Raspberry Pi running **OpenPLC**.
This repository holds the full project: a Python **simulator** that models the
engine and load, the **PLC control logic** (IEC 61131-3 Structured Text), a
web **dashboard**, and the **documentation**. The guiding principle is
*sim-first*: we validate the entire control system against a simulated engine
before a single bolt of hardware is purchased, then swap the simulated I/O for
real sensors and a real valve without touching the control logic.

## Architecture

```
   +-------------------+        Modbus TCP         +-------------------+
   |    Simulator      | <-----------------------> |      OpenPLC      |
   |  (Python, this    |   holding + input regs    |  (IEC 61131-3 ST  |
   |   repo)           |   on port 502             |   PID + safety)   |
   |                   |                           |                   |
   | engine physics,   |                           | reads sensors,    |
   | torque curve,     |                           | writes valve cmd  |
   | valve lag, faults |                           |                   |
   +-------------------+                           +---------+---------+
                                                             |
                                                             | Modbus TCP
                                                             v
                                                   +-------------------+
                                                   |    Dashboard      |
                                                   |  (Next.js, later) |
                                                   | live telemetry,   |
                                                   | run control, logs |
                                                   +-------------------+
```

The simulator and the real hardware present the **same Modbus register map**
to the PLC. Only the I/O source changes; the control code does not.

## Hardware target

| Spec            | Value                          |
|-----------------|--------------------------------|
| Engine          | Briggs & Stratton LO206        |
| Peak torque     | ~10 ft-lbs                     |
| Peak power      | ~8.8 HP                        |
| Max RPM         | ~6100 RPM (governed class)     |
| Load            | Hydraulic brake (proportional valve) |

## Getting started

There are three independent things you can run. Pick the one you need.

### 1. Run the simulator

```bash
# on the dev VM, the venv lives at /opt/dyno-venv
source /opt/dyno-venv/bin/activate
./scripts/start_sim.sh
```

The simulator starts a Modbus TCP server (default `0.0.0.0:502`) that the PLC
connects to. See [simulator/README.md](simulator/README.md).

### 2. Load the PLC program

Open the OpenPLC web UI (`http://<dyno-dev>:8080`), upload
`plc/dyno_control.st`, compile, and start the runtime. Point its Modbus master
at the simulator. See [plc/README.md](plc/README.md).

### 3. Run the dashboard

Not scaffolded yet. See [dashboard/README.md](dashboard/README.md).

## Deeper reading

- [docs/architecture.md](docs/architecture.md) — system design and rationale
- [plc/register_map.md](plc/register_map.md) — **the contract** between sim and PLC
- [docs/sim_to_real.md](docs/sim_to_real.md) — migrating from sim to real hardware
- [docs/bom.md](docs/bom.md) — hardware bill of materials
- [docs/blog/01_why_a_dyno.md](docs/blog/01_why_a_dyno.md) — project blog

## The core principle

> The simulator and the real dyno share **identical** control code. The only
> thing that differs is where the Modbus register values come from — a Python
> physics model today, real ADCs and a valve driver tomorrow. If you find
> yourself special-casing "sim vs real" in the control logic, stop: the
> register map is the contract, and it is the only contract.
