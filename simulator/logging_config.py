"""Centralized logging setup: console at INFO, rotating file at DEBUG."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .config import LoggingSection


def setup_logging(cfg: LoggingSection) -> None:
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "simulator.log"

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, cfg.console_level.upper(), logging.INFO))
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=cfg.retention_days,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(getattr(logging, cfg.file_level.upper(), logging.DEBUG))
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Quiet bacpypes3 at INFO on console (it's noisy at DEBUG); full trace still goes to file
    logging.getLogger("bacpypes3").setLevel(logging.WARNING)
