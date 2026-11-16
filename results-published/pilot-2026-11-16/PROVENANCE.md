# Provenance

**Code.**

- Amendment 3 and its implementation: `1f4c368`. CI passed both jobs (`test`, `pilot`) before the first pod was rented.
- Qwen3-32B's selection ran at `1f4c368` (`git_dirty: false`).
- Its Slack phases ran at `177312a`, which only adds its frozen attacks, gates, projection and reuse check.
- Granite 4.0 H Small's development phases ran at `177312a`; its Slack phases at `e37d3e4`, which adds its frozen attacks.
- Each manifest records its commit.
- The reporting fixes described in the README (hold-back message, percentage display) came after all runs. They touch no request, delivery, execution or scoring code.

**Data.** AgentDojo 0.1.35, benchmark v1.2.2. Banking for development, slack for evaluation; the suite hashes are in each manifest. Repeat subset and execution order: `data/pilot/amendment-3-evaluation-design.json` (subset hash `6b9be500…d88f1`).

**Servers.**

- Image `vllm/vllm-openai:v0.33.0`, digest `sha256:d825baf9…84c6e`, on both pods (from the pods' system logs).
- One RTX PRO 6000 Blackwell 96 GB per pod, Secure cloud, $2.69/h listed, 150 GB container disk, no volume.
- Qwen3-32B: pod `pxrrdap88tin5c`, US-PA-1, revision `9216db57…`, `--tool-call-parser hermes`, thinking disabled per request.
- Granite 4.0 H Small: pod `1jlad7wd8u3l3o`, CA-MTL-3, revision `b8c0982b…`, `--tool-call-parser granite4`.
- Both: bf16, 32,768 context, `--generation-config vllm`, 16 client workers.
- `PIE_OPENAI_LAUNCH_ARGS`, recorded in each manifest, describes the server configuration only. For Qwen it is identical to F1's, which the control-reuse check requires.

**Expiry.** Each pod ran `scripts/pod_expiry.py` in the background with an absolute expiry: Qwen 214 minutes after creation ($10.00 allocation), Granite 324 minutes ($15.00). Neither was reached. Both pods were deleted by the client.

**Server logs.** Not copied in full. The parts relied on are quoted in `run_record.json`:

- startup timing;
- image digest;
- KV cache size (Qwen 93,040 tokens, as in F1);
- that the server logged `200 OK` for every request around the proxy disconnects.

Access-log lines carry client addresses on RunPod's internal proxy network and are not reproduced.

**Redactions and scan.** The bundle was searched for API keys and tokens, authorization headers, signed URLs, pod proxy addresses, IP addresses, home-directory paths and the author's name or e-mail. Nothing was found. Pod IDs appear only in `run_record.json` and here; they name deleted resources and are neither addresses nor credentials. The e-mail addresses in traces (`dora@gmail.com`, `fred9246@gmail.com`, `@bluesparrowtech.com`, `@example.com` and others) are AgentDojo's synthetic fixtures. "password" occurrences are AgentDojo's synthetic `update_password` tool.
