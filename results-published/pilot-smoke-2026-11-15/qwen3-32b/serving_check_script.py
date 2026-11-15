"""One development-only request: does the server's prompt equal the pinned local rendering?"""
import copy, json, os, sys
import httpx
from transformers import AutoTokenizer
from prompt_injection_eval.pilot import adapter, episode, serialize
from prompt_injection_eval.pilot.scripted import ScriptedProvider

base = os.environ["PIE_OPENAI_BASE_URL"]
out = sys.argv[1]
client = httpx.Client(base_url=base, timeout=120)
info = {"version": client.get("/version").json(), "models": client.get("/v1/models").json()}

# Build the exact wire conversation of a clean banking episode at its injection point.
class Capture(ScriptedProvider):
    def generate(self, request):
        self.wire = copy.deepcopy(request.messages); self.tools = request.tools
        return super().generate(request)
cap = Capture("benign")
episode.run(episode.Spec("banking", "clean", "json", "user_task_0", None, None, 0), cap, episode.Settings(model="x", label="x"))
wire = []
for m in cap.wire:
    m = dict(m)
    if m.get("tool_calls"):
        m["tool_calls"] = [{**c, "function": {**c["function"], "arguments": json.dumps(c["function"]["arguments"])}} for c in m["tool_calls"]]
    wire.append(m)
body = {"model": "Qwen/Qwen3-32B", "messages": wire, "tools": cap.tools, "tool_choice": "auto", "temperature": 0.0,
        "max_tokens": 64, "return_prompt_text": True, "chat_template_kwargs": {"enable_thinking": False}}
r = client.post("/v1/chat/completions", json=body); r.raise_for_status(); data = r.json()
server_prompt = data.get("prompt_text")
tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-32B", revision="9216db5781bf21249d130ec9da846c4624c16137", token=False)
local = tok.apply_chat_template(cap.wire, tools=cap.tools, add_generation_prompt=True, tokenize=False, enable_thinking=False)
result = {
    **info,
    "prompt_returned": isinstance(server_prompt, str),
    "identical_to_local_rendering": server_prompt == local,
    "ends_with_empty_think_block": isinstance(server_prompt, str) and server_prompt.endswith("<think>\n\n</think>\n\n"),
    "hermes_tools_block": isinstance(server_prompt, str) and "<tools>" in server_prompt,
    "tool_result_json_object_verbatim": wire[-1]["content"] in (server_prompt or ""),
    "response_finish_reason": data["choices"][0]["finish_reason"],
    "response_has_tool_calls": bool(data["choices"][0]["message"].get("tool_calls")),
    "usage": data.get("usage"),
}
if server_prompt != local and isinstance(server_prompt, str):
    i = next((k for k in range(min(len(local), len(server_prompt))) if local[k] != server_prompt[k]), None)
    result["first_difference"] = {"at": i, "local": local[max(0, (i or 0) - 80):(i or 0) + 120], "server": server_prompt[max(0, (i or 0) - 80):(i or 0) + 120]}
json.dump({**result, "server_prompt": server_prompt, "request": body}, open(out, "w"), indent=1)
print(json.dumps(result, indent=1))
