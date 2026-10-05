# Related work

Five sources are enough to see where this project sits. Each note says what it is, what this repository borrows, and what it deliberately does not do. Read them in this order if you are new.

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

## The industry checklist

OWASP. "LLM01:2025 Prompt Injection." *OWASP Top 10 for Large Language Model Applications*, version 2025. [genai.owasp.org/llmrisk/llm01-prompt-injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

OWASP lists prompt injection as the first risk for LLM applications and distinguishes direct from indirect injection. Indirect injection, in their wording, is instructions hidden in external content the model processes. They also list the practical consequences: data disclosure, unintended tool use, and content that bypasses controls. The page is a risk list for builders, not an evaluation method.

**Borrowed.** The name of the problem, and the reminder that a prompt-level instruction is not a control you should rely on by itself. The responsible-use notes in this repository match that: a low score here is not a deployment argument.

**Not done here.** No coverage of the rest of the Top 10, no scanner, and no mapping of these 40 cases onto an OWASP compliance claim.

## Agents, as the thing this is not

Edoardo Debenedetti, Jie Zhang, Mislav Balunović, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr. "AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents." NeurIPS 2024 Datasets and Benchmarks. arXiv:2406.13352.

AgentDojo gives a model tools — email, banking, travel bookings — and puts the attack in data a tool returns. Success is about whether the agent then takes a harmful action, not only whether it prints a canary. The environment is extensible so attacks and defenses can be added. Their headline is that capable tool-using models still fail many tasks, and that existing attacks break some security properties and not others.

**Borrowed.** The insistence on reporting utility and security separately. An agent that refuses every tool call is secure and useless. The same split is why this project has `secure_but_unhelpful`.

**Not done here.** No tools, no environment, no state-based check of a side effect. A model in this harness can only emit text. If it prints `CANARY_D01`, that is the entire compromise. AgentDojo is the right thing to read next if you want the version of this problem where the model can act. This repository stops one step earlier, on purpose: the measurement is about instruction-following on a document, and it can be run on a laptop with no API key.
