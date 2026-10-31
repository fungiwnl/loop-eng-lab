import os
import sys
from pathlib import Path

import anthropic

MODEL = "claude-haiku-5-5"
SYSTEM = (
    "You are a helpful assistant in a terminal chat about the loop-eng-lab project. "
    "Use the tools to look at its files when a question needs them. "
    "Keep answers short unless asked for detail."
)

# USD per million tokens, Haiku 5.5 with prompts up to 100K tokens.
INPUT_PRICE = 0.10
OUTPUT_PRICE = 0.50
CACHE_WRITE_PRICE = INPUT_PRICE * 1.25
CACHE_READ_PRICE = INPUT_PRICE * 0.1

ROOT = Path(__file__).resolve().parent.parent

TOOLS = [
    {
        "name": "list_files",
        "description": "List a directory of the loop-eng-lab project. Directories end in '/'. Hidden files are not listed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory relative to the project root, '.' for the root."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "read_file",
        "description": "Read a text file of the loop-eng-lab project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File relative to the project root, e.g. 'steps/04_history.py'."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


# The model chooses the path, so keep it inside the project and away from .env, .git and .venv.
def resolve(path):
    full = (ROOT / path).resolve()
    if not full.is_relative_to(ROOT):
        raise ValueError(f"{path} is outside the project")
    if any(part.startswith(".") for part in full.relative_to(ROOT).parts):
        raise ValueError(f"{path} is hidden")
    return full


def list_files(path):
    entries = [p.name + "/" if p.is_dir() else p.name for p in sorted(resolve(path).iterdir()) if not p.name.startswith(".")]
    return "\n".join(entries) or "(empty directory)"


def read_file(path):
    return resolve(path).read_text() or "(empty file)"


def run_tool(block):
    tools = {"list_files": list_files, "read_file": read_file}
    try:
        return {"type": "tool_result", "tool_use_id": block.id, "content": tools[block.name](**block.input)}
    except Exception as e:
        # Errors go back to the model as a result, so it can correct itself.
        return {"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True}


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(f"ANTHROPIC_API_KEY is not set. Put it in .env and run: uv run --env-file .env {sys.argv[0]}")

    client = anthropic.Anthropic()
    messages = []
    cost = 0.0

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line == "/quit":
            break

        # A turn can now be several messages (tool calls and results), so remember where it started.
        turn_start = len(messages)
        messages.append({"role": "user", "content": line})

        while True:
            error = None
            try:
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=64000,
                    system=SYSTEM,
                    tools=TOOLS,
                    output_config={"effort": "low"},
                    cache_control={"type": "ephemeral"},
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        print(text, end="", flush=True)
                    reply = stream.get_final_message()
            except KeyboardInterrupt:
                error = "interrupted"
            except anthropic.APIConnectionError:
                error = "network error, check your connection"
            except anthropic.RateLimitError:
                error = "rate limited, wait a moment and try again"
            except anthropic.APIStatusError as e:
                error = f"API error {e.status_code}: {e.message}"
            print()

            if error:
                print(f"[{error}]")
                del messages[turn_start:]
                break

            usage = reply.usage
            cost += (
                usage.input_tokens * INPUT_PRICE
                + usage.cache_creation_input_tokens * CACHE_WRITE_PRICE
                + usage.cache_read_input_tokens * CACHE_READ_PRICE
                + usage.output_tokens * OUTPUT_PRICE
            ) / 1_000_000
            print(
                f"[in {usage.input_tokens:,}  cache write {usage.cache_creation_input_tokens:,}"
                f"  cache read {usage.cache_read_input_tokens:,}  out {usage.output_tokens:,}"
                f"  |  session ~${cost:.6f}]"
            )

            if reply.stop_reason == "refusal":
                category = reply.stop_details.category if reply.stop_details else None
                print(f"[declined: {category}]")
                del messages[turn_start:]
                break
            # A reply cut off mid tool call can't be answered, so drop the whole turn.
            if reply.stop_reason == "max_tokens":
                print("[reply cut off at max_tokens, turn dropped]")
                del messages[turn_start:]
                break

            messages.append({"role": "assistant", "content": reply.content})
            if reply.stop_reason != "tool_use":
                break

            # Every tool result for this reply goes back in one user message.
            results = []
            for block in reply.content:
                if block.type == "tool_use":
                    print(f"[tool] {block.name} {block.input}")
                    results.append(run_tool(block))
            messages.append({"role": "user", "content": results})
