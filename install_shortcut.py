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

# ── Run helper (with timeout + dbus env) ─────────────────
def run(cmd: str, timeout: int = 8) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout, env=_dbus_env()
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 1, "", "timeout")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


# ── Terminal launcher command ─────────────────────────────
def find_terminal() -> str | None:
    for t in TERMINALS:
        if shutil.which(t):
            return t
    return None

def build_exec_cmd(terminal: str) -> str:
    # If venv exists, activate it then run agent
    if VENV_ACTIVATE.exists():
        inner = f"source {VENV_ACTIVATE} && python3 {AGENT_SCRIPT}"
    else:
        inner = f"{PYTHON_BIN} {AGENT_SCRIPT}"

    launchers = {
        "gnome-terminal": f"gnome-terminal -- bash -c '{inner}; exec bash'",
        "xterm":          f"xterm -e 'bash -c \"{inner}; exec bash\"'",
        "konsole":        f"konsole -e bash -c '{inner}'",
        "xfce4-terminal": f"xfce4-terminal -e 'bash -c \"{inner}\"'",
        "alacritty":      f"alacritty -e bash -c '{inner}'",
        "kitty":          f"kitty bash -c '{inner}'",
        "tilix":          f"tilix -e 'bash -c \"{inner}\"'",
    }
    return launchers.get(terminal, f"{terminal} -e 'bash -c \"{inner}\"'")


# ══════════════════════════════════════════════════════════
#  METHOD 1 — dconf  (fastest, no dbus hang)
# ══════════════════════════════════════════════════════════
DCONF_BASE = "/org/gnome/settings-daemon/plugins/media-keys"
DCONF_PATH = f"{DCONF_BASE}/custom-keybindings/aegis/"

def install_dconf(exec_cmd: str) -> bool:
    """Write keybinding directly via dconf (bypasses gsettings dbus hang)."""
    if not shutil.which("dconf"):
        return False

    print("  Trying dconf (direct write)...")

    # Read existing list
    r = run(f"dconf read {DCONF_BASE}/custom-keybindings")
    raw = r.stdout.strip()

    if not raw or raw in {"@as []", "[]"}:
        existing = []
    else:
        # Parse GVariant string array  ['a', 'b', ...]
        existing = [x.strip().strip("'\"")
                    for x in raw.strip("[]").split(",")
                    if x.strip().strip("'\"")] 

    if DCONF_PATH not in existing:
        existing.append(DCONF_PATH)

    new_list = "[" + ", ".join(f"'{p}'" for p in existing) + "]"

    cmds = [
        f"dconf write {DCONF_BASE}/custom-keybindings \"{new_list}\"",
        f"dconf write {DCONF_PATH}name    \"'AEGIS Agent'\"",
        f"dconf write {DCONF_PATH}command \"'{exec_cmd}'\"",
        f"dconf write {DCONF_PATH}binding \"'<Super>n'\"",
    ]
    for cmd in cmds:
        r = run(cmd, timeout=5)
        if r.returncode != 0:
            print(f"  [dconf] failed on: {cmd}")
            print(f"  stderr: {r.stderr.strip()}")
            return False

    return True


def uninstall_dconf():
    if not shutil.which("dconf"):
        return
    r = run(f"dconf read {DCONF_BASE}/custom-keybindings")
    raw = r.stdout.strip()
    if not raw:
        return
    existing = [x.strip().strip("'\"")
                for x in raw.strip("[]").split(",")
                if x.strip().strip("'\"") and "aegis" not in x]
    new_list = "[" + ", ".join(f"'{p}'" for p in existing) + "]"
    run(f"dconf write {DCONF_BASE}/custom-keybindings \"{new_list}\"")
    run(f"dconf reset -f {DCONF_PATH}")


# ══════════════════════════════════════════════════════════
#  METHOD 2 — gsettings  (with timeout protection)
# ══════════════════════════════════════════════════════════

def install_gsettings(exec_cmd: str) -> bool:
    base  = "org.gnome.settings-daemon.plugins.media-keys"
    cbase = f"{base}.custom-keybinding"
    path  = DCONF_PATH

    print("  Trying gsettings (timeout=8s)...")

    r = run(f"gsettings get {base} custom-keybindings", timeout=8)
    if r.stderr == "timeout":
        print("  [gsettings] timed out — dbus not reachable from this shell")
        return False

    raw = r.stdout.strip()
    if raw in {"@as []", "[]", "''", ""}:
        current_list = []
    else:
        current_list = [x.strip().strip("'\"")
                        for x in raw.strip("[]").split(",")
                        if x.strip().strip("'\"")]

    if path not in current_list:
        current_list.append(path)

    new_list = "[" + ", ".join(f"'{p}'" for p in current_list) + "]"

    cmds = [
        f"gsettings set {base} custom-keybindings \"{new_list}\"",
        f"gsettings set {cbase}:{path} name    'AEGIS Agent'",
        f"gsettings set {cbase}:{path} command '{exec_cmd}'",
        f"gsettings set {cbase}:{path} binding '<Super>n'",
    ]
    for cmd in cmds:
        r = run(cmd, timeout=8)
        if r.stderr == "timeout" or r.returncode != 0:
            print(f"  [gsettings] failed: {r.stderr.strip()}")
            return False

    return True


def uninstall_gsettings():
    base = "org.gnome.settings-daemon.plugins.media-keys"
    path = DCONF_PATH
    r = run(f"gsettings get {base} custom-keybindings", timeout=8)
    if r.stderr == "timeout":
        return
    raw = r.stdout.strip()
    existing = [x.strip().strip("'\"")
                for x in raw.strip("[]").split(",")
                if x.strip().strip("'\"") and "aegis" not in x]
    new_list = "[" + ", ".join(f"'{p}'" for p in existing) + "]"
    run(f"gsettings set {base} custom-keybindings \"{new_list}\"", timeout=8)


# ══════════════════════════════════════════════════════════
#  METHOD 3 — xbindkeys  (universal fallback)
# ══════════════════════════════════════════════════════════
XBINDKEYS_RC     = Path.home() / ".xbindkeysrc"
XBINDKEYS_MARKER = "# AEGIS Super+N"

def install_xbindkeys(exec_cmd: str) -> bool:
    if not shutil.which("xbindkeys"):
        print("  [xbindkeys] not installed.")
        print("  Install: sudo apt install xbindkeys")
        return False

    entry = f'\n{XBINDKEYS_MARKER}\n"{exec_cmd}"\n  Super + n\n'

    if XBINDKEYS_RC.exists():
        content = XBINDKEYS_RC.read_text()
        if XBINDKEYS_MARKER in content:
            print("  [xbindkeys] entry already present.")
            return True
        XBINDKEYS_RC.write_text(content + entry)
    else:
        XBINDKEYS_RC.write_text(entry)

    # Kill existing xbindkeys and restart
    run("pkill xbindkeys 2>/dev/null", timeout=3)
    time.sleep(0.5)
    subprocess.Popen(["xbindkeys"], start_new_session=True)
    return True

def uninstall_xbindkeys():
    if not XBINDKEYS_RC.exists():
        return
    lines = XBINDKEYS_RC.read_text().splitlines()
    out, skip = [], 0
    for line in lines:
        if XBINDKEYS_MARKER in line:
            skip = 2
            continue
        if skip > 0:
            skip -= 1
            continue
        out.append(line)
    XBINDKEYS_RC.write_text("\n".join(out))
    run("pkill -HUP xbindkeys 2>/dev/null", timeout=3)


# ══════════════════════════════════════════════════════════
#  METHOD 4 — i3 / sway config
# ══════════════════════════════════════════════════════════

def _find_wm_config() -> Path | None:
    for p in [
        Path.home() / ".config/i3/config",
        Path.home() / ".config/sway/config",
        Path.home() / ".i3/config",
    ]:
        if p.exists():
            return p
    return None

def install_i3(exec_cmd: str) -> bool:
    cfg = _find_wm_config()
    if not cfg:
        return False
    marker = "# AEGIS_SHORTCUT"
    text   = cfg.read_text()
    if marker in text:
        print(f"  [i3/sway] binding already in {cfg}")
        return True
    cfg.write_text(text + f"\n{marker}\nbindsym $mod+n exec {exec_cmd}\n")
    print(f"  [i3/sway] Added to {cfg}. Reload: $mod+Shift+r")
    return True

def uninstall_i3():
    cfg = _find_wm_config()
    if not cfg:
        return
    lines = cfg.read_text().splitlines()
    new   = [l for l in lines
             if "# AEGIS_SHORTCUT" not in l and "bindsym $mod+n exec" not in l]
    cfg.write_text("\n".join(new))


# ══════════════════════════════════════════════════════════
#  .desktop launcher  (appears in app search)
# ══════════════════════════════════════════════════════════
DESKTOP_PATH = Path.home() / ".local/share/applications/aegis-agent.desktop"

def install_desktop(exec_cmd: str):
    DESKTOP_PATH.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP_PATH.write_text(f"""[Desktop Entry]
Version=1.0
Type=Application
Name=AEGIS Agent
Comment=Ubuntu OS Chief-of-Staff AI
Exec={exec_cmd}
Icon=utilities-terminal
Terminal=false
Categories=Utility;
StartupNotify=true
""")
    run(f"chmod +x {DESKTOP_PATH}")
    run("update-desktop-database ~/.local/share/applications/ 2>/dev/null", timeout=5)
    print(f"  .desktop launcher installed → {DESKTOP_PATH}")

def uninstall_desktop():
    if DESKTOP_PATH.exists():
        DESKTOP_PATH.unlink()
        print(f"  Removed {DESKTOP_PATH}")


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════╗")
    print("║   AEGIS Shortcut Installer  (Super+N)║")
    print("╚══════════════════════════════════════╝\n")

    if args.uninstall:
        print("Removing Super+N shortcut...")
        uninstall_dconf()
        uninstall_gsettings()
        uninstall_i3()
        uninstall_xbindkeys()
        uninstall_desktop()
        print("\n✔  Shortcut removed.\n")
        return

    terminal = find_terminal()
    if not terminal:
        print("✘  No terminal emulator found.")
        print("   sudo apt install gnome-terminal\n")
        sys.exit(1)

    exec_cmd = build_exec_cmd(terminal)

    print(f"  Terminal  : {terminal}")
    print(f"  Command   : {exec_cmd}")
    print(f"  Agent     : {AGENT_SCRIPT}")
    print(f"  Venv      : {'found ✔' if VENV_ACTIVATE.exists() else 'not found'}\n")

    # Detect DE
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    print(f"  Desktop   : {de or 'unknown'}\n")

    success = False

    # i3/sway first if applicable
    if any(x in de for x in ["i3", "sway"]) or _find_wm_config():
        success = install_i3(exec_cmd)

    # GNOME: try dconf first (no dbus hang), then gsettings fallback
    if not success and any(x in de for x in ["gnome","unity","budgie","cinnamon",""]):
        success = install_dconf(exec_cmd)
        if not success:
            success = install_gsettings(exec_cmd)

    # xbindkeys universal fallback
    if not success:
        print("  Falling back to xbindkeys...")
        success = install_xbindkeys(exec_cmd)

    # Always install .desktop
    install_desktop(exec_cmd)

    print()
    if success:
        print("✔  Super+N shortcut installed!")
        print("   Press Super+N anywhere to launch AEGIS.\n")
        print("   NOTE: Log out and back in if Super+N doesn't work immediately.\n")
    else:
        print("⚠  Auto-install failed. Manually bind this command to Super+N:")
        print(f"\n   {exec_cmd}\n")
        print("   Settings → Keyboard → Custom Shortcuts → Add\n")


if __name__ == "__main__":
    main()