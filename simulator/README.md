# Simulator

The Python simulator stands in for the LO206 engine and the hydraulic brake
load during sim-first development. It runs a Modbus TCP server that speaks the
contract in [../plc/register_map.md](../plc/register_map.md), so the OpenPLC
control program can connect to it exactly as it will connect to real hardware.

## Layout

| File                 | Role                                               |
|----------------------|----------------------------------------------------|
| `modbus_map.py`      | Register contract as named constants (single source of truth) |
| `torque_curve.py`    | LO206 Black Slide (.520) torque lookup + interpolation |
| `engine_sim.py`      | I/O-agnostic engine + hydraulic-brake physics model |
| `modbus_server.py`   | pymodbus async TCP server mapping the model to registers |
| `tests/`             | pytest suite                                       |

## Setup

The dev VM already has a system venv at `/opt/dyno-venv` with the dependencies
installed. To recreate elsewhere:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source /opt/dyno-venv/bin/activate
# from repo root:
./scripts/start_sim.sh
# or directly:
python modbus_server.py
```

The server listens on `0.0.0.0:502` (standard Modbus TCP). **Port note:** binding
502 needs root or `CAP_NET_BIND_SERVICE`; an unprivileged process automatically
falls back to **5020** and logs the change. Point the OpenPLC Modbus master at
the VM's IP on whichever port the startup log reports. A 10 ms physics loop runs
alongside the server; a heartbeat line prints every 5 s.

## Register contract

`modbus_map.py` mirrors `../plc/register_map.md`:

- **Input registers (30001-30007):** sensors the sim writes (RPM, torque x10,
  PSI, CHT, valve-actual x100, AFR x10, status).
- **Holding registers (40001-40004):** commands the PLC writes (valve-cmd x100,
  target RPM, control mode, safety-enable).

## Test

```bash
source /opt/dyno-venv/bin/activate
cd simulator
pytest -v
```

## Status

Implemented and smoke-tested end to end over Modbus TCP:

- `torque_curve.py` — Black Slide (.520) data + numpy interpolation, with
  zero-below-2000 / hold-above-6100 clamps.
- `engine_sim.py` — engine inertia (J=0.05 kg.m^2), hydraulic pump load
  (gain 12 ft-lbs), first-order valve lag (tau=120 ms), CHT thermal model, and
  overpressure/overtemp safety trips. Physics placeholders are flagged
  `# TODO: calibrate against real hardware`.
- `modbus_server.py` — pymodbus 3.13 async server sharing a live datastore with
  the physics loop.

Next: PID tuning happens on the PLC side (see `../plc/`), against this sim.
