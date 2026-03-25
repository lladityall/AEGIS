#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║           AEGIS  —  tool_executor.py                     ║
║   Executes Ubuntu bash and Android ADB commands.         ║
╚══════════════════════════════════════════════════════════╝
"""

import subprocess


class ToolExecutor:
    """Runs bash and ADB commands, returns clean string output."""

    def bash(self, command: str, timeout: int = 60) -> str:
        """Execute a bash command on the Ubuntu host."""
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True,
                timeout=timeout
            )
            parts = []
            if result.stdout.strip():
                parts.append(result.stdout.strip())
            if result.stderr.strip():
                parts.append(f"[stderr] {result.stderr.strip()}")
            if result.returncode != 0:
                parts.append(f"[exit {result.returncode}]")
            return "\n".join(parts) if parts else "(no output)"
        except subprocess.TimeoutExpired:
            return f"[timeout after {timeout}s]"
        except Exception as exc:
            return f"[error] {exc}"

    def adb(self, command: str, timeout: int = 60) -> str:
        """Execute an ADB command against the connected Android device."""
        if not command.strip().startswith("adb"):
            command = f"adb {command.strip()}"
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True,
                timeout=timeout
            )
            parts = []
            if result.stdout.strip():
                parts.append(result.stdout.strip())
            if result.stderr.strip():
                parts.append(f"[stderr] {result.stderr.strip()}")
            if result.returncode != 0:
                parts.append(f"[exit {result.returncode}]")
            return "\n".join(parts) if parts else "(no output)"
        except subprocess.TimeoutExpired:
            return f"[timeout after {timeout}s]"
        except Exception as exc:
            return f"[error] {exc}"
