#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║           AEGIS  —  install_shortcut.py                  ║
║   Registers Super+N → launch AEGIS in a terminal.        ║
╚══════════════════════════════════════════════════════════╝

Run once:
    python3 install_shortcut.py

Uninstall:
    python3 install_shortcut.py --uninstall
"""

import os, sys, shutil, argparse, subprocess, json, time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent.resolve()
AGENT_SCRIPT = SCRIPT_DIR / "aegis_agent.py"

# Always use the SYSTEM python3 (not venv) so the shortcut
# works when launched from outside the venv via Super+N.
# We wrap it in an activation line inside the terminal command.
VENV_ACTIVATE = SCRIPT_DIR / "venv" / "bin" / "activate"
PYTHON_BIN    = sys.executable          # venv python, used for the run cmd

TERMINALS = [
    "gnome-terminal", "xterm", "konsole",
    "xfce4-terminal", "alacritty", "kitty", "tilix",
]

# DBUS address helper — needed when running inside venv / sudo
def _dbus_env() -> dict:
    """Return env dict with DBUS_SESSION_BUS_ADDRESS set if possible."""
    env = os.environ.copy()
    if "DBUS_SESSION_BUS_ADDRESS" in env:
        return env
    # Try to discover it from a running gnome-session process
    try:
        uid = os.getuid()
        result = subprocess.run(
            f"grep -z DBUS_SESSION_BUS_ADDRESS /proc/$(pgrep -u {uid} gnome-session | head -1)/environ 2>/dev/null | tr -d '\\0'",
            shell=True, capture_output=True, text=True, timeout=3
        )
        if result.stdout.strip():
            key, val = result.stdout.strip().split("=", 1)
            env[key] = val
    except Exception:
        pass
    return env
