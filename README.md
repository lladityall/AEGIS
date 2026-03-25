# AEGIS Agent  🛡

**A E G I S** — Autonomous Execution & General Intelligence System

Ubuntu OS Agent  •  v2.0  •  Chief of Staff AI

---

## File Structure

```
aegis/
├── aegis_agent.py        ← Main entry point (run this)
├── tool_executor.py      ← Ubuntu bash + Android ADB execution
├── task_manager.py       ← Saves each task to a separate file
├── rag_engine.py         ← Document ingestion & RAG retrieval
├── install_shortcut.py   ← Registers Super+N keyboard trigger
├── requirements.txt      ← Python dependencies
└── README.md             ← This file
```

Task outputs are saved to: `~/.aegis/tasks/`
RAG document store:        `~/.aegis/rag_store/`

---

## Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Register Super+N keyboard shortcut (run once)
python3 install_shortcut.py

# 3. Launch manually (or press Super+N after step 2)
python3 aegis_agent.py
```

---

## Usage

### Basic commands

| Command | Description |
|---|---|
| `help` | Show all built-in commands |
| `clear` | Redraw the banner |
| `exit` / `quit` | Shut down AEGIS |

### RAG — Feed documents

```
load /path/to/document.pdf
load ~/notes/meeting.txt
load /home/aditya/report.docx
```

After loading, just ask questions:

```
You: summarise the key findings from the report
You: what does the document say about the API limits?
You: find all action items mentioned in the meeting notes
```

### Task files

Every task AEGIS performs is saved to a separate timestamped file in
`~/.aegis/tasks/`.  List them with:

```
tasks
```

### Ubuntu system commands

```
You: what's my current CPU and RAM usage?
You: show all running python processes
You: find all .log files modified in the last 24 hours
```

### Android ADB commands

```
You: set my phone volume to 50%
You: open YouTube and search for lo-fi beats
You: enable DND on my phone
```

---

## Super+N Shortcut

Run `python3 install_shortcut.py` once.  From then on, pressing **Super+N**
anywhere on your desktop will open a terminal running AEGIS.

Supports: GNOME, XFCE, KDE, i3, sway, and xbindkeys fallback.

To uninstall the shortcut:

```bash
python3 install_shortcut.py --uninstall
```

---

## RAG Dependencies

For full semantic search, install:

```bash
pip install sentence-transformers numpy PyPDF2 python-docx
```

Without these, AEGIS falls back to keyword-based retrieval (still works,
just less accurate).

---

## Configuration

Edit the top of `aegis_agent.py` to change:

```python
MODEL_NAME     = "gpt-oss:120b"
OLLAMA_HOST    = "https://ollama.com"
OLLAMA_API_KEY = "your-key-here"
```
