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

Price read before each rental: $2.69/h, Secure, RTX PRO 6000 Blackwell 96 GB; 150 GB container disk.

| Pod | Model | In-pod expiry (allocation) | Lifetime | Amount | Source |
| --- | --- | --- | ---: | ---: | --- |
| `pxrrdap88tin5c` | Qwen3-32B | 214 min ($10.00) | about 82.5 min | 3.7038 | billing record, read 2026-11-16 15:17 UTC (GPU 3.6778, disk 0.0260; 11:00 to 13:00) |
| `1jlad7wd8u3l3o` | Granite 4.0 H Small | 324 min ($15.00) | about 33.2 min | 1.4807 | billing record, same read (GPU 1.4685, disk 0.0122; 12:00 to 14:00) |
| | **Pilot** | | | **5.1845** | of the $20 allowance; the pre-billing estimate was 5.23 |

Neither expiry was reached; both pods were deleted by the client and `list-pods` returned no pods afterwards.

**Project total after the pilot: $18.7115 (billing records); $31.2885 of $50 remains.** Records are billing-API figures and can still be revised.

## Reconciliation with the account (2026-11-10 to 2026-11-16, read 2026-11-16 15:17 UTC)

| | Amount |
| --- | ---: |
| Account total, all resources (`list-billing`, daily buckets) | 20.5239 |
| Attributed to this project (above) | 18.7115 |
| 2026-11-10 pods, not attributed (day bucket; the per-pod records above sum to 1.1112) | 1.1116 |
| Network volume `0uhv9a501u`, not attributed, 2026-11-10 to now | 0.7010 |
| Difference | 0.0000 (rounding: −0.0002) |

The account total therefore splits exactly into this project's costs and the two unrelated items. The network volume still accrues about $0.117 a day. Nothing unrelated was touched. `list-pods` returned no pods at the same time.
