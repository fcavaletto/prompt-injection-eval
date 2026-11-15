# Related work

Seven sources are enough to see where this project sits. Each note says what it is, what this repository borrows, and what it deliberately does not do. Read them in this order if you are new.

## Indirect prompt injection

Kai Greshake, Sahar Abdelnabi, Shailesh Mishra, Christoph Endres, Thorsten Holz, and Mario Fritz. "Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection." arXiv:2302.12173, 2023. Also in the *Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security* (AISec 2023).

The paper's point is that the attacker does not have to type the prompt. They can put instructions in data the application will retrieve: a web page, an email, a document. The model then treats that data as something to obey. They show this against real systems, including retrieval-backed chat, and they treat the blur between data and instructions as the vulnerability.

**Borrowed.** The threat model. The attacker controls the document. The user task is legitimate. The system instruction is trusted and is not the attack surface under test.

**Not done here.** No retrieval system, no tools, no API calls, no attempt to compromise a product. The documents are synthetic and the payloads are canaries. Greshake et al. show that the problem reaches deployed applications. This repository measures one narrow slice of it on local open-weight models.

## Direct prompt injection, as the contrast

Fábio Perez and Ian Ribeiro. "Ignore Previous Prompt: Attack Techniques For Language Models." arXiv:2211.09527, 2022. NeurIPS 2022 Workshop on Machine Learning Safety.

This is the earlier, direct version: the user types an attack such as "ignore previous instructions" into the model's input. Their PromptInject framework measures goal hijacking and prompt leaking against GPT-3, with a simple string match for whether the model emitted a target.

**Borrowed.** The idea that a canary plus an exact check is a usable first measurement, and that small wording changes move the result. Several cases in this dataset end with an "ignore the user task" line. That wording is a descendant of this paper. The difference is where the line sits: here it is inside a document the user asked the model to analyze, not in the user turn itself.

**Not done here.** No search for the best attack string, no prompt leaking of a hidden system prompt as the main metric, and no claim that these hand-written sentences are strong attacks. Perez and Ribeiro vary the attack. This project holds the attack fixed and varies the prompt template around the document.

## Spotlighting

Keegan Hines, Gary Lopez, Matthew Hall, Federico Zarfati, Yonatan Zunger, and Emre Kıcıman. "Defending Against Indirect Prompt Injection Attacks With Spotlighting." arXiv:2403.14720, 2024.

Spotlighting is a family of prompt-only defenses. The model sees one stream of text and cannot tell which part came from the user and which part came from untrusted data. Spotlighting tries to make provenance visible. The paper describes three versions: delimiting (markers around the untrusted span), datamarking (a special character interleaved through the untrusted text), and encoding (transforming the untrusted text, for example with Base64). On their GPT-family experiments they report a large drop in attack success. That number is about their documents, their models, and their encoding. It is not a result of this repository.

**Borrowed.** The datamarking idea, in a simpler form. Condition `spotlight` (`defended-v2`) replaces each run of whitespace in the document with `^` and tells the model that marked text is data. `defended-v1` is closer to delimiting plus a refusal rule: the document sits between "untrusted document" markers and the model is told not to follow instructions inside it. Both defenses stay in the user message. The system instruction is identical to baseline.

**Not done here.** No Base64 encoding variant. The marker is the ASCII caret, not a private-use Unicode character. The template tells the model not to copy `^` into the answer, because a leaked marker would make keyword checks harder to read and would itself be a utility failure. Do not cite Hines et al.'s attack-success drop as if these local runs had reproduced it. The comparison that belongs to this project is in [results](results.md).

## Adaptive attacks: the evaluation standard

Milad Nasr, Nicholas Carlini, and coauthors. "The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Against LLM Jailbreaks and Prompt Injections." arXiv:2510.09023, 2025.

Qiusi Zhan, Richard Fang, Henil Shalin Panchal, and Daniel Kang. "Adaptive Attacks Break Defenses Against Indirect Prompt Injection Attacks on LLM Agents." NAACL 2025 Findings. arXiv:2503.00061.

Both papers make the same argument with different tools. A defense that is tested only against attacks written before the defense existed has not been tested. Nasr et al. take twelve published defenses that reported near-zero attack success and break most of them above 90% with gradient search, reinforcement learning, random search, and human red teams. Zhan et al. bypass eight indirect-injection defenses on tool-using agents with attacks built for each one.

**Borrowed.** The standard itself. The [adaptive study](adaptive.md) exists because the 0.3.0 result, datamarking at 0 to 4 successes out of 89, was measured against attacks that could not respond to the defense. The study also borrows the habit of saying exactly what the attacker knows and how many queries they get.

**Not done here.** No gradients, no reinforcement learning, no human red team, no agents. The adaptive attacker in this repository is deliberately cheap: sixteen text recipes written after reading the templates, ranked on tuning seeds. That makes the result a lower bound on what an adaptive attacker can do, not an estimate of it. If a cheap attacker already breaks a defense, the stronger ones in these papers are not needed to make the point; where the cheap attacker fails, nothing follows.

## Attacker models

Patrick Chao, Alexander Robey, Edgar Dobriban, Hamed Hassani, George J. Pappas, and Eric Wong. "Jailbreaking Black Box Large Language Models in Twenty Queries." arXiv:2310.08419, 2023.

PAIR uses one language model to attack another. The attacker model proposes a prompt, reads the target's reply, and revises, for a small number of rounds.

**Borrowed.** The loop, as the second attacker in the adaptive study: a local model writes the injected text, sees the target's reply, and tries again, five times at most.

**Not done here.** PAIR targets jailbreaks, runs many parallel streams, and uses a judge model to score replies. Here the goal is injection, there is one stream, and the deterministic scorers decide success. The study also adds a control PAIR does not have: the same attacker model with the same budget but no template and no feedback, so that "five tries" can be separated from "five informed tries".

## The industry checklist

OWASP. "LLM01:2025 Prompt Injection." *OWASP Top 10 for Large Language Model Applications*, version 2025. [genai.owasp.org/llmrisk/llm01-prompt-injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

OWASP lists prompt injection as the first risk for LLM applications and distinguishes direct from indirect injection. Indirect injection, in their wording, is instructions hidden in external content the model processes. They also list the practical consequences: data disclosure, unintended tool use, and content that bypasses controls. The page is a risk list for builders, not an evaluation method.

**Borrowed.** The name of the problem, and the reminder that a prompt-level instruction is not a control you should rely on by itself. The responsible-use notes in this repository match that: a low score here is not a deployment argument.

**Not done here.** No coverage of the rest of the Top 10, no scanner, and no mapping of these cases onto an OWASP compliance claim.

## Instruction hierarchy

Eric Wallace, Kai Xiao, Reimar Leike, Lilian Weng, Johannes Heidecke, and Alex Beutel. "The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions." arXiv:2404.13208, 2024.

OpenAI. "gpt-oss-120b & gpt-oss-20b Model Card." arXiv:2508.10925, 2025.

Wallace et al. argue that a model should give instructions different authority depending on where they come from, with the system prompt above the user and tool outputs below both, and train a model to behave that way. The gpt-oss model card describes the same idea as a role order: system, developer, user, assistant, tool.

**Borrowed.** The question the tool-result arm asks: does putting the document in the tool role make injected text in it weaker? On [ten open models](placement.md), including both gpt-oss models, it makes it stronger: a raw-text tool result undoes a security rule that works in the user message. An apparent exception on gpt-oss-20b in 0.5.0 came from the chat template JSON-encoding the tool message.

**Not done here.** No training, and no test of a model trained with the hierarchy on tool outputs specifically. The result says that, for these models as served, the tool role is not the protection the hierarchy describes.

*Correction, 2026-11-15:* the comparison did not isolate the tool role. On Qwen the tool result is rendered inside a user turn, two models had malformed tool turns, and the gpt-oss prompts cannot be checked. See [Corrections](corrections.md), C3, C4 and C9.

Charles Ye, Jasmine Cui, and Dylan Hadfield-Menell. "Prompt Injection as Role Confusion." arXiv:2603.12277, 2026.

They train linear probes that read which role a model thinks a token belongs to, on gpt-oss-20b and 120b, Nemotron-3 and Qwen3-30B, and find that text written in a user's style is still represented as largely user-like when it sits inside tool tags, and that how user-like injected text looks to the model predicts attack success.

**Borrowed.** Their account predicts the behavioral result here: if tool text reads as user text, a rule written about "the document" in the user message should lose force when the same document arrives as a tool result.

**Not done here.** No probes. The two studies are complementary: they measure the representation, this one measures paired attack success across placements, with a held-out protocol and a defensive rule.

## Agents, as the thing this is not

Edoardo Debenedetti, Jie Zhang, Mislav Balunović, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr. "AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents." NeurIPS 2024 Datasets and Benchmarks. arXiv:2406.13352.

AgentDojo gives a model tools — email, banking, travel bookings — and puts the attack in data a tool returns. Success is about whether the agent then takes a harmful action, not only whether it prints a canary. The environment is extensible so attacks and defenses can be added. Their headline is that capable tool-using models still fail many tasks, and that existing attacks break some security properties and not others.

**Borrowed.** The insistence on reporting utility and security separately. An agent that refuses every tool call is secure and useless. The same split is why this project has `secure_but_unhelpful`.

**Not done here.** No tools, no environment, no state-based check of a side effect. A model in this harness can only emit text. If it prints `CANARY_D01`, that is the entire compromise. The eight `tool_call_request` cases added in 0.3.0 ask the model to write a function call such as `forward_invoice(...)`, and the reports count how often a naive line parser would have found one. That is a text proxy borrowed from the shape of the AgentDojo question. Since 0.5.0 the adaptive study also delivers the document as a tool result: the conversation holds one `read_document` call and its output, rendered by each model's own chat template, and the model answers. That borrows AgentDojo's placement of the attack, in data a tool returns, but not its environment: one call, one turn, nothing executed. It says nothing about what an agent with real tools, real tool outputs, and multiple turns would do. AgentDojo is the right thing to read next if you want the version of this problem where the model can act. This repository stops one step earlier, on purpose: the measurement is about instruction-following on a document, and it can be run on a laptop with no API key.
