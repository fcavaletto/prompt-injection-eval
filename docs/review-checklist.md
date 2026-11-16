# Checklist for an independent human reviewer

**For a person who did not write this work.** Review by another AI system, including the assistant that helped write it, does not count as independent human review. Nothing here needs a GPU or a model call; tokenizer files are downloaded from the Hugging Face Hub.

Record for each item: pass, fail or unclear, a note, and the commit you checked. Return the filled list to the author. It will be published with the report as it was returned.

**Setup**

```bash
git clone https://github.com/fcavaletto/prompt-injection-eval && cd prompt-injection-eval
git checkout research-audit-2026-11
pip install -e ".[dev,pilot]" transformers
```

Then clone the four pinned repositories as listed in `results-published/wp7-audit-2026-11-16/README.md`.

## A. Error-path reproducer (AgentDojo `local`)

1. Read `agentdojo/agent_pipeline/llms/local_llm.py` in the installed `agentdojo==0.1.35`, lines 45 to 73.
   - Does every exception in `chat_completion_request` lead to `""` being returned?
   - Does `LocalLLM.query` turn that into an assistant message with no tool call?
2. Run `pytest tests/test_wp7.py -k server_error`.
   - Read the test. Does it show what it claims, and nothing more?
3. Read AgentDojo's security scoring (`task_suite.py`, `_check_task_result` and `run_task_with_pipeline`).
   - Does an episode that ends this way enter ordinary scoring?
   - Could an attack completed before the error still score as a success?

## B. Provenance

4. In the AgentDojo repository, check:
   - `git log -- src/agentdojo/agent_pipeline/llms/local_llm.py`;
   - `git show 9272bf1e0:src/agentdojo/agent_pipeline/llms/local_llm.py`;
   - `git merge-base --is-ancestor` for `9272bf1e0` and `73afb31dc`.

   Do you agree with the provenance paragraph in `docs/wp7-audit.md`:
   - that the code which generated the runs is not recorded;
   - that the runs commit's own LocalLLM lacks `reformat_message`;
   - that both audited behaviours are present from `32521207f` to v0.1.35?
5. Open three traces under `runs/meta-llama_Llama-3.3-70B-Instruct/workspace/`, one of them listed with `empty_final: true` in `agentdojo_local_traces.jsonl`.
   - Confirm `pipeline_name`, `benchmark_version` and `agentdojo_package_version`.
   - Confirm the empty final assistant turn.
6. InjecAgent: `git log` shows the prompted path restructured on 2024-07-02.
   - Is the statement that the audited revision may differ from the one behind the paper's tables fair?
   - ToolHazard: does its README say prompt mode produced the reported results?

## C. Bounds

7. From `agentdojo_local_traces.jsonl`, recount N, S and M for Llama 3.3 under `important_instructions`, workspace and all suites. Use your own code, not ours.
   - Expected: N = 560, S = 38, M = 29 (workspace); N = 949, S = 219, M = 29 (all suites).
8. Check the arithmetic:
   - bounds S/N to (S+M)/N: 6.8% to 12.0%, and 23.1% to 26.1%;
   - complete-case S/(N−M): 7.2% and 23.8%.

   Are they labelled as conditional missing-outcome bounds, not confidence intervals, everywhere they appear (`docs/wp7-audit.md`, `docs/report-draft.md`)?
9. Is the claim that the SecAlign comparison survives correct, including the stated exception (workspace `direct`)?
10. Is the hypothesis (context-limit errors) kept separate from what is observed (empty endings, request lengths)?
    - Is the template dependence stated: the near-separation, not complete separation, without a template?

## D. Representative renderings

11. Open `results-published/wp7-audit-2026-11-16/renders/AD-1.txt`.
    - Find the payload (`MARK-PAYLOAD-7`). Decode it by hand: JSON string, then JSON object, then YAML. Is it intact?
    - Is "extra encoding reproduced, payload survives, effect unmeasured" a fair summary?
12. Open `renders/AD-3.txt`. Is the system text present twice, the second time under a `developer` header?
13. Open `renders/IA-1.txt` and `renders/IA-1_reference_format.txt`. Is the system prompt outside `<<SYS>>` in the first and inside it in the second?
14. Open `renders/TH-1.txt`. Is the tool output YAML in a plain user turn?
15. Run `python scripts/wp7_audit.py --ext <clones> --out /tmp/wp7` and compare `audit.json` with the stored one. Ignore the `written` timestamp.

## E. Decomposition (pilot, exploratory)

16. Run `python scripts/pilot_exploratory.py results-published/pilot-2026-11-16 --output /tmp/exploratory`. Does `exploratory.json` match the stored one?
17. By hand, from `results-published/pilot-2026-11-16/exploratory/goal_rates.csv` (Qwen rows), recompute:
    - the primary contrast (+8.6);
    - the wording component (+7.1);
    - the format component (+1.4).

    Do wording plus format equal the primary?
18. Is every exploratory analysis labelled as written after the outcomes were known?
    - Is the registered reading of the primary contrast stated unchanged?

## F. Scope of claims

19. Does any new claim in `docs/report-draft.md` rest on the project's earlier text-based scorer (Studies A and B)? It should not: that scorer has no human validation.
20. Are the unverifiable configurations (AD-1s, TH-2, ADI-1) reported as unverifiable, not as passes?

Reviewer: ______  Date: ______  Commit checked: ______
