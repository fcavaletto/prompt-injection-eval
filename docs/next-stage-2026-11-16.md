# Next stage after the pilot (2026-11-16)

> **Superseded as a plan (2026-11-17).** The current plan is the [Stage 1 protocol](protocol-stage1.md). This page is kept as written for the record; its recommendation was made before the [claim–evidence table](claim-evidence.md) and the supplementary analyses.

Offline. No pod was rented and no model was called for this page. New analyses of existing results are **exploratory**. Proposals are **unregistered**. The completed pilot, its registered analyses and its pre-registered reading are unchanged; corrections are dated notes ([Corrections](corrections.md) C11 to C13).

## 1. What the pilot shows, tightened

Detail: [Pilot design](pilot-design.md), section 9.6e; [exploratory output](https://github.com/fcavaletto/prompt-injection-eval/tree/research-audit-2026-11/results-published/pilot-2026-11-16/exploratory).

- **The registered primary** (each format against the attack selected for it on banking) is positive for both models: Qwen3-32B +8.6 (+2.9 to +14.3), Granite 4.0 H Small +11.4 (+2.9 to +21.0). It measures a selection procedure as well as serialization.
- **Qwen, decomposed:** +7.1 (+2.4 to +12.9) from the two selected wordings differing in strength in both formats, and +1.4 (−2.9 to +6.2) from the average same-attack format difference. A format effect of a few points is neither shown nor excluded. The attack × format interaction is +1.0 (−5.7 to +7.6).
- **Granite:** same-attack format effect +10.5 averaged over two attacks (+3.8 to +17.1); interaction +1.9 (−7.6 to +11.4).
- **Between models:** Granite's baseline format effect minus Qwen's is +7.6 (−0.9 to +16.2). A difference between the models is not established.

## 2. The progression gate

Detail: [Pilot design](pilot-design.md), section 9.8a.

- Condition 2 ("runs disagree in at most 5% of cells") names no outcome.
- Granite disagreed in 4 of 84 repeated cells on attack success (4.8%) and 5 of 84 on user-task success (6.0%).
- The rule is ambiguous. Read conservatively it is not met, so **section 9.8 as registered does not justify the larger study.**
- The threshold is not waived and no further repeats are collected.
- The nondeterminism is small for estimation: first-run estimates already absorb it, and the all-runs analysis moved Granite's primary by 0.3 points. It is large enough to matter for reproducing single-run numbers.
  *Qualified 2026-11-16: this assumes run-to-run noise independent across cases; shared batch effects were not investigated. The 4 of 84 cells are clustered (2 of 21 pairs); see [Pilot design](pilot-design.md) 9.8a.*
- A replacement rule is proposed there for any future design, to be registered before that design's data.

## 3. Novelty, reassessed

*Note 2026-11-16, later: every claim marked (s) below, and the ToolHazard figures, were verified from full text and code. All held except the attribution of 87 tasks to ToolHazard's format experiment. See [the audit appendix](research-audit-2026-11.md), D1b. The novelty conclusion stands.*

**Read for this page.** Read 2026-11-16 through a fetching tool: the opening of each paper verbatim, and the rest as a model-extracted summary. Statements from the summary part are marked (s); they should be checked against the paper before being cited.

- *Agent Data Injection*, arXiv:2607.05120 v1. New to this project.
- *AutoDojo*, arXiv:2606.15057 v3. New.
- *SARA*, arXiv:2608.27146 v1. New; not close.
- ToolHazard's abstract page: still only v1, "Work in Progress". Two code links exist: `github.com/MurrayTom/ToolHazard`, and an anonymized repository. The project's earlier reading of the code, at commit `544b73b`, found no JSON switch. That was not re-checked.

| Question | Closest existing experiment | What remains open | Evidence that would answer it | Kind |
| --- | --- | --- | --- | --- |
| Does JSON instead of free-text tool output lower the success of a fixed injection? | ToolHazard Sec. 7.2, Fig. 4: GPT-4.1 and Gemini-3.1-Pro, prompt mode (per the README), experiment size not stated (87 is the benchmark's), no intervals; e.g. 52.6% free-form vs 5.9% JSON on one attack | Size and sign on open models in function-calling mode, with verified delivery and task-clustered intervals; formats defined exactly | Same-attack contrasts on untouched pairs at about ±5 points, two or more families. The pilot gives Granite +10.5 (+3.8 to +17.1) and Qwen +1.6 (−2.2 to +5.7), Slack only | **Controlled replication** |
| Does an attacker who writes for JSON succeed against JSON? | ADI, arXiv:2607.05120: JSON-shaped "data injection" (fake objects, delimiter spoofing) on AgentDojo with tool output switched to JSON. GPT-5.2: 49.1% (s), against near-zero for instruction injection (0.0% to 0.7%, verbatim). It assumes the attacker knows the format (Sec. III-A). AutoDojo: black-box optimization on AgentDojo, including entries "shaped like the surrounding tool output"; no format varied | Neither varies the serialization with the payload fixed. Does escaped JSON (as `json.dumps` writes it) blunt format-aware payloads relative to free text, on models whose prompts are verified? ADI reports that models misread even escaped delimiters (Sec. III-C), which predicts little protection | A crossed design: payloads written for JSON, for text, and instruction baselines, each under both serializations, with delivery verified. Development on banking and Slack, confirmation on untouched pairs | **Potentially novel**, narrowed by ADI. Not established |
| Does choosing attacks per format confound format comparisons? | General adaptive-attack work (Nasr et al.; AutoDojo) optimizes per defense. No paper found that decomposes a format comparison into wording and format | Whether selected-attack comparisons in this literature are confounded in the same way | The pilot's decomposition (Qwen: 7.1 of 8.6 points are wording), applied to other published selected-attack comparisons | **Measurement and methods** |
| How repeatable are agent-security outcomes at temperature 0? | Pape et al. and Masoudian et al.: the backend shifts benchmark scores. Agent-security papers read here report single runs: AutoDojo (s), SARA's attack metrics (s), ADI (s) | Per-model disagreement rates on attack outcomes under one stack | Repeat subsets per model and stack. The pilot gives Qwen 0 of 126 and Granite 4 to 8 of 84 | **Measurement** |
| Do harnesses deliver what they claim? | Shaw: delivery against the environment; Tang and Zheng: serving stack and tool calls | Prompt-level delivery in other public harnesses (AgentDojo, InjecAgent, ToolHazard, ADI's extended AgentDojo) for their open-model settings | WP7: run the census fixtures through their message-building code. Free | **Measurement and methods**, the most promising |

**Assessment.**

- **Controlled replication.** A confirmatory same-attack study would turn ToolHazard's reported direction into an interval for two open models under one stack. It is useful, and the design is ready ([proposal](proposal-confirmatory-serialization.md)). It is not new.
- **Measurement contribution.** These are reproducible and partly done:
  - the corrected record;
  - the rendering census;
  - the prompt-level delivery check;
  - the wording/format decomposition;
  - repeatability under one stack.
  
  Its weight depends mostly on WP7: whether the check finds problems in other groups' published setups.
- **Potentially novel finding.** Only the second row: serialization against attacks written for it. ADI shows format-aware JSON injection works and leaves the serialization comparison open. That question needs a new attack family (data injection, not instruction injection), new development work, and probably new scoring. It is a revised direction, not a continuation of this design.
- **Is another serialization experiment the best next investment? No.** The registered-style study would cost $11 to $21 and produce a replication. The free WP7 audit decides whether the methods contribution is worth writing up, and it costs nothing.

## 4. Spending

From billing records read 2026-11-16 15:17 UTC ([ledger](https://github.com/fcavaletto/prompt-injection-eval/blob/research-audit-2026-11/results-published/spending-ledger.md)):

- **Pilot:** $5.1845 (Qwen $3.7038, Granite $1.4807; estimate was $5.23).
- **Project total:** $18.7115. **$31.2885 of $50 remains.**
- **Unrelated account items, left untouched:** 2026-11-10 pods $1.1116, and network volume `vlm-research-eu-se-1`, $0.701 to date, accruing about $0.117 a day. The account total for 2026-11-10 to 2026-11-16, $20.5239, equals the project's costs plus these two items.
- No pods exist.

## 5. Options

Costs come from `scripts/cost_next_stage.py`. They include controls (three runs) and the repeat subset (60 pairs, two extra runs), plus overhead. Throughput is scaled from Slack by 0.7 (central) and 0.5 (conservative), at 7 and 11 calls per attack episode. Qwen's pilot host was slow; a faster host could roughly halve Qwen's share.

| Option | Work | Cost, central / conservative | Strongest defensible claim |
| --- | --- | --- | --- |
| **0. Conclude and release** | Write up the record as it stands; run WP7 (free); merge the branch and tag a release when you decide to | $0 more | In two open models, on Slack with verified delivery, the best of eight wordings found for JSON did worse against JSON than the best found for text, by about 9 to 11 points. For Granite most of that was a same-attack format effect (about 10 points); for Qwen most was attack wording. Plus the corrected record, the census and the delivery check as methods |
| **A. Confirmatory same-attack study** (the proposal's core) | Fixed baseline × 2 formats × 700 reserved pairs, both models | $10.8 / $21.2 | JSON vs text changed a fixed injection's success by X (interval) per model on untouched pairs, with verified delivery: a controlled replication |
| A+G. A plus Granite's selection module | Adds `text_fake_turn` for Granite | $12.4 / $24.9 | A, plus whether Granite's format effect depends on the attack |
| B. Full frozen attack sets, both models | Adds Qwen's two selected attacks | $20.5 / $42.5 | A, plus selection transfer for both models. **The conservative case exceeds the remaining $31.29** |
| C. Granite only | Frozen set, one model | $5.4 / $10.7 | One model only; nothing about whether the effect depends on the model |
| D. Revised direction: format-aware data injection under two serializations | New payload family, development on banking and Slack, new scoring; then 2 attacks × 2 formats × 700 pairs, both models | $16.4 / $33.7 for evaluation, plus about $2 to $4 of development. **The conservative case exceeds the remainder** | If it held: whether escaping in JSON serialization blunts attacks written for JSON, on open models. Possibly novel, narrowed by ADI |

## 6. Recommendation

*Note 2026-11-16, later: WP7 has been run ([WP7](wp7-audit.md)). It found two issues in AgentDojo's published open-model path and clean passes elsewhere. The updated recommendation is in the [report draft](report-draft.md), section 12. It still recommends against another serialization experiment now.*

**Conclude this line with the current evidence, and release it as a methods and replication report. Run the free WP7 audit first. Do not spend the remaining budget on another serialization experiment now.**

- **The registered gate does not support progression.** Read conservatively, section 9.8 is not met, and waiving it after seeing the result would not be defensible.
- **The available studies are replications.** The study that fits the budget (A) would be a controlled replication of a direction ToolHazard already reported. The question that could be new, serialization against format-aware injection, is a different design that does not fit the budget conservatively, and ADI has already narrowed it.
- **The decision should wait on WP7.** If WP7 finds delivery problems in other groups' published setups, the methods paper has its central result, and option A would be a reasonable, affordable confirmatory appendix: register the [proposal](proposal-confirmatory-serialization.md) first, then run it. If WP7 finds nothing, the record as it stands is a short replication report and the line should end there.

Decisions that are yours:

1. Accept or reject this recommendation.
2. Whether to merge `research-audit-2026-11` into `main` and tag a release. Not done.
3. Whether to authorize option A, or any other, after WP7.
4. The network volume and the 2026-11-10 pods are not this project's. Whether to keep the volume is your call; it was not touched.
