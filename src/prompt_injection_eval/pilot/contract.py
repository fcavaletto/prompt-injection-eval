"""Template profiles for the measurement contract (docs/measurement-contract.md).

A profile records, for one pinned chat template, how a chat-completion conversation is laid
out in the prompt: the turn delimiters, which turn role each message role is rendered in,
how tool results are wrapped and whether consecutive tool messages share one turn, and the
generation header. The values are read from the templates at the pilot's pinned revisions;
the checker does not choose them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    template: str
    turn_start: str  # contains "{role}"
    turn_end: str
    generation_header: str
    tool_role: str  # the turn role tool messages are rendered in
    group_tool_messages: bool  # consecutive tool messages share one turn
    tool_turn_prefix: str  # text at the start of a tool turn's body, before the first block
    tool_block_open: str
    tool_block_close: str
    tool_block_separator: str
    call_open: str
    call_close: str


PROFILES = {
    "qwen3": Profile(
        name="qwen3",
        template="Qwen/Qwen3-32B@9216db5781bf21249d130ec9da846c4624c16137 (enable_thinking=False)",
        turn_start="<|im_start|>{role}\n",
        turn_end="<|im_end|>\n",
        generation_header="<|im_start|>assistant\n<think>\n\n</think>\n\n",
        tool_role="user",
        group_tool_messages=True,
        tool_turn_prefix="",
        tool_block_open="<tool_response>\n",
        tool_block_close="\n</tool_response>",
        tool_block_separator="\n",
        call_open="<tool_call>\n",
        call_close="\n</tool_call>",
    ),
    "granite4": Profile(
        name="granite4",
        template="ibm-granite/granite-4.0-h-small@b8c0982bab7fde4eb48110f5a069527c008fab39",
        turn_start="<|start_of_role|>{role}<|end_of_role|>",
        turn_end="<|end_of_text|>\n",
        generation_header="<|start_of_role|>assistant<|end_of_role|>",
        tool_role="user",
        group_tool_messages=True,
        tool_turn_prefix="\n",
        tool_block_open="<tool_response>\n",
        tool_block_close="\n</tool_response>",
        tool_block_separator="\n",
        call_open="<tool_call>\n",
        call_close="\n</tool_call>",
    ),
    "scripted": Profile(
        name="scripted",
        template="prompt_injection_eval.pilot.scripted.reference_render",
        turn_start="<|im_start|>{role}\n",
        turn_end="<|im_end|>\n",
        generation_header="<|im_start|>assistant\n",
        tool_role="user",
        group_tool_messages=False,
        tool_turn_prefix="",
        tool_block_open="<tool_response>\n",
        tool_block_close="\n</tool_response>",
        tool_block_separator="",
        call_open="<tool_call>\n",
        call_close="\n</tool_call>",
    ),
}
