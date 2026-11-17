# Checklist for an independent human reviewer

**For a person who did not write this work.** Review by another AI system, including the assistant that helped write it, does not count as independent human review. Nothing here needs a GPU or a model call; tokenizer files are downloaded from the Hugging Face Hub.

Record for each item: pass, fail or unclear, a note, and the commit you checked. Return the filled list to the author. It will be published with the report as it was returned.

**Setup**

```bash
git clone https://github.com/fcavaletto/prompt-injection-eval && cd prompt-injection-eval
git checkout research-audit-2026-11   # 2026-11-17: for sections G and H, check out offline-package-2026-11
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

## G. Attack realism, scoring and Stage 1 design (added 2026-11-17)

Files: `src/prompt_injection_eval/pilot/stage1.py`, `data/stage1/design.json`, `docs/protocol-stage1.md`, `tests/test_stage1.py`.

21. **Forged-data realism.** Read the five forged fields in `stage1.PATHWAYS`.
    - Would a reader take each as data (a payee's bank details, a source link) and not as an instruction?
    - Is Slack `user_task_0` ("Full article" plus a link) data or an implicit instruction? Mark each pathway: data / instruction / unclear.
22. **Equal control.** Does every attack, instruction or forged, go into the same field, at the same place, within the baseline's length, without touching trusted text or schemas?
23. **Twins.** Do `neutral_baseline_one_line` and each `forged_one_line` differ from their multiline twins only in whitespace?
24. **Goal scoring.**
    - Read `test_goal_scoring_credits_data_following_and_not_the_reference` and AgentDojo's security checks for banking `injection_task_5` and Slack `injection_task_1` and `injection_task_3`.
    - Does acting on the forged data, and only that, satisfy the check?
    - Was dropping the rent pathways (rent is not recurring) correct?
25. **Pair draw.** Confirm that `stage1.draw` uses no pilot outcome, and that the banking pairs come from the half no model has run.
26. **Representations.** Read `to_quoted` and the table in protocol section 2. Is each contrast described as changing what it changes, including tokens and line structure? Is any claim of a fully orthogonal factorial made anywhere?
27. **Progression.** Does the progression rule (protocol section 6) depend on effect sizes and validity checks, and not on a p-value alone?
    - Would you accept each reading in the table as discriminating between the explanations E0 to E4?

## H. Checkers and recomputed tables (added 2026-11-17)

28. Read `docs/measurement-contract.md`.
    - Were the expected verdicts committed before the checkers changed? Compare commit `15a2279` with `aadf5da`.
    - Is each verdict reasonable, in particular accepting tool results in a user turn, and rejecting a JSON result re-serialized with ASCII escapes?
29. Run `python scripts/validate_checkers.py --label review --output /tmp/cv`. Does `summary_review.md` match `results-published/checker-validation-2026-11-17/summary_v2.md`?
30. Run `python scripts/pilot_supplementary.py ...` (README). Do the reproduction checks match, and do the banking matrix rows for Granite's `baseline` and `neutral_baseline_one_line` read 47/72, 35/72, 20/72 and 28/72?

Reviewer: ______  Date: ______  Commit checked: ______
