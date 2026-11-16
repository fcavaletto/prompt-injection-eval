# Spending ledger

Project limit: **$50.00** all-in. Amounts are RunPod `list-pod-billing` / `list-billing` records (USD) unless marked as estimates. Records are billing-API figures, not invoices, and can be revised.

## Attributed to this project

| Date (UTC) | What | Resources | Amount | Source |
| --- | --- | --- | ---: | --- |
| 2026-11-13 | Studies A and B (ten models, vLLM) | pods `7i7v34ndif3lzz` $7.0028, `xivqfylylwtkuu` $3.2924, `g78a1bd64dc7at` $2.0114, `x45qa4atkq56i7` $0.0576 | 12.3642 | billing records, read 2026-11-16 |
| 2026-11-15 | Expiry rehearsal (CPU pod) | `91iemjqlup83kd` | 0.0027 | billing record |
| 2026-11-15 | Qwen3-32B smoke | `s2nmfm4nus2go4` | 0.2242 | billing record |
| 2026-11-15 | F1a, Granite smoke | `t5ze8z024whrwy` (GPU 0.2745, disk 0.0017) | 0.2762 | billing record |
| 2026-11-15 | F1b, Qwen controls and feasibility | `lnumay2bk1o50t` (GPU 0.6542, disk 0.0052) | 0.6594 | billing record |
| | **Total before the pilot** | | **13.5270** | |
| | **Remaining of $50** | | **36.4730** | |

F1's billed total, $0.935683, is below its pre-billing estimate of $0.952.

## Not attributed

Also on the account, with no mention anywhere in this repository:

- 2026-11-10: ten pods, $1.1112 in all (`s3uabwvn1a10q9`, `lpcwjejlq79ped`, `ulduogqygqs4d5` and seven CPU pods under $0.01 each).
- Network volume `0uhv9a501u` (`vlm-research-eu-se-1`, 50 GB, EU-SE-1): standard storage, about $0.117 a day since 2026-11-10 ($0.68 to 2026-11-16).

The earlier figure of "about $12.3 before the smoke" excluded both. They are listed here so that nothing is dropped silently. Counting them would leave about $34.2 of the $50; the $20 pilot allowance fits either way.

## Pilot (authorized 2026-11-16: at most $20 all-in across both models)

Filled in as pods are rented; see section 9.6c of the pilot design and the pilot's `run_record.json`.
