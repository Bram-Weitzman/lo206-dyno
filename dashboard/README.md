# Dashboard

A Next.js web dashboard for live dyno telemetry, run control, and logged-run
review. **Not scaffolded yet** — this directory is a placeholder for the
Phase 2+ work.

## Planned scope

- Live telemetry (RPM, torque, hydraulic pressure, head temp, valve position)
  streamed from the running dyno.
- Run control: start/stop, mode select (manual / PID hold / sweep), target RPM.
- Logged runs: torque-vs-RPM curves, comparison across runs and slide configs.

## Open question

How the dashboard gets data is undecided: read Modbus directly, or read from a
logging service that persists to SQLite/PostgreSQL. See `../CLAUDE.md` open
questions and `../docs/architecture.md`.

## When scaffolding

```bash
# from this directory, once we commit to it:
npx create-next-app@latest .
```

Until then, this README and `.gitkeep` hold the directory in git.
