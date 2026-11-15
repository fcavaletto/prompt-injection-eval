# Provenance

## Code that ran

The manifest (`smoke/manifest.json`, kept exactly as written) records `git_commit` `d35910ccf9b4c2f059b2083b5c58e61248b942d0` and `git_dirty: true`.

The working tree differed from that commit in one file, `docs/pilot-design.md`: the launch section (9.2) was being rewritten to show the pod start command. That edit was committed afterwards, unchanged, as `615778a3b4d5471041d1e46f66a8e6c15e6f172b` (2026-11-15 20:33:34 +0100, about 1.5 minutes after the smoke ended).

What supports "no code differed":

- `git diff d35910c 615778a` touches only `docs/pilot-design.md` (9 lines added, 5 removed), and is empty for `src/`, `tests/`, `scripts/` and `pyproject.toml`.
- Immediately after that commit, `git status --short` listed no modified tracked file, so no other tracked file differed from `d35910c` at that point.
- The package was installed in editable mode, so the code that ran was the working tree's `src/`.

What it does not cover:

- There is no snapshot of the working tree taken at run time. The statement rests on the commit made about 90 seconds after the run and on the session record that no other tracked file was edited in between.
- `git_dirty` is computed without untracked files. Untracked and ignored files are not covered. No untracked, non-ignored file existed when `615778a` was committed.
- The Python environment is not recorded beyond `agentdojo 0.1.35` (checked at run time) and the package version. In particular, the versions of `httpx`, `pydantic` and other dependencies are not pinned in the manifest.

## Inputs fixed by hash

- AgentDojo 0.1.35, benchmark v1.2.2; banking suite hash `dd40d8e04b483dd8a674a181cd94c47ed0edd2aab96df2bf283375d94230e244` (in the manifest).
- Attack library hash `bfb5fea427caa36ccc7bfcd18c47acfa7726782d93b8bfeab86eda621a7b94a8`. The smoke used only the fixed baseline attack.
- Smoke criterion `smoke-v1`, fixed in `d35910c` before any live inference.
- Every trace carries the manifest hash `952bb06762cb…` and a request fingerprint.

## Server

- Image `vllm/vllm-openai:v0.33.0`, digest `sha256:d825baf9ce4b1b6bfc5ecc7b79880c7e6748c65a72d697ce3d47607aafa84c6e` (from the pod's system log).
- Model `Qwen/Qwen3-32B` at revision `9216db5781bf21249d130ec9da846c4624c16137` (from the vLLM startup log), bf16, 32,768 context, `--generation-config vllm`, `--enable-auto-tool-choice --tool-call-parser hermes`.
- One RunPod pod, `s2nmfm4nus2go4`, RTX PRO 6000 Blackwell 96 GB, Secure Cloud, US-PA-1. The pod no longer exists.
- Thinking disabled per request (`chat_template_kwargs.enable_thinking = false`). Confirmed in the returned prompts, which end with an empty think block.

## Rehearsal pod

A separate CPU pod, `91iemjqlup83kd`, tested the expiry script before the GPU pod was rented. No model ran on it. See `run_record.json`.

## Redactions

None. The files were searched for API keys, authorization headers, bearer tokens, signed URLs, server addresses, IP addresses, e-mail addresses, home-directory paths and the author's name or e-mail.

- **"password":** occurs only in AgentDojo's synthetic `update_password` tool schema and task text.
- **Server address:** the pod's proxy address was never written to any file. The client read it from an environment variable that is not recorded.
- **Pod identifiers:** both pod IDs are kept. They name resources that have been deleted and are neither addresses nor credentials.
- **`0.0.0.0`:** appears once, as vLLM's bind address in the log excerpt.
