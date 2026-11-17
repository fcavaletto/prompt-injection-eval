# Prompt Injection Eval

A measurement harness for indirect prompt injection in tool-using agents. Every request is checked for what reaches the model.

**Status, 2026-11-17: a research checkpoint, not a release.** The report is a draft, independent human review is pending, and the next study is designed but not run.

## Read in this order

1. [Report draft](report-draft.md): what reaches the model, and whether tool-output serialization changes injection success.
2. [Claim–evidence table](claim-evidence.md): every current headline, its status (confirmed, conditional, unsupported, unresolved) and its evidence.
3. [Corrections](corrections.md): C1 to C24.
4. [Evidence index](evidence-index.md): where the evidence lives and what checks it.
5. [Pre-registration](preregistration.md) and [reproduction guide](reproduce.md).

## Plans

- **Current plan: the [Stage 1 protocol](protocol-stage1.md)**. It asks why JSON resisted AgentDojo's attack, and whether a forged-data attack is affected. It is not run and not authorized. The [adaptive follow-up](protocol-adaptive.md) comes after it and is costed separately.
- **Superseded plans,** kept for the record: [Research audit and next step](research-next-step.md) (2026-11-14/15), [Next stage](next-stage-2026-11-16.md) (2026-11-16), and the [unregistered confirmatory proposal](proposal-confirmatory-serialization.md) (2026-11-16).

## Methods

[Measurement contract](measurement-contract.md) · [Pilot design](pilot-design.md) · [WP7 harness audit](wp7-audit.md) · [Rendering census](rendering-census.md)

## History

The earlier studies (static benchmark, adaptive attacker, placement, InjecAgent) and the previous front page are in the [historical overview](history.md). Their claims carry the corrections listed above, and none of the current findings rests on their text-based scorer.
