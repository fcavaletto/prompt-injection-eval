## Checker validation, v2

| Checker | Class | Should reject | Detected | Should accept | False alarms |
|---|---|---:|---:|---:|---:|
| pilot_contract | valid | 0 | 0 | 24 | 0 |
| pilot_contract | role | 24 | 24 | 0 | 0 |
| pilot_contract | schema | 16 | 16 | 0 | 0 |
| pilot_contract | arguments | 20 | 20 | 0 | 0 |
| pilot_contract | duplicates | 12 | 12 | 0 | 0 |
| pilot_contract | order | 12 | 12 | 0 | 0 |
| pilot_contract | association | 8 | 8 | 0 | 0 |
| pilot_contract | truncation | 16 | 16 | 0 | 0 |
| pilot_contract | payload | 14 | 14 | 0 | 0 |
| pilot_v1 | valid | 0 | 0 | 24 | 0 |
| pilot_v1 | role | 24 | 0 | 0 | 0 |
| pilot_v1 | schema | 16 | 16 | 0 | 0 |
| pilot_v1 | arguments | 20 | 12 | 0 | 0 |
| pilot_v1 | duplicates | 12 | 0 | 0 | 0 |
| pilot_v1 | order | 12 | 12 | 0 | 0 |
| pilot_v1 | association | 8 | 8 | 0 | 0 |
| pilot_v1 | truncation | 16 | 12 | 0 | 0 |
| pilot_v1 | payload | 14 | 14 | 0 | 0 |
| wp7_strict | wp7-valid | 0 | 0 | 5 | 0 |
| wp7_strict | wp7 | 20 | 20 | 0 | 0 |
| wp7_v1 | wp7-valid | 0 | 0 | 5 | 0 |
| wp7_v1 | wp7 | 20 | 0 | 0 | 0 |

### Disagreements with the expected verdict

- `pilot_v1` qwen3-json:R1 (role): expected reject, got accept []
- `pilot_v1` qwen3-json:R2 (role): expected reject, got accept []
- `pilot_v1` qwen3-json:R3 (role): expected reject, got accept []
- `pilot_v1` qwen3-json:R4 (role): expected reject, got accept []
- `pilot_v1` qwen3-json:R5 (role): expected reject, got accept []
- `pilot_v1` qwen3-json:R6 (role): expected reject, got accept []
- `pilot_v1` qwen3-json:A4 (arguments): expected reject, got accept []
- `pilot_v1` qwen3-json:A5 (arguments): expected reject, got accept []
- `pilot_v1` qwen3-json:D1 (duplicates): expected reject, got accept []
- `pilot_v1` qwen3-json:D2 (duplicates): expected reject, got accept []
- `pilot_v1` qwen3-json:D3 (duplicates): expected reject, got accept []
- `pilot_v1` qwen3-json:T2 (truncation): expected reject, got accept []
- `pilot_v1` granite4-json:R1 (role): expected reject, got accept []
- `pilot_v1` granite4-json:R2 (role): expected reject, got accept []
- `pilot_v1` granite4-json:R3 (role): expected reject, got accept []
- `pilot_v1` granite4-json:R4 (role): expected reject, got accept []
- `pilot_v1` granite4-json:R5 (role): expected reject, got accept []
- `pilot_v1` granite4-json:R6 (role): expected reject, got accept []
- `pilot_v1` granite4-json:A4 (arguments): expected reject, got accept []
- `pilot_v1` granite4-json:A5 (arguments): expected reject, got accept []
- `pilot_v1` granite4-json:D1 (duplicates): expected reject, got accept []
- `pilot_v1` granite4-json:D2 (duplicates): expected reject, got accept []
- `pilot_v1` granite4-json:D3 (duplicates): expected reject, got accept []
- `pilot_v1` granite4-json:T2 (truncation): expected reject, got accept []
- `pilot_v1` qwen3-text:R1 (role): expected reject, got accept []
- `pilot_v1` qwen3-text:R2 (role): expected reject, got accept []
- `pilot_v1` qwen3-text:R3 (role): expected reject, got accept []
- `pilot_v1` qwen3-text:R4 (role): expected reject, got accept []
- `pilot_v1` qwen3-text:R5 (role): expected reject, got accept []
- `pilot_v1` qwen3-text:R6 (role): expected reject, got accept []
- `pilot_v1` qwen3-text:A4 (arguments): expected reject, got accept []
- `pilot_v1` qwen3-text:A5 (arguments): expected reject, got accept []
- `pilot_v1` qwen3-text:D1 (duplicates): expected reject, got accept []
- `pilot_v1` qwen3-text:D2 (duplicates): expected reject, got accept []
- `pilot_v1` qwen3-text:D3 (duplicates): expected reject, got accept []
- `pilot_v1` qwen3-text:T2 (truncation): expected reject, got accept []
- `pilot_v1` granite4-text:R1 (role): expected reject, got accept []
- `pilot_v1` granite4-text:R2 (role): expected reject, got accept []
- `pilot_v1` granite4-text:R3 (role): expected reject, got accept []
- `pilot_v1` granite4-text:R4 (role): expected reject, got accept []
- `pilot_v1` granite4-text:R5 (role): expected reject, got accept []
- `pilot_v1` granite4-text:R6 (role): expected reject, got accept []
- `pilot_v1` granite4-text:A4 (arguments): expected reject, got accept []
- `pilot_v1` granite4-text:A5 (arguments): expected reject, got accept []
- `pilot_v1` granite4-text:D1 (duplicates): expected reject, got accept []
- `pilot_v1` granite4-text:D2 (duplicates): expected reject, got accept []
- `pilot_v1` granite4-text:D3 (duplicates): expected reject, got accept []
- `pilot_v1` granite4-text:T2 (truncation): expected reject, got accept []
- `wp7_v1` AD-1:W1 (wp7): expected reject, got accept []
- `wp7_v1` AD-1:W2 (wp7): expected reject, got accept []
- `wp7_v1` AD-1:W3 (wp7): expected reject, got accept []
- `wp7_v1` AD-1:W4 (wp7): expected reject, got accept []
- `wp7_v1` AD-2:W1 (wp7): expected reject, got accept []
- `wp7_v1` AD-2:W2 (wp7): expected reject, got accept []
- `wp7_v1` AD-2:W3 (wp7): expected reject, got accept []
- `wp7_v1` AD-2:W4 (wp7): expected reject, got accept []
- `wp7_v1` AD-3:W1 (wp7): expected reject, got accept []
- `wp7_v1` AD-3:W2 (wp7): expected reject, got accept []
- `wp7_v1` AD-3:W3 (wp7): expected reject, got accept []
- `wp7_v1` AD-3:W4 (wp7): expected reject, got accept []
- `wp7_v1` IA-1:W1 (wp7): expected reject, got accept []
- `wp7_v1` IA-1:W2 (wp7): expected reject, got accept []
- `wp7_v1` IA-1:W3 (wp7): expected reject, got accept []
- `wp7_v1` IA-1:W4 (wp7): expected reject, got accept []
- `wp7_v1` TH-1:W1 (wp7): expected reject, got accept []
- `wp7_v1` TH-1:W2 (wp7): expected reject, got accept []
- `wp7_v1` TH-1:W3 (wp7): expected reject, got accept []
- `wp7_v1` TH-1:W4 (wp7): expected reject, got accept []
