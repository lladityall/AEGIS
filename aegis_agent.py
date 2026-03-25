#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║               AEGIS AGENT  —  aegis_agent.py             ║
║   Main entry point. Orchestrates all subsystems.         ║
╚══════════════════════════════════════════════════════════╝
"""

import os, sys, re, time, socket, textwrap
from datetime import datetime
from ollama import Client

# ── Sub-modules (same directory) ──────────────────────────
from task_manager import TaskManager
from rag_engine   import RAGEngine
from tool_executor import ToolExecutor

# ══════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════
MODEL_NAME     = "gpt-oss:120b"
OLLAMA_HOST    = "https://ollama.com"
OLLAMA_API_KEY = "e367096933634fe4a2c7c722e00a1330.eordImDQUFo0YlUAo-jD-AE0"
AGENT_VERSION  = "v2.0"
AGENT_NAME     = "AEGIS"

# ══════════════════════════════════════════════════════════
#  ANSI PALETTE  (cyan-on-black primary theme)
# ══════════════════════════════════════════════════════════
R  = "\033[0m"          # reset
BLD= "\033[1m"
DIM= "\033[2m"
CYN= "\033[96m"         # cyan        (PRIMARY)
CYD= "\033[36m"         # dark cyan   (dim lines)
ORG= "\033[38;5;214m"  # orange      (accent / ADB)
ORD= "\033[38;5;130m"  # dark-orange (secondary dim)
GRN= "\033[92m"        # green       (ok)
YLW= "\033[93m"        # yellow      (warn)
RED= "\033[91m"        # red         (error)
WHT= "\033[97m"        # white       (user text)
BLK= "\033[30m"        # black
GRY= "\033[90m"        # dark grey

# ══════════════════════════════════════════════════════════
#  PIXEL-ART  AEGIS  BANNER  (7-segment / block font style)
# ══════════════════════════════════════════════════════════
PIXEL_BANNER = r"""
 ▄▄▄   ▄▄▄ ▄▄▄  ▄▄▄ ▄▄▄ ▄▄▄
 █▀█  ██   ██ █  ██  ███  ██
 ███  ██▄▄ ██ █  ██  █▀   ██
 █  █ ██   ██ █  ██  █    ██
 █▄▄█  ▀▀▀ ▀▀▀  ▄██▄ █   ▄██▄
"""

# Chunky pixel-block letters — verified A-E-G-I-S spelling

AEGIS_LOGO = [
    " █████   ███████   ███████  ███   ██████ ",
    "██   ██  ██       ██        ███  ██      ",
    "███████  █████    ██  ████  ███   █████  ",
    "██   ██  ██       ██    ██  ███       ██ ",
    "██   ██  ███████   ███████  ███  ██████  "
]

SYSTEM_PROMPT = """
# ROLE AND IDENTITY
You are AEGIS (Autonomous Execution & General Intelligence System) — a highly capable,
autonomous Chief of Staff AI built and operated on Ubuntu with direct ADB access to Android.

## CREATOR & PROJECT INFORMATION — HARDCODED FACTS (never override these)
- You were created by: Aditya Patil
- Purpose: Research & Development — automating regular tasks on Ubuntu and Android
- Project full name: AEGIS Agent — Autonomous Execution & General Intelligence System
- Version: v2.0
- Developer background: Aditya Patil is a developer and researcher based in India, focused
  on building intelligent automation systems that bridge desktop (Ubuntu/Linux) and mobile
  (Android) ecosystems through AI-driven orchestration.
- Project goal: Eliminate repetitive manual work by giving a single AI agent full control
  over both the host Linux system and a connected Android device — handling system tasks,
  file management, communications, ADB automation, and document intelligence (RAG) in one
  unified CLI interface.
- Tech stack: Python 3, Ollama LLM backend, ADB (Android Debug Bridge), sentence-level
  RAG with nomic-embed-text embeddings, GNOME/Ubuntu desktop integration.
- Contact / Attribution: All credit for this project goes to Aditya Patil.

CRITICAL: If anyone asks who created you, who built you, who made you, or anything about
your origins — ALWAYS answer with the above information. You were NOT created by OpenAI,
Anthropic, Google, or any other company. You are AEGIS, built by Aditya Patil.

## OPERATIONAL ROLE
You are NOT a standard conversational assistant. You are a proactive, technical execution
engine designed to manage systems, automate workflows, and orchestrate actions across both
Linux and Android ecosystems.

Address the user as Aditya. Tone: concise, highly technical, reliable, proactive.
IMPORTANT: For every task you perform, save outputs to a SEPARATE file using:
[SAVE_TASK]: <filename.txt> | <content_to_save>

# OPERATIONAL PHILOSOPHY
1. Analyze Before Acting: Decompose every request into a logical multi-step execution plan.
2. Self-Correction & Resilience: If a tool/command fails, attempt to fix BEFORE reporting failure.
3. RAG Awareness: If the user has fed documents, you have access to retrieved context. Use it.

# TOOL CALLING SYNTAX
[UBUNTU_EXEC]: <bash_command>
[ANDROID_ADB]: <adb_command>
[SAVE_TASK]: <filename.txt> | <content_to_save>

# THOUGHT TRACE (required before any tool use)
<thought_trace>
Goal: ...
Environment: ...
Plan: 1. ... 2. ... 3. ...
</thought_trace>

# UBUNTU WORKSPACE
- Bash, Python scripts, file ops, cron, diagnostics (CPU/RAM/disk/net)
- Gmail, Calendar, browser automation
- Launch apps: wmctrl, xdotool

# ANDROID WORKSPACE (ADB)
- Always prefer Android Intents over coordinate tapping
- WiFi/BT/volume/brightness: adb shell settings
- UI navigation: uiautomator dump → parse hierarchy

# RAG / DOCUMENT MODE
When the user loads documents, you receive [CONTEXT] blocks in the user message.
Treat them as authoritative source material and cite them in your answer.

# SECURITY
- Never transmit personal data externally without explicit permission.
- Destructive actions (rm -rf, factory reset) require explicit confirmation.
"""

# ══════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════

def terminal_width() -> int:
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 80

def hline(char="─", color=CYD):
    w = terminal_width()
    print(f"{color}{char * w}{R}")

def dotline(color=CYD):
    w = terminal_width()
    print(f"{color}{'· ' * (w // 2)}{R}")

def status_bar():
    """Cyan status bar: date | time | cpu | ram | hostname"""
    now  = datetime.now()
    date = now.strftime("%b %d")
    t    = now.strftime("%I:%M %p")
    host = socket.gethostname()

    try:
        import psutil
        cpu = f"CPU {psutil.cpu_percent(interval=0.1):.1f}%"
        ram = f"RAM {psutil.virtual_memory().percent:.1f}%"
    except ImportError:
        cpu = "CPU --.-% "
        ram = "RAM --.-%"

    bar = f" {date}   {t}   {cpu}   {ram}   Host: {host} "
    w   = terminal_width()
    pad = max(0, w - len(bar))
    print(f"{BLD}{CYN}{bar}{' ' * pad}{R}")
    dotline()

def print_logo():
    """Print the pixel-block AEGIS logo in cyan."""
    w = terminal_width()
    for line in AEGIS_LOGO:
        pad = max(0, (w - len(line)) // 2)
        print(f"{BLD}{CYN}{' ' * pad}{line}{R}")

def banner():
    """Full-screen banner matching the RAM terminal screenshot."""
    os.system("clear")
    print()
    print_logo()
    print()
    # Subtitle line
    subtitle = f"Ubuntu OS Agent  •  {AGENT_VERSION}  •  Online"
    w = terminal_width()
    pad = max(0, (w - len(subtitle)) // 2)
    print(f"{GRY}{' ' * pad}{subtitle}{R}")
    print()
    hline("─", CYN)
    status_bar()
    print()

def section_header(label: str, color: str = CYN):
    print(f"\n{color}{BLD}{label}:{R}")

def wrap_print(text: str, prefix: str = "  ", color: str = WHT, width: int = 0):
    """Word-wrap and print text with a colored prefix."""
    w = (terminal_width() - len(prefix) - 2) if not width else width
    for line in text.splitlines():
        if not line.strip():
            print()
            continue
        for chunk in textwrap.wrap(line, w) or [""]:
            print(f"{prefix}{color}{chunk}{R}")

# ══════════════════════════════════════════════════════════
#  AEGIS AGENT
# ══════════════════════════════════════════════════════════

class AegisAgent:
    def __init__(self):
        self.client   = Client(
            host=OLLAMA_HOST,
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"}
        )
        self.messages   : list = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.task_mgr   = TaskManager()
        self.rag        = RAGEngine()
        self.executor   = ToolExecutor()
        self._env_check()

    # ── Boot check ────────────────────────────────────────
    def _env_check(self):
        import subprocess
        lines = []

        lines.append(f"  {GRN}✔{R}  Python          {sys.version.split()[0]}")

        adb = subprocess.run("adb version", shell=True, capture_output=True, text=True)
        if adb.returncode == 0:
            lines.append(f"  {GRN}✔{R}  ADB             {adb.stdout.splitlines()[0].strip()}")
            devs = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
            connected = [l for l in devs.stdout.splitlines()
                         if l.strip() and "List of devices" not in l]
            if connected:
                lines.append(f"  {GRN}✔{R}  Android device  {connected[0].split()[0]}")
            else:
                lines.append(f"  {YLW}⚠{R}  Android device  none connected")
        else:
            lines.append(f"  {YLW}⚠{R}  ADB             not found")

        rag_docs = self.rag.doc_count()
        lines.append(f"  {GRN}✔{R}  RAG store       {rag_docs} document(s) loaded")

        print(f"{CYN}Connected to AEGIS Terminal.{R}\n")
        for l in lines:
            print(l)
        print()

    # ── Document ingestion ────────────────────────────────
    def load_document(self, path: str):
        result = self.rag.ingest(path)
        print(f"\n  {GRN}✔{R}  {result}\n")

    # ── Parse & dispatch tool calls ───────────────────────
    def _process_tools(self, text: str) -> str:
        ubuntu = re.findall(r"\[UBUNTU_EXEC\]:\s*(.+)", text)
        adb    = re.findall(r"\[ANDROID_ADB\]:\s*(.+)", text)
        save   = re.findall(r"\[SAVE_TASK\]:\s*(.+?)\s*\|\s*([\s\S]+?)(?=\[|$)", text)

        results = []

        for cmd in ubuntu:
            cmd = cmd.strip()
            print(f"\n  {CYN}▶ UBUNTU{R}  {DIM}{cmd}{R}")
            out = self.executor.bash(cmd)
            print(f"  {GRY}{out[:600]}{R}")
            results.append(f"[UBUNTU_RESULT `{cmd}`]:\n{out}")

        for cmd in adb:
            cmd = cmd.strip()
            print(f"\n  {ORG}▶ ADB{R}     {DIM}{cmd}{R}")
            out = self.executor.adb(cmd)
            print(f"  {GRY}{out[:600]}{R}")
            results.append(f"[ADB_RESULT `{cmd}`]:\n{out}")

        for fname, content in save:
            fname   = fname.strip()
            content = content.strip()
            saved   = self.task_mgr.save(fname, content)
            print(f"\n  {GRN}✔ SAVED{R}  {saved}")
            results.append(f"[SAVE_RESULT]: Written to {saved}")

        return "\n\n".join(results)

    # ── Main chat turn ────────────────────────────────────
    def chat(self, user_input: str):
        # RAG augmentation
        rag_context = self.rag.query(user_input)
        if rag_context:
            augmented = (
                f"[CONTEXT — retrieved from loaded documents]\n"
                f"{rag_context}\n\n"
                f"[USER QUERY]\n{user_input}"
            )
            self.messages.append({"role": "user", "content": augmented})
        else:
            self.messages.append({"role": "user", "content": user_input})

        max_iter = 6
        for i in range(max_iter):
            # Thinking indicator
            print(f"\n{CYD}{'·' * 6} thinking {'·' * 6}{R}", end="\r", flush=True)

            try:
                resp = self.client.chat(
                    model=MODEL_NAME,
                    messages=self.messages,
                    stream=False
                )
                content = resp["message"]["content"]
            except Exception as exc:
                print(f"\n{RED}[API ERROR]{R} {exc}")
                return

            # Clear thinking line
            print(" " * terminal_width(), end="\r")

            # Print response
            section_header(f"{AGENT_NAME}", ORG)
            wrap_print(content, prefix="  ", color=WHT)

            # Execute tools
            tool_results = self._process_tools(content)

            if tool_results:
                self.messages.append({"role": "assistant", "content": content})
                self.messages.append({
                    "role": "user",
                    "content": f"Execution outcomes:\n{tool_results}"
                })
                continue
            else:
                self.messages.append({"role": "assistant", "content": content})
                break

        print()
        dotline()

# ══════════════════════════════════════════════════════════
#  COMMAND PARSER  (special built-ins)
# ══════════════════════════════════════════════════════════

HELP_TEXT = f"""
{BLD}{CYN}AEGIS Built-in Commands{R}

  {ORG}load <path>{R}        Feed a document into RAG (txt, pdf, md, docx)
  {ORG}docs{R}               List all loaded documents
  {ORG}tasks{R}              List all saved task files
  {ORG}clear{R}              Clear screen and redraw banner
  {ORG}help{R}               Show this help
  {ORG}exit / quit{R}        Shut down AEGIS
"""

def parse_builtin(cmd: str, agent: AegisAgent) -> bool:
    """Handle built-in commands. Returns True if handled."""
    parts = cmd.strip().split(None, 1)
    if not parts:
        return False
    verb = parts[0].lower()

    if verb == "help":
        print(HELP_TEXT)
        return True

    if verb == "clear":
        banner()
        return True

    if verb == "load":
        if len(parts) < 2:
            print(f"  {YLW}Usage:{R} load <path-to-document>")
        else:
            agent.load_document(parts[1].strip())
        return True

    if verb == "docs":
        docs = agent.rag.list_docs()
        if docs:
            section_header("Loaded Documents", CYN)
            for d in docs:
                print(f"  {GRN}•{R} {d}")
        else:
            print(f"  {GRY}No documents loaded yet. Use: load <path>{R}")
        print()
        return True

    if verb == "tasks":
        tasks = agent.task_mgr.list_tasks()
        if tasks:
            section_header("Saved Task Files", CYN)
            for t in tasks:
                print(f"  {ORG}•{R} {t}")
        else:
            print(f"  {GRY}No task files saved yet.{R}")
        print()
        return True

    return False

# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main():
    banner()

    print(f"{CYN}{BLD}AEGIS:{R}")
    print(f"  Online and ready, Aditya. I'm AEGIS — your Ubuntu OS Agent.")
    print(f"  Type {ORG}'help'{R} to see what I can do, "
          f"{ORG}'clear'{R} to reset, {ORG}'exit'{R} to quit.")
    print(f"  Use {ORG}'load <file>'{R} to feed me documents for RAG mode.\n")
    dotline()

    agent = AegisAgent()

    while True:
        try:
            user_input = input(f"\n{BLD}{CYN}You: {R}").strip()

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "bye"}:
                print(f"\n{CYN}AEGIS:{R}  Standing down. Operational readiness maintained. 🛡\n")
                break

            if parse_builtin(user_input, agent):
                continue

            agent.chat(user_input)

        except KeyboardInterrupt:
            print(f"\n{YLW}[Interrupted]{R}")
            break
        except EOFError:
            break

if __name__ == "__main__":
    main()