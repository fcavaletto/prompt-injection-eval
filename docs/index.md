# Prompt Injection Eval

Prompt-level defenses against indirect prompt injection look strong on a fixed set of attack documents. This project measures whether they hold against an attacker who has read the defense.

They do not. On 59 held-out documents, with one attempt each and no feedback, a strategy tuned on other documents succeeds 50 to 57 times against a generic "untrusted data" rule, where the static attacks succeeded 1 to 7 times. Against datamarking it succeeds 40/59 on Qwen3-4B, 47/59 on Qwen3-14B, and 22/59 on gpt-oss-20b, where the static attacks succeeded 1 to 3 times. One round of patching the template takes Qwen3-4B from 40/59 to 26/59.

Where the document sits matters too. On [ten open models](placement.md) at full precision, a document delivered as a raw tool result is easier to inject through than the same document in the user message under the same security rule, on every model: the plain override succeeds 43/59 on Qwen3-32B instead of 4/59. JSON-encoding the tool message takes much of that back, which also explains an apparent gpt-oss exception reported in 0.5.0. With the rule in place, an adaptive strategy still succeeds on 45 to 58 of 59 in either placement, on every model.

![Attack success on the 59 held-out seeds, by model and defense](assets/static_vs_adaptive.png)

- [Adaptive attacks](adaptive.md) is the main result: method, tables, ablation, the result without the blank character, quiet attacks, transfer, the patch round, the tool-result placement, and limits.
- [Where the document sits](placement.md) reruns the protocol on ten models from five developers and corrects one earlier claim.
- [Static results](results.md) is the earlier study the adaptive one re-examines: 105 cases, three prompt conditions, four local models.
- If you are new to this problem, start with the [guide](learn.md). It takes about twenty minutes and needs no install. The [walkthrough notebook](notebooks/01_walkthrough.ipynb) then runs the same ideas on a mock model.

These are small quantized local models, 24 hand-written strategies, and synthetic documents. The numbers are a lower bound on the attacker and say nothing about deployed systems.
