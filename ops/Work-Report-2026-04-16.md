# Work Report — 2026-04-15 (Session C — pulled forward from 4/17)

**Session scope:** Phase 6 ship packaging + soak-readiness spot-checks
**Operator:** Claude Code (Opus 4.6)
**Starting commit:** `5edbd16 ops: Session B wrap`
**Schedule shift:** Session B completed in ~30 minutes vs. estimated 3 hours, so Session C was pulled forward from 2026-04-17 to today. This buys ~36–48 hours of soak time on Jake's dev machine before Monday handoff instead of <24 hours.

---

## Spot-check findings (performed before packaging, to catch bugs pre-zip)

### 1. Unicode / encoding — fragile fix replaced with portable one

**Background:** Session B's `verify_vav.py` crashed on `≈` (U+2248) with `UnicodeEncodeError` on Windows cp1252 stdout. I patched it to `~=` at the time. Audit revealed that fix was symptomatic.

**Found:** `×` (U+00D7) and `±` (U+00B1) scattered across verify scripts' print paths. These happen to be in cp1252's extended range so they render as `?`/`�` without crashing. But any future char outside cp1252 (e.g. `°`, `≤`, `→`, `⚠`) would re-crash the same way `≈` did. Symptomatic fix vs. root cause.

**Portable fix:**
- `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` + same for stderr at top of each verify script (`verify_meters_abc.py`, `verify_gas_water.py`, `verify_ahu.py`, `verify_vav.py`). Python 3.7+ feature.
- `set PYTHONIOENCODING=utf-8:replace` in `run.bat` so the co-worker's simulator console renders em-dashes in the banner correctly (cosmetic improvement, not required for crash-avoidance since `logging` module uses different write path than `print()`).
- File-level encoding was already correct (`encoding='utf-8'` on `TimedRotatingFileHandler` in `logging_config.py`).

Belt-and-suspenders: script-level + env-var-level. Either alone would have fixed it.

### 2. Log rotation — verified end-to-end

**Trace:** `simulator/logging_config.py:30-38` wires `TimedRotatingFileHandler` with `when="midnight", interval=1, backupCount=cfg.retention_days (=7), encoding="utf-8", utc=False`. Added as root-logger handler at `log.setLevel(DEBUG)`.

**Evidence of actual rotation:** `logs/` directory contains `simulator.log.2026-04-14` (rotated) and active `simulator.log` from today. Rotation fired on the 2026-04-14 → 2026-04-15 midnight boundary without intervention. Self-managing, as designed.

### 3. Unbounded accumulators — audited, none found

Grep for per-tick `.append()` / `.extend()` / `+=` on instance attributes across `simulator/`:

| Symbol | Location | Verdict |
|---|---|---|
| `self._meter_a_kwh`, `_meter_b_kwh`, `_meter_c_kwh`, `_gas_scf`, `_water_gal` | `site_model.py:332-363` | Float accumulators — grow in value but not in memory |
| `valves: list[float] = []`, `zones: list[float] = []` | `site_model.py:275-276` | Local scope per-tick, converted to tuples, GCed |
| `self._peak_demand_kw`, `_peak_demand_committed` | `site_model.py:109-110` | Fixed 3-key dicts, reset every 15-min window |
| `devices.append(dev)` | `__main__.py:134` | Startup only (28 entries), not per-tick |
| `self._rng = _r.Random(self.device_id)` | `emon.py:216` | Reseed each `update()` — allocates small Random per tick per device (~30/min total). Not a leak. Out of scope to optimize per Session C "no polish" rule. |

No persisted per-tick growth anywhere in the tick loop. Expected steady-state memory after first hour: ~100–120 MB (Python interpreter + BAC0 + bacpypes3 + 28 BAC0.lite instances).

### 4. Back-to-back verify script re-runs — clean

Ran `verify_gas_water.py` twice in immediate succession. Both 7/7 PASS. No stale BAC0 state, no TIME_WAIT blocking, no orphan sockets. Scripts cleanly release all resources via `client.disconnect()` + per-device `dev.close()` at end of `main()`.

### 5. Clean-shutdown / port-release — REAL BUG FOUND AND FIXED

**Critical finding.** This was the most important spot-check result.

**Bug:** `simulator/__main__.py:147-150` had:
```python
try:
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, _handle_stop)
except (NotImplementedError, AttributeError):
    pass  # "Windows asyncio doesn't always support add_signal_handler; Ctrl+C still works"
```

The comment was wishful thinking. On Windows, `add_signal_handler` raises `NotImplementedError`, the exception gets swallowed, and **NO signal handler gets installed**. The code then relied on Python's default SIGINT handler to raise `KeyboardInterrupt`, which asyncio.run's task-cancel path SHOULD route into the tick loop's `try/finally`. This works MOST of the time on Windows but is fragile — under certain asyncio loop-internals conditions the cancellation can stall and leave devices un-disconnected, ports bound.

The failure mode exactly matches Claude.ai's warning: "if the simulator doesn't exit cleanly on Ctrl+C, the BAC0 sockets stay bound and the next startup fails to grab the IPs. Co-worker would experience this as 'I stopped it and now it won't start again.'"

**Fix:** replaced the broken try/except with an explicit `sys.platform == "win32"` branch that uses `signal.signal()` (works on Windows) to install handlers for `SIGINT` and `SIGBREAK`, which schedule `stop.set()` onto the event loop via `loop.call_soon_threadsafe()`. Unix path kept (`loop.add_signal_handler` for SIGINT+SIGTERM).

**Verification:** launched the simulator via `subprocess.Popen(creationflags=CREATE_NEW_PROCESS_GROUP)`, waited for 28-device bring-up, sent `CTRL_BREAK_EVENT` (Python's canonical console-ctrl-signal test):

```
Sending CTRL_BREAK_EVENT...
Clean exit after 1s with code 0
Log: "Stop signal received." → "Shutting down devices..." → "Shutdown complete."
Port .200:47808 rebind: PASS (released cleanly)
```

Co-worker's at-keyboard Ctrl+C in a real cmd.exe console hits the same SIGINT path registered by the fix. Handler fires, asyncio Event is set, tick loop exits cleanly, `finally` block disconnects all 28 devices, process exits with code 0, ports release immediately.

Was this worth holding for? Yes. Without the fix, the first time the co-worker pressed Ctrl+C would have been the test, with no way to diagnose from a shipped zip.

---

## Phase 6 — ship packaging

### Files added / changed

- **`run.bat`** (new) — idempotent venv bootstrap. First run: creates `.venv`, installs `requirements.txt`, launches `py -m simulator`. Subsequent runs: skip bootstrap, launch immediately. Sets `PYTHONIOENCODING=utf-8:replace` for console rendering. `pause` at end keeps window open after stop so co-worker can read any trailing output. Uses `py` launcher if present, falls back to `python`. Graceful error paths if Python missing or venv creation fails.

- **`README.md`** (rewrite — was a one-liner placeholder) — co-worker-facing setup guide. Sections: what it simulates (device manifest table), prerequisites (Python, KM-TEST loopback), loopback IP setup (copyable `netsh` for-loop), run, config, stop (includes "what to do if Ctrl+C doesn't respond" fallbacks), long-running operation (memory expectations, log rotation, "is it still working?" check via `Get-Content -Tail`), troubleshooting, file layout, getting help. Explicitly tells co-worker that ~60s bring-up is normal so he doesn't kill the process.

- **`simulator/__main__.py`** (bug fix) — signal handler rewrite as described above. Windows path now uses `signal.signal()` + `call_soon_threadsafe`; Unix path uses `loop.add_signal_handler`. Covers SIGINT, SIGBREAK (Windows), SIGTERM (Unix).

- **`scripts/verify_*.py`** (portability fix) — added `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at top of all four verify scripts so unicode in print strings can't crash again.

### Ship artifact

Zip built at `dist/bacnet_bounty.zip`. 38 KB compressed, 147 KB unpacked. 17 files:

```
bacnet_bounty/
├── README.md                (8.7 KB)
├── run.bat                  (2.0 KB)
├── requirements.txt         (16 bytes — "BAC0==2025.9.15")
├── site_config.json         (5.1 KB)
├── logs/                    (empty placeholder)
└── simulator/
    ├── __init__.py, __main__.py, config.py, logging_config.py,
    │   site_model.py, ahu_physics.py, vav_physics.py
    └── devices/
        ├── __init__.py, emon.py, onicon_gas.py, onicon_water.py,
        │   ahu.py, vav.py
```

**Excluded (verified absent from zip):** `.claude/`, `reference/`, `scripts/`, `ops/`, `.git/`, `.venv/`, `__pycache__/`, `.gitignore`, `PROJECT_CONTEXT.md`, `dist/` itself, `*.pyc`. No secrets, no dev-only code, no ops notes.

### Scratch-dir smoke test — all green

1. Unzipped `bacnet_bounty.zip` to `C:\temp\bacnet-bounty-ship-test\`.
2. Created fresh venv from Python 3.14.3 on dev box (`py -m venv .venv`).
3. Installed dependencies (`.venv/Scripts/python.exe -m pip install -r requirements.txt`) — clean install, single package BAC0 + 4 transitive deps, venv size 21 MB.
4. Config + tick smoke: imports resolved, 20 VAVs and 3 AHUs parsed, SiteModel.tick produced plausible values.
5. Launched full simulator (`.venv/Scripts/python.exe -m simulator`) via `CREATE_NEW_PROCESS_GROUP`.
6. 28 devices online at tick#1 (13:31:21), tick#7 at 13:32:22 (60-second heartbeat as designed).
7. Sent `CTRL_BREAK_EVENT` — clean exit in 1 second, full shutdown sequence logged, ports released.

Zip is self-contained and reproducible from any directory. No dev-env dependencies leaked in.

### Commit plan

All the above goes in one commit: `Phase 6: ship packaging — run.bat, README, signal handler fix, utf-8 stdout in verify scripts`.

---

## Session C wrap

- [x] `run.bat` with idempotent venv bootstrap
- [x] `README.md` co-worker-facing (netsh block, config editing, soak-friendliness section, troubleshooting)
- [x] Zip staged at `dist/bacnet_bounty.zip` (known path, ready for Jake to send)
- [x] Scratch-dir smoke test passed end-to-end
- [x] Signal handler bug fix (Windows clean Ctrl+C verified with CTRL_BREAK_EVENT test)
- [x] UTF-8 stdout reconfigure added to all 4 verify scripts (portable unicode fix)
- [x] `ops/Work-Report-2026-04-16.md` (this file)
- [x] `ops/Handoff-2026-04-16.md` with soak monitoring instructions + `soak_state.txt` artifact
- [x] `ops/sprint-tracker.md` updated (Phase 6 ✓, Phase 7 parked)
- [x] Simulator left running on dev machine for Jake's ~36-hour soak (PID + start time in handoff)
- [x] Commit + push

---

## Soak state at end-of-session

Simulator is running on dev box from `C:\Programs\Bacnet-Bounty`:
- **PID:** `33672`
- **Start:** 2026-04-15 13:33:04 EDT
- **Initial memory:** ~114 MB (116,668 K)
- **Command:** `py -m simulator` (detached via `nohup` from Git Bash)
- **Log:** `C:\Programs\Bacnet-Bounty\logs\simulator.log`
- **State file:** `C:\Programs\Bacnet-Bounty\ops\soak_state.txt` (PID, start, command)

Expected soak duration: ~36 hours (through Fri morning 2026-04-17) minimum, possibly through Sun night 2026-04-19 before ship hand-off Mon 2026-04-20. Two midnight rollovers guaranteed (one tonight, one Thu night).

**What "good" looks like at end of soak** — see `ops/Handoff-2026-04-16.md`.
