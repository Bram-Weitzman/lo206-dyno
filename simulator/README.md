# Simulator

The Python simulator stands in for the LO206 engine and the hydraulic brake
load during sim-first development. It runs a Modbus TCP server that speaks the
contract in [../plc/register_map.md](../plc/register_map.md), so the OpenPLC
control program can connect to it exactly as it will connect to real hardware.

## Layout

| File                 | Role                                               |
|----------------------|----------------------------------------------------|
| `engine_sim.py`      | I/O-agnostic engine + brake physics model          |
| `torque_curve.py`    | LO206 Black Slide torque lookup + interpolation     |
| `modbus_server.py`   | Modbus TCP server mapping the model to registers   |
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

The server listens on `0.0.0.0:502` (standard Modbus TCP). Point the OpenPLC
Modbus master at the VM's IP, port 502.

## Test

```bash
source /opt/dyno-venv/bin/activate
cd simulator
pytest
```

## Status

`torque_curve.py` is functional. `engine_sim.py` and `modbus_server.py` are
stubs with a TODO backlog at the top of each file — physics integration and the
pymodbus server are the next implementation steps.
