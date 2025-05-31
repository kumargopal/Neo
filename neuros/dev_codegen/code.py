import json, difflib

async def run(state, *, text: str = ""):
    """
    • When no drafts exist → ask the LLM to generate the three core files.
    • When drafts exist     → treat *text* as an instruction, ask the LLM
                              for *patched* versions, then yield a diff via
                              `dev_diff` and store the patch for `dev_patch`.
    """
    llm     = state["__llm"]
    system  = state.get("__prompt", "")
    ctx     = state.setdefault("__dev", {})
    drafts  = ctx.setdefault("drafts", {})

    # ── 1. NEW neuro ──────────────────────────────────────────────────────
    if not drafts:
        payload = json.dumps({"request": text}, ensure_ascii=False)
        raw     = llm.generate_json(payload, system_prompt=system)
        try:
            files = json.loads(raw)
        except Exception:
            return {"reply": "⚠️ LLM did not return valid JSON – please rephrase."}

        # Persist to draft buffer
        for rel_path, content in files.items():
            drafts[f"neuross/{files.get('neuros_name', 'new_neuros')}/{rel_path}"] = content

        ctx["neuros"] = files.get("neuros_name", "new_neuros")
        return {"reply": f"🆕 Draft for **{ctx['neuros']}** created. "
                         "Review or say more changes, then `/dev_save`."}

    # ── 2. PATCH EXISTING DRAFTS ──────────────────────────────────────────
    payload = json.dumps({
        "instruction": text,
        "current": drafts
    }, ensure_ascii=False)
    raw = llm.generate_json(payload, system_prompt=system)
    try:
        patched = json.loads(raw)
    except Exception:
        return {"reply": "⚠️ Couldn't parse LLM output – try again."}

    # Compute unified diff per file & stash patch for dev_patch
    patch_bundle = []
    for path, new_body in patched.items():
        old_body = drafts.get(path, "").splitlines(keepends=True)
        new_body = new_body.splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            old_body, new_body, fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
        patch_bundle.append(diff)

    ctx["pending_patch"] = "\n".join(patch_bundle)
    return {"reply": "Here's what will change:\n```\n"
                     + ctx["pending_patch"] + "\n```\n"
                     "Say **apply patch** to accept or **discard** to ignore."}
