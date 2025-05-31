# 🧠 Neo

A local-first framework for building, testing, and running **“neuros”**—small, hot-swappable Python skills that a planning LLM stitches together into task-flows (DAGs). Neo ships with:

| Component          | What it does                                                                                             |
| ------------------ | -------------------------------------------------------------------------------------------------------- |
| **FastAPI server** | Exposes `/chat` (REST) and `/ws/{cid}` (WebSocket) so UIs or scripts can talk to the brain in real time. |
| **CLI client**     | Rich-TTY front-end with coloured panels, DAG tracing, and developer toggles (`/dev on`, `/dag show`, …). |
| **Brain**          | Keeps per-conversation state, decides which planner / replier to use (profiles), triggers the executor.  |
| **Executor**       | Walks a DAG, runs each neuro, captures stdout, and streams node events back over WebSocket.              |
| **Neuro factory**  | Hot-reloads every `neuros/*/conf.json` + `code.py`, injects `BaseBrain` and `prompt.txt` automatically.  |

---

## Quick start

```bash
# 1. Install deps (Python 3.11+)
pip install -r requirements.txt

# 2. Launch the server (reload on code changes)
python server.py

# 3. In another terminal, talk to it
python cli_client.py --host localhost --port 8000
```

The CLI prints a prompt like:

```
neuro Client v1.0  (cid: be3a9d1f)
Type /help for commands
>
```

Type messages as you would in ChatGPT.
Use `/dag show` to pop up a live NetworkX preview of the current flow.

---

## File/Folder layout

```
.
├─ core/                 # Brain, executor, conversation log, pub-sub hub
├─ neuros/               # Every skill lives in its own sub-folder
│   └─ <name>/
│       ├─ conf.json     # Manifest (inputs, outputs, desc, model…)
│       ├─ code.py       # async def run(state, **params)
│       └─ prompt.txt    # (optional) system prompt for LLM skills
├─ profiles/             # Profile presets: general, code_dev, neuro_dev
├─ tests/                # JSON scenarios for headless testing
├─ logs/prompts/         # LLM prompt/response transcripts (auto-generated)
└─ cli_client.py         # Rich-terminal client
```

> **Tip:** Hot-reloading is on by default. Edit a neuro’s `code.py`; the factory picks it up within \~1 s.

---

## Working with developer mode

```text
/dev on             # switch to neuro_dev profile
dev_new             # bootstrap a new neuro through LLM
dev_edit ...        # mutate drafts
dev_show            # view staged files
dev_save            # persist to neuros/<name>/
```

The **dev\_planner** auto-routes conversational instructions (“add error handling”, “rename param”) to the right dev\_\* neuro.

---

## Profiles

| Profile     | Planner        | Replier      | Visible neuros                                       |
| ----------- | -------------- | ------------ | ---------------------------------------------------- |
| `general`   | `planner`      | `reply`      | all (`*`)                                            |
| `code_dev`  | `code_planner` | `code_reply` | `code_*` + `neuro_list`                              |
| `neuro_dev` | `dev_planner`  | `dev_reply`  | `dev_*`, `load_neuro`, `neuro_list`, `dev_codegen` … |

Toggle at runtime with `/profile <name>` or the shorthand `/dev on | off`.

---

## Testing

```bash
# Run an automated scenario
python automated_cli_client.py tests/greetings.json
```

Each step in the JSON array is sent as a user turn, and the runner waits until the DAG finishes before moving on.

---

## Contributing

* Fork → create a feature branch → open a PR.
* Stick to Python 3.11+, type-hinted code.
* If you add third-party deps in a neuro, import them lazily (see template in README “Implementation rules”).

---

## License

MIT © 2025 Neo Contributors

> This project uses the OpenAI API. Make sure you set `OPENAI_API_KEY` in your environment before starting the server.
