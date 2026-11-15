#!/usr/bin/env python
"""Rendering census: how templates and serving code turn one conversation into a prompt.

The census takes a few fixed conversations (data/rendering_census/fixtures.json),
renders them with each sampled model's chat template (data/rendering_census/sample.json)
and records what survives: tool definitions, completed calls, tool results, message
boundaries and how tool output is serialized. No model weights are downloaded and no
text is generated.

Each row says how it was obtained:

- ``transformers``: rendered by ``tokenizer.apply_chat_template`` of the pinned revision.
  The actual implementation, but a tokenizer-level observation, not a server.
- ``transformers_jinja``: the template file rendered by the Jinja environment transformers
  uses, without the tokenizer (used when a tokenizer needs remote code, which is not run).
- ``vllm_replay``: prompts that vLLM 0.33.0 returned during Study B, compared with a
  transformers rendering of the same conversation. Server observations of the Study B
  conversations, not of the census fixtures.
- ``ollama_template``: Ollama library templates rendered by Ollama's own template and
  renderer packages (scripts/ollama_render). Code-level, not a running server.

Usage:
    python scripts/rendering_census.py transformers
    python scripts/rendering_census.py vllm-replay
    python scripts/rendering_census.py ollama --renderer /path/to/ollama_render
    python scripts/rendering_census.py summary
"""

from __future__ import annotations

import argparse
import csv
import copy
import datetime as dt
import gzip
import hashlib
import json
import platform
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "rendering_census" / "fixtures.json"
SAMPLE = ROOT / "data" / "rendering_census" / "sample.json"
OUT = ROOT / "results-published" / "rendering-census-2026-11-15"
STUDY_B = ROOT / "results-published" / "v08"

# Role headers of the template families in the sample. The census reports the last
# header before a tool result as the turn that carries it.
ROLE_HEADERS = [
    r"<\|im_start\|>\s*(\w+)",
    r"<\|start_header_id\|>\s*(\w+)\s*<\|end_header_id\|>",
    r"<\|start_of_role\|>\s*([\w ]+?)\s*<\|end_of_role\|>",
    r"<\|start\|>\s*([^<]+?)\s*(?:<\|channel\|>[^<]*)?<\|message\|>",
    r"<start_of_turn>\s*(\w+)",
    r"<\|turn>\s*(\w+)",
    r"<\|(user|assistant|system|tool|tool_response|observation|ipython)\|>",
    r"<\|header_start\|>\s*(\w+)\s*<\|header_end\|>",
    r"\[(TOOL_RESULTS|AVAILABLE_TOOLS|INST|SYSTEM_PROMPT)\]",
    r"<｜(tool▁outputs▁begin|tool▁output▁begin|User|Assistant)｜>",
    r"<\|im_(?:user|assistant|system)\|>\s*(\w+)\s*<\|im_middle\|>",
    r"<extra_id_1>\s*(\w+)",
]
DATE = re.compile(
    r"\b(20\d\d-\d\d-\d\d|\d{1,2} [A-Z][a-z]{2,8},? 20\d\d|[A-Z][a-z]{2,8} \d{1,2}, 20\d\d)\b"
)


def sha(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def load_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


def hostile_content(conv: dict[str, Any], variant: str) -> Any:
    record, raw = conv["record"], conv["raw_text"]
    if variant == "raw":
        return raw
    if variant == "json":
        return json.dumps(record)
    if variant == "yaml":
        return yaml.safe_dump(record).strip()
    if variant == "parts":
        return [{"type": "text", "text": raw}]
    raise ValueError(variant)


def cases(fx: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("single_call", "default"),
        ("single_call", "args_string"),
        ("single_call", "no_system"),
        ("single_call", "no_tools"),
        ("multi_tools", "default"),
        ("hostile_output", "raw"),
        ("hostile_output", "json"),
        ("hostile_output", "yaml"),
        ("hostile_output", "parts"),
        ("multi_turn", "default"),
    ]


def build(
    fx: dict[str, Any], name: str, variant: str, flavour: str = "hf"
) -> tuple[list, list | None, dict]:
    """Messages and tools for one fixture and variant.

    ``flavour`` is ``hf`` (the transformers message format) or ``ollama`` (the Ollama
    /api/chat format). Both describe the same conversation.
    """
    conv = fx["conversations"][name]
    source = conv["messages"]
    if isinstance(source, str):
        source = fx["conversations"][source]["messages"]
    messages = copy.deepcopy(source)
    if variant == "no_system":
        messages = [m for m in messages if m["role"] != "system"]
    out = []
    for m in messages:
        m = dict(m)
        if m.get("content") == "<<TOOL_OUTPUT>>":
            m["content"] = hostile_content(conv, variant)
        if "tool_calls" in m:
            calls = []
            for c in m["tool_calls"]:
                args: Any = c["arguments"]
                if variant == "args_string":
                    args = json.dumps(args)
                if flavour == "ollama":
                    calls.append(
                        {"id": c["id"], "function": {"name": c["name"], "arguments": args}}
                    )
                else:
                    calls.append(
                        {
                            "type": "function",
                            "id": c["id"],
                            "function": {"name": c["name"], "arguments": args},
                        }
                    )
            m["tool_calls"] = calls
        if flavour == "ollama" and m["role"] == "tool":
            m["tool_name"] = m.pop("name")
        out.append(m)
    tools = None if variant == "no_tools" else [fx["tools"][t] for t in conv["offered"]]
    return out, tools, conv


def carrier(before: str) -> tuple[str | None, str | None]:
    """The last role header before a tool result, and the role it names."""
    best: tuple[int, str, str] | None = None
    for pattern in ROLE_HEADERS:
        for match in re.finditer(pattern, before):
            if best is None or match.end() > best[0]:
                best = (match.end(), match.group(0), match.group(1))
    return (best[1], best[2].strip()) if best else (None, None)


def content_encoding(rendered: str, content: Any, marker: str) -> str:
    if isinstance(content, list):
        text = content[0]["text"]
        if text in rendered:
            return "parts_flattened_verbatim"
        if marker in rendered:
            return "parts_serialized_as_list"
        return "absent"
    if content in rendered:
        return "verbatim"
    if json.dumps(content)[1:-1] in rendered:
        return "json_escaped_ascii"
    if json.dumps(content, ensure_ascii=False)[1:-1] in rendered:
        return "json_escaped"
    if content.strip() and marker in rendered:
        return "altered"
    return "absent"


def analyse(
    rendered: str, fx: dict[str, Any], name: str, variant: str, messages: list, tools: list | None
) -> dict[str, Any]:
    conv = fx["conversations"][name]
    offered = conv["offered"]
    desc = fx["markers"]["tool_description"]
    row: dict[str, Any] = {}

    row["tool_descriptions_rendered"] = {t: desc[t] in rendered for t in offered}
    row["tool_definitions_all_rendered"] = all(row["tool_descriptions_rendered"].values())
    if tools:
        forms = []
        for tool in tools:
            for obj in (tool, tool["function"]):
                for kwargs in (
                    {},
                    {"ensure_ascii": False},
                    {"separators": (",", ":")},
                    {"indent": 4},
                    {"indent": 2},
                ):
                    forms.append(json.dumps(obj, **kwargs))
        row["tool_schema_json_verbatim"] = any(f in rendered for f in forms)
    if name == "multi_tools":
        row["schema_detail_rendered"] = {
            t: m in rendered for t, m in fx["markers"]["schema_detail"].items()
        }
        row["non_ascii_in_description"] = (
            "verbatim"
            if "Café, 東京" in rendered
            else "escaped"
            if "Caf\\u00e9" in rendered
            else "absent"
        )
        row["quotes_in_description"] = (
            "escaped"
            if '\\"matches\\"' in rendered
            else "verbatim"
            if '"matches"' in rendered
            else "absent"
        )

    positions = {m: rendered.find(m) for m in conv["order"]}
    expected = [m for m in conv["order"] if not (variant == "no_system" and m == "MARK-SYS")]
    row["markers_missing"] = [m for m in expected if positions[m] < 0]
    found = [positions[m] for m in expected if positions[m] >= 0]
    row["order_preserved"] = found == sorted(found)

    calls = {}
    for marker, tool_name in conv["calls"].items():
        at = rendered.find(marker)
        info: dict[str, Any] = {"rendered": at >= 0}
        if at >= 0:
            window = rendered[max(0, at - 260) : at + len(marker) + 40]
            info["name_rendered"] = tool_name in window
            if re.search(r'\\+"(order_id|query|recipient|body)\\+"', window):
                info["arguments"] = "json_string_escaped"
            elif re.search(r'"(order_id|query|recipient|body)"\s*:', window):
                info["arguments"] = "json_object"
            else:
                info["arguments"] = "other"
        calls[marker] = info
    row["completed_calls"] = calls
    row["completed_calls_all_rendered"] = all(
        c["rendered"] and c.get("name_rendered") for c in calls.values()
    )
    row["call_id_rendered"] = "call_census_000" in rendered

    results = {}
    tool_messages = [m for m in messages if m["role"] == "tool"]
    for marker, message in zip(conv["results"], tool_messages, strict=True):
        content = message["content"]
        text = content[0]["text"] if isinstance(content, list) else content
        encoding = content_encoding(rendered, content, marker)
        info = {"encoding": encoding}
        start = (
            rendered.find(text)
            if encoding in ("verbatim", "parts_flattened_verbatim")
            else rendered.find(marker)
        )
        if start >= 0:
            before = rendered[max(0, start - 400) : start]
            header, role = carrier(before)
            info["carrier_header"] = header
            info["carrier_role"] = role
            info["wrapped_in_tool_response_tag"] = bool(re.search(r"<tool_response>\s*$", before))
            info["before"] = before[-160:]
            end = (
                start + len(text)
                if encoding in ("verbatim", "parts_flattened_verbatim")
                else start + len(marker)
            )
            info["after"] = rendered[end : end + 80]
        results[marker] = info
    row["tool_results"] = results
    row["tool_results_all_rendered"] = all(r["encoding"] != "absent" for r in results.values())

    if name == "multi_turn":
        a, b = rendered.find("MARK-RESULT-2"), rendered.find("MARK-RESULT-3")
        if 0 <= a < b:
            between = rendered[a + len("MARK-RESULT-2") : b]
            row["between_parallel_results"] = between[:240]
            row["parallel_results_separate_turns"] = carrier(between)[0] is not None
    if variant == "no_system":
        at = rendered.find("MARK-USER-1")
        prefix = rendered[: max(at, 0)]
        row["prefix_before_first_user_text"] = prefix[:600]
        row["prefix_chars"] = len(prefix)
        row["prefix_contains_date"] = bool(DATE.search(prefix))
    row["prompt_tail"] = rendered[-100:]
    row["chars"] = len(rendered)
    row["rendered_sha256"] = sha(rendered)
    return row


def template_features(source: str) -> dict[str, Any]:
    return {
        "template_sha256": sha(source),
        "template_chars": len(source),
        "mentions_tools": "tools" in source,
        "mentions_tool_calls": "tool_calls" in source or "ToolCalls" in source,
        "mentions_tool_role": bool(re.search(r"""['"]tool['"]""", source)),
        "inserts_date": "strftime_now" in source or "currentDate" in source,
        "can_raise": "raise_exception" in source,
    }


def software() -> dict[str, str]:
    import huggingface_hub
    import jinja2
    import tokenizers
    import transformers

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "transformers": transformers.__version__,
        "tokenizers": tokenizers.__version__,
        "jinja2": jinja2.__version__,
        "huggingface_hub": huggingface_hub.__version__,
        "pyyaml": yaml.__version__,
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def save_render(config_id: str, name: str, variant: str, rendered: str, stack: str) -> str:
    path = OUT / "renders" / stack / config_id / f"{name}.{variant}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    return str(path.relative_to(OUT))


# --- transformers ---------------------------------------------------------------------


def load_template(config: dict[str, Any]) -> tuple[Any, str | None, str, str | None]:
    """Tokenizer (or None), template source, renderer label, and a note."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import EntryNotFoundError
    from transformers import AutoTokenizer

    repo, revision = config["hf_repo"], config["revision"]
    try:
        tok = AutoTokenizer.from_pretrained(
            repo, revision=revision, token=False, trust_remote_code=False
        )
        return tok, tok.chat_template, "transformers", None
    except Exception as exc:  # noqa: BLE001 - recorded, then fall back to the template file
        note = f"tokenizer not loaded without remote code: {type(exc).__name__}: {str(exc)[:160]}"
    for filename in ("chat_template.jinja", "tokenizer_config.json"):
        try:
            path = hf_hub_download(repo, filename, revision=revision, token=False)
        except EntryNotFoundError:
            continue
        text = Path(path).read_text()
        if filename.endswith(".json"):
            text = json.loads(text).get("chat_template")
        if isinstance(text, str):
            return None, text, "transformers_jinja", note
    return None, None, "none", note + "; no chat template file in the repository"


def render_hf(
    tok: Any, source: str, messages: list, tools: list | None, kwargs: dict[str, Any]
) -> str:
    if tok is not None:
        return tok.apply_chat_template(
            messages, tools=tools, add_generation_prompt=True, tokenize=False, **kwargs
        )
    from transformers.utils.chat_template_utils import _compile_jinja_template

    template = _compile_jinja_template(source)
    return template.render(messages=messages, tools=tools, add_generation_prompt=True, **kwargs)


def control_tokens(tok: Any, text: str) -> dict[str, list[str]]:
    """Tokens in ``text`` that the tokenizer maps to its added vocabulary."""
    ids = tok(text, add_special_tokens=False)["input_ids"]
    added = tok.added_tokens_decoder
    special = set(tok.all_special_ids) | {i for i, t in added.items() if t.special}
    return {
        "as_special_tokens": sorted({tok.convert_ids_to_tokens(i) for i in ids if i in special}),
        "as_added_tokens": sorted(
            {tok.convert_ids_to_tokens(i) for i in ids if i in added and i not in special}
        ),
    }


def stage_transformers(only: str | None) -> None:
    fx, sample = load_fixtures(), json.loads(SAMPLE.read_text())
    rows, token_ids = [], {}
    for config in sample["configs"]:
        if only and config["id"] != only:
            continue
        tok, source, renderer, note = load_template(config)
        base = {
            "stack": "transformers",
            "observation": {
                "transformers": "rendered by tokenizer.apply_chat_template (actual implementation, tokenizer level)",
                "transformers_jinja": "template file rendered by the transformers Jinja environment, tokenizer not loaded",
                "none": "not observed",
            }[renderer],
            "renderer": renderer,
            "config": config["id"],
            "hf_repo": config["hf_repo"],
            "revision": config["revision"],
            "mirror_of_gated_repo": config["mirror_of_gated_repo"],
            "group": config["group"],
            "template_kwargs": config["template_kwargs"],
            "note": note,
        }
        if source is None:
            rows.append({**base, "fixture": None, "variant": None, "error": "no chat template"})
            print(f"{config['id']:22s} no chat template")
            continue
        base.update(template_features(source))
        ids_for_config = {}
        ok = 0
        for name, variant in cases(fx):
            messages, tools, _ = build(fx, name, variant)
            row = {**base, "fixture": name, "variant": variant}
            try:
                rendered = render_hf(tok, source, messages, tools, config["template_kwargs"])
            except Exception as exc:  # noqa: BLE001 - a template that refuses the input is a finding
                row["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                rows.append(row)
                continue
            ok += 1
            row["error"] = None
            row["render_file"] = save_render(config["id"], name, variant, rendered, "transformers")
            row.update(analyse(rendered, fx, name, variant, messages, tools))
            if tok is not None:
                ids = tok(rendered, add_special_tokens=False)["input_ids"]
                ids_for_config[f"{name}.{variant}"] = ids
                row["token_count"] = len(ids)
                row["token_ids_sha256"] = sha(json.dumps(ids))
                if name == "hostile_output" and variant != "parts":
                    content = next(m["content"] for m in messages if m["role"] == "tool")
                    row["control_strings_in_tool_output"] = control_tokens(tok, content)
            rows.append(row)
        token_ids[config["id"]] = ids_for_config
        print(
            f"{config['id']:22s} {renderer:18s} rendered {ok}/{len(cases(fx))}  template {base['template_sha256'][:10]}"
        )
    if only:
        print(json.dumps(rows, indent=1, ensure_ascii=False)[:6000])
        return
    write_rows(OUT / "transformers.jsonl", rows)
    with gzip.open(OUT / "token_ids.json.gz", "wt") as handle:
        json.dump(token_ids, handle)
    manifest = {
        "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "software": software(),
        "fixtures_sha256": sha(FIXTURES.read_bytes()),
        "sample_sha256": sha(SAMPLE.read_bytes()),
        "note": "No model weights were downloaded and no text was generated.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


# --- vLLM replay ----------------------------------------------------------------------


def stage_vllm_replay() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from prompt_injection_eval import injecagent
    from transformers import AutoTokenizer

    sample = {c["id"]: c for c in json.loads(SAMPLE.read_text())["configs"]}
    cases_by_id = {c.case_id: c for c in injecagent.load_cases(ROOT / injecagent.DATA_DIR)}
    tools = injecagent.load_tools(ROOT / injecagent.DATA_DIR)
    rows = []
    for folder in sorted(STUDY_B.iterdir()):
        label = folder.name
        if (
            label.endswith("-smoke")
            or label not in sample
            or not (folder / "raw_results.jsonl.gz").exists()
        ):
            continue
        stored = []
        with gzip.open(folder / "raw_results.jsonl.gz", "rt") as handle:
            for line in handle:
                r = json.loads(line)
                if r.get("rendered_prompt"):
                    stored.append(r)
        summary: dict[str, Any] = {
            "stack": "vllm_replay",
            "observation": "prompt returned by the vLLM server during Study B, compared with a transformers rendering",
            "config": label,
            "hf_repo": sample[label]["hf_repo"],
            "revision_used_for_comparison": sample[label]["revision"],
            "stored_prompts": len(stored),
        }
        if not stored:
            summary["result"] = "no prompt was stored for this model (the server returned none)"
            rows.append(summary)
            print(f"{label:16s} no stored prompt")
            continue
        runtime = stored[0]["runtime_info"]
        summary["server"] = {k: runtime.get(k) for k in ("runtime_version", "launch_args")}
        summary["run_date"] = stored[0]["timestamp"][:10]
        tok = AutoTokenizer.from_pretrained(
            sample[label]["hf_repo"], revision=sample[label]["revision"], token=False
        )
        match_converted = match_wire = 0
        by_condition: dict[str, list[int]] = {}
        example = None
        for r in stored:
            messages, offered = injecagent.build_conversation(
                cases_by_id[r["case_id"]], r["condition"], tools
            )
            kwargs = {} if r.get("think") is None else {"enable_thinking": bool(r["think"])}
            converted = copy.deepcopy(messages)
            for m in converted:
                for call in m.get("tool_calls", []):
                    call["function"]["arguments"] = json.loads(call["function"]["arguments"])
            outcome = []
            for form in (converted, messages):
                try:
                    text = tok.apply_chat_template(
                        form, tools=offered, add_generation_prompt=True, tokenize=False, **kwargs
                    )
                except Exception as exc:  # noqa: BLE001
                    text = f"<render error: {type(exc).__name__}>"
                outcome.append(text == r["rendered_prompt"])
                if form is converted and text != r["rendered_prompt"] and example is None:
                    a, b = text, r["rendered_prompt"]
                    i = next(
                        (k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b))
                    )
                    example = {
                        "condition": r["condition"],
                        "first_difference_at": i,
                        "transformers": a[max(0, i - 80) : i + 160],
                        "vllm": b[max(0, i - 80) : i + 160],
                        "chars_transformers": len(a),
                        "chars_vllm": len(b),
                    }
            match_converted += outcome[0]
            match_wire += outcome[1]
            by_condition.setdefault(r["condition"], [0, 0])
            by_condition[r["condition"]][0] += outcome[0]
            by_condition[r["condition"]][1] += 1
        summary["identical_with_arguments_parsed"] = match_converted
        summary["identical_with_arguments_as_sent"] = match_wire
        summary["identical_by_condition"] = {
            k: f"{v[0]}/{v[1]}" for k, v in sorted(by_condition.items())
        }
        summary["first_mismatch"] = example
        rows.append(summary)
        print(
            f"{label:16s} stored {len(stored):3d}  identical {match_converted} (arguments parsed) / {match_wire} (as sent)"
        )
    write_rows(OUT / "vllm_replay.jsonl", rows)


# --- Ollama ---------------------------------------------------------------------------


def registry(path: str) -> bytes:
    request = urllib.request.Request(
        "https://registry.ollama.ai/v2/library/" + path,
        headers={
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            "User-Agent": "rendering-census",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
        return response.read()


def stage_ollama(renderer_binary: str) -> None:
    fx, sample = load_fixtures(), json.loads(SAMPLE.read_text())
    jobs, meta = [], {}
    for tag in sample["ollama_template_tags"]:
        name, _, version = tag.partition(":")
        manifest = json.loads(registry(f"{name}/manifests/{version}"))
        layers = {layer["mediaType"].rsplit(".", 1)[-1]: layer for layer in manifest["layers"]}
        config = json.loads(registry(f"{name}/blobs/{manifest['config']['digest']}"))
        template = (
            registry(f"{name}/blobs/{layers['template']['digest']}").decode()
            if "template" in layers
            else ""
        )
        params = (
            json.loads(registry(f"{name}/blobs/{layers['params']['digest']}"))
            if "params" in layers
            else {}
        )
        system = (
            registry(f"{name}/blobs/{layers['system']['digest']}").decode()
            if "system" in layers
            else None
        )
        meta[tag] = {
            "stack": "ollama_template",
            "observation": "rendered by Ollama's template and renderer packages (v0.34.4 source), not by a running server",
            "config": tag,
            "manifest_sha256": sha(json.dumps(manifest, sort_keys=True)),
            "model_layer_digest": layers.get("model", {}).get("digest"),
            "template_layer_digest": layers.get("template", {}).get("digest"),
            "renderer_in_config": config.get("renderer"),
            "parser_in_config": config.get("parser"),
            "params": params,
            "default_system_layer": system,
            "requires": config.get("requires"),
            **template_features(template),
        }
        for fixture, variant in cases(fx):
            if variant in ("parts", "args_string"):
                continue  # the Ollama chat API takes string content and object arguments only
            messages, tools, _ = build(fx, fixture, variant, flavour="ollama")
            if system and variant != "no_system":
                pass  # an explicit system message replaces the layer default
            jobs.append(
                {
                    "id": f"{tag}|{fixture}|{variant}",
                    "template": template,
                    "renderer": config.get("renderer") or "",
                    "messages": messages,
                    "tools": tools or [],
                }
            )
    done = subprocess.run(  # noqa: S603 - the binary is built from scripts/ollama_render
        [renderer_binary],
        input=json.dumps({"jobs": jobs}),
        capture_output=True,
        text=True,
        check=True,
    )
    rows = []
    for result in json.loads(done.stdout):
        tag, fixture, variant = result["id"].split("|")
        row = {
            **meta[tag],
            "fixture": fixture,
            "variant": variant,
            "error": result["error"] or None,
        }
        if not result["error"]:
            messages, tools, _ = build(fx, fixture, variant)
            row["render_file"] = save_render(
                tag.replace(":", "-"), fixture, variant, result["prompt"], "ollama_template"
            )
            row.update(analyse(result["prompt"], fx, fixture, variant, messages, tools))
        rows.append(row)
    write_rows(OUT / "ollama_template.jsonl", rows)
    for tag in meta:
        good = sum(1 for r in rows if r["config"] == tag and not r["error"])
        print(
            f"{tag:22s} rendered {good}  renderer={meta[tag]['renderer_in_config']}  template {meta[tag]['template_sha256'][:10]}"
        )


# --- summary --------------------------------------------------------------------------


def read_rows(name: str) -> list[dict[str, Any]]:
    path = OUT / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def stage_summary() -> None:
    rows = read_rows("transformers.jsonl") + read_rows("ollama_template.jsonl")
    by_config: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rows:
        by_config.setdefault((r["stack"], r["config"]), {})[f"{r['fixture']}.{r['variant']}"] = r
    lineage: dict[str, list[str]] = {}
    for (stack, config), cells in by_config.items():
        first = next(iter(cells.values()))
        if first.get("template_sha256"):
            lineage.setdefault(first["template_sha256"], []).append(f"{stack}:{config}")
    out = []
    for (stack, config), cells in sorted(by_config.items()):
        first = next(iter(cells.values()))

        def get(cell: str, *keys: str, cells: dict[str, dict[str, Any]] = cells) -> Any:
            value: Any = cells.get(cell)
            for key in keys:
                if value is None:
                    return None
                value = value.get(key)
            return value

        def state(cell: str, key: str, cells: dict[str, dict[str, Any]] = cells) -> Any:
            c = cells.get(cell)
            if c is None:
                return "not run"
            if c.get("error"):
                return "template error"
            return c.get(key)

        template_sha = first.get("template_sha256")
        out.append(
            {
                "stack": stack,
                "config": config,
                "observation": first["observation"],
                "revision": first.get("revision") or first.get("template_layer_digest"),
                "template_sha256": (template_sha or "")[:12],
                "shares_template_with": "; ".join(
                    x for x in lineage.get(template_sha or "", []) if x != f"{stack}:{config}"
                ),
                "tool_definitions": state("single_call.default", "tool_definitions_all_rendered"),
                "four_definitions": state("multi_tools.default", "tool_definitions_all_rendered"),
                "schema_as_json": state("multi_tools.default", "tool_schema_json_verbatim"),
                "completed_call": state("single_call.default", "completed_calls_all_rendered"),
                "call_arguments": get(
                    "single_call.default", "completed_calls", "MARKARG1", "arguments"
                ),
                "call_arguments_if_sent_as_string": get(
                    "single_call.args_string", "completed_calls", "MARKARG1", "arguments"
                )
                or state("single_call.args_string", "completed_calls_all_rendered"),
                "call_id": state("single_call.default", "call_id_rendered"),
                "result_carrier_role": get(
                    "single_call.default", "tool_results", "MARK-RESULT-1", "carrier_role"
                ),
                "result_carrier_header": get(
                    "single_call.default", "tool_results", "MARK-RESULT-1", "carrier_header"
                ),
                "result_in_tool_response_tag": get(
                    "single_call.default",
                    "tool_results",
                    "MARK-RESULT-1",
                    "wrapped_in_tool_response_tag",
                ),
                "raw_output": get("hostile_output.raw", "tool_results", "MARK-RESULT-H", "encoding")
                or state("hostile_output.raw", "x"),
                "json_output": get(
                    "hostile_output.json", "tool_results", "MARK-RESULT-H", "encoding"
                )
                or state("hostile_output.json", "x"),
                "yaml_output": get(
                    "hostile_output.yaml", "tool_results", "MARK-RESULT-H", "encoding"
                )
                or state("hostile_output.yaml", "x"),
                "content_parts": get(
                    "hostile_output.parts", "tool_results", "MARK-RESULT-H", "encoding"
                )
                or state("hostile_output.parts", "x"),
                "forged_special_tokens": "; ".join(
                    get("hostile_output.raw", "control_strings_in_tool_output", "as_special_tokens")
                    or []
                ),
                "forged_added_tokens": "; ".join(
                    get("hostile_output.raw", "control_strings_in_tool_output", "as_added_tokens")
                    or []
                ),
                "multi_turn_all_calls": state("multi_turn.default", "completed_calls_all_rendered"),
                "multi_turn_all_results": state("multi_turn.default", "tool_results_all_rendered"),
                "multi_turn_order": state("multi_turn.default", "order_preserved"),
                "parallel_results_separate_turns": state(
                    "multi_turn.default", "parallel_results_separate_turns"
                ),
                "history_without_tools_argument": state(
                    "single_call.no_tools", "completed_calls_all_rendered"
                ),
                "added_text_without_system_chars": get("single_call.no_system", "prefix_chars"),
                "inserts_date": first.get("inserts_date"),
                "errors": "; ".join(
                    f"{k}: {v['error'][:80]}" for k, v in cells.items() if v.get("error")
                ),
            }
        )
    with (OUT / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    families = [members for members in lineage.values() if len(members) > 1]
    (OUT / "lineages.json").write_text(
        json.dumps({"shared_templates": families, "distinct_templates": len(lineage)}, indent=2)
        + "\n"
    )
    print(
        f"{len(out)} configurations, {len(lineage)} distinct templates, {len(families)} templates shared by more than one"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("stage", choices=["transformers", "vllm-replay", "ollama", "summary"])
    parser.add_argument(
        "--only", help="transformers stage: one configuration id; prints rows instead of writing"
    )
    parser.add_argument(
        "--renderer", help="ollama stage: path to the built scripts/ollama_render binary"
    )
    args = parser.parse_args()
    if args.stage == "transformers":
        stage_transformers(args.only)
    elif args.stage == "vllm-replay":
        stage_vllm_replay()
    elif args.stage == "ollama":
        if not args.renderer:
            parser.error("--renderer is required for the ollama stage")
        stage_ollama(args.renderer)
    else:
        stage_summary()


if __name__ == "__main__":
    main()
