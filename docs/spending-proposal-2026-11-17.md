# Spending proposal (2026-11-17): three separately gated stages

**No paid call, rental or launch is authorized by this document.** Each stage needs its own explicit approval. The first two together request at most **$13**. The adaptive stage cannot start because a progression rule passed: it needs a later, separate approval.

| Stage | Proposed cap | Status | Central / high estimate | Enforcement |
| --- | ---: | --- | --- | --- |
| Granite Stage 1 ([protocol](protocol-stage1.md), Amendment 4) | **$8** | Awaiting approval | $1.74 / $5.56 | in-pod expiry deletes the pod; client deadlines; one pod session per batch |
| OpenRouter feasibility screen, calibration included ([protocol](protocol-openrouter.md)) | **$5** | Awaiting approval | $0.14 / $3.74 | durable ledger (reserve before sending, charged until reconciled, crash-safe, single process); a required service-side key limit no larger than $5; key-usage reconciliation; 1,200-call cap; `max_tokens` 4096; `max_price` routing ceiling |
| Adaptive follow-up ([protocol](protocol-adaptive.md)) | **$18** | Conditional; needs a later approval | $4.25 / $15.85 | in-pod expiry; designed in detail only after Stage 1's progression decision is written down |

**Budget.**

- The ledger (2026-11-16) shows $18.71 spent of the project's $50, so $31.29 remains.
- All three caps together come to $31, which leaves $0.29.
- If the adaptive stage is ever approved, the ledger should be re-read first.
- The unrelated network volume noted in the ledger accrues on the account, outside this project.

## GPU stages: what the estimate includes

**Price.** $2.69/h, RTX PRO 6000 Blackwell Server Edition, Secure cloud, read from RunPod `list-gpu-types` on 2026-11-17. It must be re-read immediately before rental.

**Per pod session:**

- **Startup, including image pull, weight download and model loading:** 5.98 minutes measured for Granite with a cached image. The high case assumes 15 minutes.
- **Rendering check:** 1 minute.
- **Idle:** 2 minutes.
- **Shutdown margin:** 5 minutes.
- **Storage:** 150 GB of container disk at $0.10/GB-month, about $0.02/h. Nothing persists after deletion, and no network volume is used.

**Stage 1 specifically:**

- **Sessions:** two, one per batch. Both are needed: the batches are scheduled independently.
- **Reruns:** 5% (central) or 10% (high).
- **High case:** every attack episode reaches the round limit, the host runs at half speed, and one extra failed start is allowed.
- **Cap mechanics:** (8 − 0.10) / 2.69 h − 5 min = **171 minutes** of pod lifetime, split as 85 minutes per session.

**Enforcement.**

- `scripts/pod_expiry.py` deletes the pod from inside at a fixed time, independently of the client.
- Client deadlines stop new episodes 3 minutes before expiry.
- Deletion is confirmed by listing pods.

## API stage: what the estimate includes

**Price.** Both models are $0.10 per million input tokens and $0.50 per million output tokens, on the pinned endpoints (OpenRouter endpoints API, 2026-11-17).

**Included in the estimate:**

- **Cumulative input across turns:** every call resends the conversation and the tools, starting at about 6.5k characters.
- **Reasoning tokens:** billed as output, inside `max_tokens`.
- **Retries:** up to three attempts per call.
- **Calibration:** 4 episodes.

**Enforcement, and its limits** ([screen protocol](protocol-openrouter.md) §6):

- **Local ledger.** Every attempt is reserved durably before it is sent, and stays charged until the API reports its cost. Timeouts, errors and missing usage stay charged. A crash leaves the reservations charged, and only one process can spend at a time.
- **The reservation bound** (request bytes plus a framing allowance; `max_tokens` for output) is conservative but not proven. A cost above it halts spending.
- **Backstop:** a dedicated OpenRouter key with a credit limit of at most $5, checked before launch and reconciled after each phase.
- **What cannot be proven.** The local ledger cannot prove a hard cap. The service-side key limit is the backstop, and whether one in-flight request can overshoot it is not documented.

## Launch order, if approved

1. **OpenRouter:** calibration (4 episodes), then a stop-and-check on routing, model, cost reporting and request-level delivery, then the screen (60).
2. **Granite Stage 1:**
   - batch 0 (510 episodes) in one session;
   - batch 1 (348) in a second session;
   - then the report and the written progression decision.
3. **Adaptive:** only after a further approval, with its own registration.

## Progression rules, summarized

**Stage 1 to an adaptive proposal: all four must hold** (Amendment 4):

- valid measurement;
- benign controls within 10 points;
- batch disagreement under 15% of cells;
- an informative security question, meaning a primary contrast clearly beyond or clearly within its threshold, or forged-data success of at least 10%.

No p-value is used, and a JSON advantage is neither required nor sufficient.

**The screen informs Stage 2 scope only.** It has no progression rule of its own and launches nothing.
