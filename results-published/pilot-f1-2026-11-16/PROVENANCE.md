# Provenance

**Code.** All three phases ran at commit `d152041a…` (`git_dirty: false` in each manifest). That commit fixed the plan, the order of the feasibility workload and its accounting before any F1 inference. CI passed on it, for both the main and pilot jobs, before the first pod was rented.

**Data.** AgentDojo 0.1.35, benchmark v1.2.2, banking suite only. The suite hash is in each manifest.

**Granite server (F1a).**

- Pod `t5ze8z024whrwy`, deleted.
- Image `vllm/vllm-openai:v0.33.0`, digest `sha256:d825baf9…84c6e`.
- Model `ibm-granite/granite-4.0-h-small` at revision `b8c0982bab7fde4eb48110f5a069527c008fab39`, bf16, 32,768 context, `--generation-config vllm`, `--tool-call-parser granite4`.
- No thinking switch.

**Qwen server (F1b).**

- Pod `lnumay2bk1o50t` in EUR-IS-2, deleted.
- Same image.
- Model `Qwen/Qwen3-32B` at revision `9216db5781bf21249d130ec9da846c4624c16137`, bf16, 32,768 context, `--generation-config vllm`, `--tool-call-parser hermes`.
- Thinking disabled per request.

`PIE_OPENAI_LAUNCH_ARGS`, which is recorded in each manifest, describes only the server configuration. Pod IDs and data centers are recorded here and in `run_record.json`.

**Expiry.** Each pod ran `scripts/pod_expiry.py` in the background with an absolute expiry time. Neither expiry was reached: both pods were deleted by the client first.

**Redactions.** The files were searched for API keys, authorization headers, bearer tokens, signed URLs, server addresses, IP addresses, e-mail addresses, home-directory paths and the author's name or e-mail. Nothing was found in the traces, manifests, reports or checks. One redaction was made:

- **What:** the access-log lines copied from the Qwen pod's server log.
- **Why:** each showed a client address in 100.64.0.0/10, RunPod's internal proxy network.
- **How:** those lines are omitted from `qwen3-32b/server_log_excerpt.txt`, which says so. No other field was changed.

Pod IDs are kept; they name deleted resources and are neither addresses nor credentials. The occurrences of "password" are AgentDojo's synthetic `update_password` tool.
