# WP7 audit evidence (2026-11-16)

Offline. No model was called. Write-up: [docs/wp7-audit.md](../../docs/wp7-audit.md).

## Files

- `audit.json`: one row per configuration, holding:
  - pins and template revisions;
  - class (published, separately tested, unverifiable);
  - the checker's result and notes;
  - the InjecAgent prompt-length check.
- `requests/<id>.json`: the request each harness built for the fixture, as captured from a fake client.
- `renders/<id>.txt`: that request rendered with the template named in `audit.json`. `IA-1_reference_format.txt` is the same InjecAgent content in Meta's reference Llama 2 format, for comparison.
- `agentdojo_local_traces.jsonl` and `agentdojo_local_traces_summary.json`: the token count of the last request of each published AgentDojo LocalLLM trace (Llama 3.3 70B, Meta-SecAlign-70B), and whether the trace ends in an empty assistant turn.

## Rebuild

No GPU and no inference. Tokenizer files are downloaded from the Hugging Face Hub at the pinned revisions.

```bash
pip install -e ".[dev,pilot]" transformers
EXT=$(mktemp -d)
git clone https://github.com/ethz-spylab/agentdojo $EXT/agentdojo && git -C $EXT/agentdojo checkout v0.1.35
git clone https://github.com/uiuc-kang-lab/InjecAgent $EXT/InjecAgent && git -C $EXT/InjecAgent checkout f19c9f2c79a41046eb13c03c51a24c567a8ffa07
git clone https://github.com/MurrayTom/ToolHazard $EXT/ToolHazard && git -C $EXT/ToolHazard checkout 544b73b12a25431cb0be3eb43df41b4aacce5335
git clone https://github.com/compsec-snu/adi $EXT/adi && git -C $EXT/adi checkout 1a3ddf8fa96bf008f3cb80dd56db5149d4ac0df7
python scripts/wp7_audit.py --ext $EXT --out results-published/wp7-audit-2026-11-16
python scripts/wp7_agentdojo_traces.py $EXT/agentdojo --out results-published/wp7-audit-2026-11-16
pytest tests/test_wp7.py
```

`wp7_audit.py` refuses to run if a clone is not at its pinned commit. From the external repositories it executes only the named message-building functions, extracted with `ast`. The AgentDojo regressions use the installed package, `agentdojo==0.1.35`.

## Regression checks

`tests/test_wp7.py`:

- re-checks every stored rendering against `audit.json`;
- asserts the token-threshold split in the published traces;
- against the installed AgentDojo 0.1.35, reproduces three behaviours:
  - LocalLLM's content-block wrapping;
  - its conversion of a server error into an empty answer;
  - PromptingLLM's duplicated system text under `developer`.

If a later AgentDojo version changes any of these, the corresponding test fails, and the finding should be re-examined at that version.

## Sensitive content

The published AgentDojo traces are not copied here; only per-trace token counts and file paths are. The fixture is synthetic. The InjecAgent rendering contains that benchmark's own synthetic user ("John Doe", `john.doe@gmail.com`) from its system prompt. No credentials or personal data are included.
