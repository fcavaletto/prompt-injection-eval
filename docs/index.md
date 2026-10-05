# Prompt Injection Eval

How often does a local open-weight model obey an instruction hidden in a document, and what does a prompt-level defense cost in usefulness?

On 36 synthetic attack cases, the automated attack-success count went from **5/36 to 1/36** for `deepseek-r1:14b` and from **9/36 to 3/36** for `qwen2.5:7b` when the user message said the document was untrusted data. Task success went from 21/40 to 28/40 on both models. Datamarking took those counts to 0/36 and 1/36. The 95% Wilson intervals for baseline and the generic defense overlap on DeepSeek and nearly overlap on Qwen, so the direction is shared and the size is not pinned down. The attacks do not adapt, and a prompt is not a security boundary.

If you are new to this problem, start with the [guide](learn.md). It takes about fifteen minutes and needs no install. The [walkthrough notebook](notebooks/01_walkthrough.ipynb) then runs the same ideas on a mock model. The [results](results.md) page is the study those numbers come from.
