# Delivery-checker validation (2026-11-17)

Offline: no model was called. The specification and the expected verdict of every mutation class are in [docs/measurement-contract.md](../../docs/measurement-contract.md). They were committed together with the results of the *unchanged* checkers (`results_v1.json`, commit `15a2279`) before any checker was changed.

## Inputs

- **Corpus:** one stored pilot request, in both formats, rendered with both pinned templates (four base cases); 37 mutation and variant types; 146 pilot cases in all.
- **Valid variants re-render identically.** Every valid variant built by substitution (V1, V5a, V5b; 12 cases) is byte-identical to what the pinned tokenizer renders for its messages (`template_verification` in `results_v2.json`).
- **WP7 corpus:** the five stored WP7 renderings, each valid (W0) and under four mutations (W1 to W4).

## Results

Detections = rejects of mutations expected to be rejected. False alarms = rejects of variants expected to be accepted.

| Class | Should reject | Archived pilot check (`delivery.check`) | Contract check (`delivery.check_contract`) |
| --- | ---: | ---: | ---: |
| valid (should accept) | 0 of 24 | 0 false alarms | 0 false alarms |
| role | 24 | **0** | 24 |
| schema | 16 | 16 | 16 |
| arguments | 20 | **12** (misses int→float, int→bool) | 20 |
| duplicates | 12 | **0** | 12 |
| order | 12 | 12 | 12 |
| association | 8 | 8 | 8 |
| truncation | 16 | **12** (misses a missing generation header) | 16 |
| payload | 14 | 14 | 14 |

| WP7 | Should reject | Archived `wp7.check` | `wp7.check(strict=True)` |
| --- | ---: | ---: | ---: |
| W0, five stored renderings (should accept) | 0 of 5 | 0 false alarms | 0 false alarms |
| W1 to W4: parameter renamed, declared type changed, argument key renamed, argument scalar type changed | 20 | **0** | 20 |

**On real prompts** (`kept_prompts_contract.json`): every full prompt the pilot, F1 and the smoke test kept from the server, 787 in all, passes the contract check.

- 383 of them are JSON-format prompts, checked completely.
- 404 are text-format prompts. For these the record items (K5 record equality, K7 payload) were skipped, because text records cannot be recovered without their shapes. Structure, roles, schemas, calls and verbatim results were checked.

## What this establishes and what it does not

- **The archived pilot check could not have detected some defect classes.** It did not check roles or turn structure. It accepted duplicated schemas, calls and results, `1` for `true` and `1.0`, and a missing generation header.
- **These gaps do not invalidate the archived pilot outcomes.**
  - All 21,321 turns of scored pilot episodes matched, by SHA-256, a local rendering of the stored conversation with the pinned template; that is a reconstruction (see the [measurement contract](../../docs/measurement-contract.md), section 6) ([supplementary tables](../pilot-2026-11-16/supplementary-2026-11-17/README.md), section 7). Any of these defects would have changed the hash.
  - The 787 kept prompts pass the repaired check.
  - So the pilot's delivery claim rests on hash equality with the pinned template, and the contract check confirms it where full prompts were kept.
  - What the hash cannot rule out is a template that itself mis-renders. The contract check guards against that only for the profiles in the specification.
- **WP7's verdicts are unchanged under the strict items:** all five stored renderings pass. Its claims are narrowed to what it checks:
  - names, descriptions and parameter markers;
  - each parameter's own name and declared type next to its marker;
  - the call's argument key and string value;
  - the result and payload in a recognized encoding;
  - the order of the parts.

  It does not decode schemas for equality, and it certifies nothing beyond the one fixture.
- **Mutation counts are evidence against the tested fault classes, not proof of completeness.** 122 of 122 means every constructed defect in these classes was detected. A defect outside them, or another instance of one, could pass.
- **Coverage is what was tested:** these mutation classes, these two templates and the scripted stand-in, one history. No universal semantic fidelity is claimed. In particular, nothing here addresses whether a *reader* can separate data from structure; free text cannot always do so (contract, section 4).

## Reproduce

```bash
HF_HUB_OFFLINE=1 python scripts/build_checker_corpus.py          # only to rebuild the base cases; needs tokenizer files
python scripts/validate_checkers.py --label v2 --output <dir>       # add --verify-templates with tokenizer files
python scripts/recheck_kept_prompts.py results-published/pilot-2026-11-16 results-published/pilot-f1-2026-11-16 results-published/pilot-smoke-2026-11-15 --output <file>
pytest tests/test_checker_contract.py
```
