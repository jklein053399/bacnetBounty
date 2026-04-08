# CLAUDE.md — BACnet Simulator

## What This Is
BAC0-based BACnet device simulator for testing station generation and parser validation without live hardware. Supports multi-vendor device models, physics simulation, and fault injection.

## Architecture

```
tools/simulator/
├── run_simulator.py           Main launcher
├── test_client.py             BACnet client tester
├── generate_trends.py         Trend data generator
├── devices/                   Device models (vendor-specific point definitions)
├── scenarios/                 Test scenarios (combine devices + configs)
├── simulation/                Physics models (AHU, zone, plant, G36 controller, faults)
├── trends/                    Pre-generated CSV trend data
├── tests/                     Simulator tests
│   └── test-data/             Test fixtures
└── output/                    GITIGNORED
    └── logs/                  Simulator runtime logs
```

## Key Conventions

### Port 47808 only
Never use alternate BACnet ports. Discovery only works on 47808. Use separate IPs via the KM-TEST Loopback adapter for multiple simulated devices.

### Loopback adapter setup
Ethernet 11 KM-TEST Loopback: add IPs before launch, reserve +1 IP for Workbench binding.

### Always kill and restart after code changes
No need to ask — kill existing simulator process, restart fresh. Exception: user explicitly says keep it running.

### Launch detached
```bash
nohup py scenarios/script.py > output/logs/simulator.log 2>&1 &
```
Don't use `run_in_background` — causes stale task notifications. Use timeout instead.

### Device models are vendor-specific (that's fine)
The device model files define vendor-specific point lists. Everything else (simulation, scenarios, client) is vendor-agnostic.

## Dependencies
- BAC0 (BACnet stack)
- Python 3.10+
