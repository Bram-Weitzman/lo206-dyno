"""LO206 engine + hydraulic-load physics model.

This module models the *engine under test* and the *hydraulic brake load* well
enough to exercise the PLC control loop end to end. It is the thing that stands
in for real hardware during sim-first development. It produces the telemetry the
PLC reads (RPM, torque, pressure, temp, actual valve position) and consumes the
command the PLC writes (valve position).

It deliberately knows NOTHING about Modbus. ``modbus_server.py`` wraps this and
maps the model's state onto the register map in ``plc/register_map.md``.

TODO (implementation backlog)
-----------------------------
- [ ] Engine inertia: integrate net torque (engine torque - brake torque) to
      get angular acceleration, then RPM. Need a real flywheel/crank inertia
      estimate (placeholder below).
- [ ] Brake torque model: map hydraulic valve position + pressure to a
      resisting torque. Needs a pump/orifice curve.
- [ ] Valve lag: first-order lag between commanded and actual valve position
      (50-200 ms time constant per docs/sim_to_real.md).
- [ ] Valve hysteresis / deadband: real proportional valves don't track
      perfectly; model backlash.
- [ ] Thermal model: head temp rises with sustained load, cools toward ambient.
- [ ] Fault injection: overspeed, over-pressure, sensor dropout for testing the
      PLC safety interlocks.
"""

from torque_curve import interpolate_torque

# --- Placeholder physical constants (REPLACE with measured/estimated values) ---
CRANK_INERTIA_KGM2 = 0.01   # TODO: real rotating inertia of crank+flywheel+clutch
VALVE_LAG_TAU_S = 0.10      # TODO: measure actual proportional-valve time constant
AMBIENT_TEMP_C = 25.0
MAX_RPM_NOMINAL = 6100      # governed class max; see README hardware target


class DynoEngine:
    """Lumped model of the LO206 engine coupled to a hydraulic brake.

    State is advanced in fixed time steps by :meth:`tick`. The Modbus server
    pushes valve commands in via :meth:`set_valve_position` and pulls telemetry
    out via the getters.
    """

    def __init__(self, dt: float = 0.05):
        self.dt = dt                       # integration step (s)
        self._rpm = 0.0
        self._valve_cmd = 0.0              # commanded 0-100 %
        self._valve_act = 0.0             # actual 0-100 % (after lag)
        self._head_temp_c = AMBIENT_TEMP_C
        self._hydraulic_psi = 0.0
        self._status = 0                  # 0 stopped, 1 running, 2 fault

    # -- inputs (from PLC via Modbus) --
    def set_valve_position(self, percent: float) -> None:
        """Set the commanded valve position (0-100 %)."""
        self._valve_cmd = max(0.0, min(100.0, percent))

    # -- simulation step --
    def tick(self) -> None:
        """Advance the model by one ``dt``.

        TODO: this is a stub. The real loop will:
          1. Apply first-order valve lag: valve_act -> valve_cmd over VALVE_LAG_TAU_S.
          2. Compute engine torque from interpolate_torque(self._rpm).
          3. Compute brake (resisting) torque from valve_act + hydraulic_psi.
          4. Integrate net torque / CRANK_INERTIA_KGM2 to update rpm.
          5. Update hydraulic_psi from valve_act and flow.
          6. Update head_temp_c from load and cooling.
        """
        # Placeholder so the server has *something* coherent to publish:
        engine_torque = interpolate_torque(self._rpm)
        _ = engine_torque  # used once the integrator below is implemented
        # (no state advance yet — see TODO)

    # -- outputs (to PLC via Modbus) --
    def get_rpm(self) -> float:
        return self._rpm

    def get_torque(self) -> float:
        """Current engine torque (ft-lbs) at the present RPM."""
        return interpolate_torque(self._rpm)

    def get_valve_actual(self) -> float:
        return self._valve_act

    def get_hydraulic_psi(self) -> float:
        return self._hydraulic_psi

    def get_head_temp_c(self) -> float:
        return self._head_temp_c

    def get_status(self) -> int:
        return self._status


if __name__ == "__main__":
    eng = DynoEngine()
    eng.set_valve_position(50.0)
    eng.tick()
    print(f"rpm={eng.get_rpm():.0f} torque={eng.get_torque():.2f} "
          f"valve={eng.get_valve_actual():.1f}% status={eng.get_status()}")
