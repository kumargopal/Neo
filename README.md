# 🧠 Neo

A **local‑first framework** for building, testing, and running *neuros*—small, hot‑swappable Python skills that a planning LLM stitches into task‑flows (directed acyclic graphs / DAGs).

Neo lets you:

* Chat naturally while the planner decides which neuros to invoke.
* Swap neuros at runtime without restarting the server (hot‑reload).
* Drop into developer‑mode to scaffold, edit, diff and save neuros from the same chat window.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Package Internals](#core-package-internals)
3. [Quick Start](#quick-start)
4. [Profiles & Modes](#profiles--modes)
5. [Developer‑Mode Workflow](#developer-mode-workflow)
6. [Code‑Project Workflow](#code-project-workflow)
7. [Example Conversations](#example-conversations)
8. [Testing with Scenarios](#testing-with-scenarios)
9. [Contributing](#contributing)
10. [License](#license)

---

## Architecture Overview

| Layer / Component  | Purpose                                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| **FastAPI server** | Exposes `POST /chat` and `WS /ws/{cid}` so UIs and scripts can stream messages & node events in real‑time.                     |
| **CLI client**     | A Rich‑TTY front‑end featuring coloured message panels, live DAG tracing, and power commands (`/dev on`, `/dag show`, …).      |
| **Brain**          | Maintains per‑conversation state, chooses a *profile* (planner + replier combo) and launches the **Executor**.                 |
| **Executor**       | Walks a DAG, runs each neuro in sequence, gathers stdout, and emits `node.*` + `task.done` events back via WebSocket.          |
| **Neuro factory**  | Hot‑reloads every `neuros/*/conf.json` + `code.py`; injects a ready‑to‑use `BaseBrain` instance and `prompt.txt` into `state`. |
| **Profiles**       | Thin JSON presets—*general*, *code\_dev*, *neuro\_dev*—that switch planners, repliers and visible neuros on the fly.           |

<p align="center"><em>All components live under <code>core/</code> or at project‑root.<br>Everything is pure Python 3.11+ with zero external services required (apart from your OpenAI key).</em></p>

---

## Core Package Internals

| Module                       | How it works                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **`core/brain.py`**          | Orchestrates a chat. It: (1) logs turns into `Conversation`; (2) runs **`intent_classifier`**; (3) picks a profile & planner; (4) publishes debug + node events over the pub‑sub **hub**.                                                                                                                                                                                      |
| **`core/executor.py`**       | Receives a **flow** object (`{"start":"n0","nodes":{…}}`). For each node it:<br>1. emits `node.start`<br>2. `await factory.run(neuro, state, **params)`<br>3. merges outputs into `state`<br>4. emits `node.done` (or error) and, if `reply` exists, an `assistant` event.<br>Re‑planning is automatic if a neuro sets `replan=True`.                                          |
| **`core/neuro_factory.py`**  | Scans `neuros/*/conf.json`. Each folder must contain:<br>• `conf.json` (manifest)<br>• `code.py` (async `run`)<br>• *optional* `prompt.txt`.<br>It compiles the code with `exec`, injects `state["__llm"]` (`BaseBrain`), and stores a `BaseNeuro` wrapper in a registry.<br>Runs an async task that watches for file‑mtime changes every second—edit & save → instant reload. |
| **`core/base_brain.py`**     | Thin wrapper around the OpenAI client. Provides `generate_text`, `generate_json`, and a higher‑level `plan()` helper that auto‑parses JSON.                                                                                                                                                                                                                                    |
| **`core/base_neuro.py`**     | A tiny struct holding `name`, `fn`, `inputs`, `outputs`, `desc`. The factory instantiates this and the executor ultimately calls `.run()`.                                                                                                                                                                                                                                     |
| **`core/conversation.py`**   | Persists each chat in `conversations/<cid>.json`. Provides `.add()` and `.history(n)` helpers so neuros & profiles can access full or sliced history.                                                                                                                                                                                                                          |
| **`core/pubsub.py`**         | Simple asyncio broadcast hub. `hub.queue(cid)` returns an `asyncio.Queue` that the server pushes events to and WebSocket clients consume from.                                                                                                                                                                                                                                 |
| **`core/…/profiles/*.json`** | Each file chooses a planner, a replier and a glob list of visible neuros. Switching profile at runtime simply updates these choices for that conversation.                                                                                                                                                                                                                     |

> **Heads‑up for contributors:** Hot‑reload for `core/` code itself is handled by `uvicorn --reload`; for neuros the factory takes care of re‑exec on change.

---

## Quick Start

```bash
# 1  Install deps (Python 3.11+)
pip install -r requirements.txt

# 2  Launch the server (reload on code changes)
python server.py

# 3  Open another terminal and chat
python cli_client.py --host localhost --port 8000
```

The CLI greets you with 

```text
neuro Client v1.0  (cid be3a9d1f)
Type /help for commands
>
```

Type messages as you would in ChatGPT. Toggle goodies:

* `/dag show` – popup a live NetworkX view of the current flow.
* `/dev on` / `/dev off` – enable or leave developer‑mode.
* `/profile <name>` – jump straight to `general`, `code_dev`, or `neuro_dev`.

---

## Profiles & Modes

| Profile     | Planner        | Replier      | Visible neuros (glob)                  |
| ----------- | -------------- | ------------ | -------------------------------------- |
| `general`   | `planner`      | `reply`      | `*`                                    |
| `code_dev`  | `code_planner` | `code_reply` | `code_*`, `neuro_list`                 |
| `neuro_dev` | `dev_planner`  | `dev_reply`  | `dev_*`, `load_neuro`, `neuro_list`, … |

Switch at runtime via `/profile code_dev` or the shortcut `/dev on` (`neuro_dev`) and `/dev off` (back to `general`).

---

## Developer‑Mode Workflow

```text
/dev on                       # → neuro_dev profile (dev_planner + dev_reply)
dev_new                       # scaffold a completely new neuro via LLM
dev_edit "add error handling" # patch drafts in memory
dev_show                      # show current drafts (Markdown diff)
dev_save                      # write drafts to neuros/<name>/ (factory reloads)
```

### Hot‑reload timeline

1. **`dev_save`** writes files to `neuros/...`.
2. The **neuro factory** notices `mtime` changed → re‑executes `code.py`.
3. Your new skill is live for the *next* planner run—no restarts.

---

## Code‑Project Workflow

| Command / Intent                      | Typical Flow                                                                                    |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| “Create project `blog`”               | `code_planner` → `code_project_manager(project_name="blog")`                                    |
| “Add a file `README.md` with heading” | planner adds a `code_file_write` node after ensuring project exists.                            |
| “Show files”                          | short‑form → `code_file_list(glob="**/*")`                                                      |
| “Open project”                        | `code_project_manager(project_name=…)` just switches the cached `__project_root`.               |
| “Patch `main.py` to log errors”       | `code_file_read` → `code_file_diff` (diff preview) → await **apply patch** → `code_file_write`. |

`code_dev` profile routes all such utterances automatically; you can still sprinkle `/dev on` if you want to author new neuros mid‑conversation.

---

## Example Conversations

### 1  Generic Chat (general profile)

```text
user  › Hi Neo!
assistant › Hello! How can I assist you today?
user  › What is the difference between a thread and a process?
assistant › … concise technical explanation …
```

The planner emits `{type:"reply"}`; no neuros run.

### 2  Neuro‑dev Session

```text
user  › /dev on
assistant › neuro‑dev profile enabled.

user  › Create a neuro that locks an Ubuntu screen.
assistant › 🆕 Draft for **screen_lock_ubuntu** created.
           (shows neuro.json, prompt.txt, code.py)

user  › Add error handling and return a boolean success flag.
assistant › Shows unified diff preview.

user  › apply patch
assistant › ✅ Applied patch.

user  › dev_save
assistant › ✅ Saved 3 file(s).
```

Factory reloads → `screen_lock_ubuntu` is now available.

### 3  Using the New Neuro Immediately

```text
user  › Lock my screen please.
assistant › 🔒 Screen locked successfully.
```

Planner chose `{name:"screen_lock_ubuntu"}`.

### 4  Code‑dev Project + Multi‑Neuro orchestration

```text
user  › /profile code_dev   # or just stay in dev and switch off later
assistant › Code‑dev profile enabled.

user  › Create project log_analyser.
assistant › ✅ Project **log_analyser** ready at …

user  › Write file log_analyser/main.py that prints "hello".
assistant › 📝 Wrote `log_analyser/main.py` (3 lines).

user  › Show project files.
assistant › Files:
           – log_analyser/main.py

user  › Run the program.            # (not yet implemented)
assistant › Currently unsupported—try adding a dev neuro to execute Python.
```

You could now `/dev on` again, `dev_new run_python_file`, implement it, `dev_save`, and immediately do:

```text
user › run_python_file path="log_analyser/main.py"
assistant › stdout: hello
```

### 5  Composing Neuros Together

```text
user  › /dev on
assistant › neuro‑dev profile enabled.

user  › Create a neuro summarise_logs that reads all *.log files in the active project and returns a markdown summary.
… (draft, patch, save) …

user  › /dev off
assistant › Switched to code‑dev profile.

user  › summarise_logs
assistant › • Total requests: 1245
           • Errors: 17 (1.3 %)
           • Slowest endpoint: /search (p95 = 812 ms)
```

---

## Testing with Scenarios

```bash
python automated_cli_client.py tests/greetings.json
```

`automated_cli_client.py` feeds user turns from the JSON array and waits for each DAG to finish (looks for `✓ Node n0` → `task.done`). Perfect for CI.

---

## Contributing

1. Fork → create a branch → open a PR.
2. Target Python 3.11+, type‑annotate new code.
3. For new neuros: **lazy‑import** external deps inside `run()` to avoid bloating the global environment.
4. Update `requirements.txt` only when absolutely necessary (server‑side libs, not per‑neuro deps).

---

## License

MIT © 2025 Neo Contributors

> **OpenAI API** – set `OPENAI_API_KEY` in your shell before starting the server.
