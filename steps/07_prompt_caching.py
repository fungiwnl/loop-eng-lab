import os
import sys

import anthropic

MODEL = "claude-haiku-5-5"
SYSTEM = "You are a helpful assistant in a terminal chat. Keep answers short unless asked for detail."

# USD per million tokens, Haiku 5.5 with prompts up to 100K tokens.
INPUT_PRICE = 0.10
OUTPUT_PRICE = 0.50
CACHE_WRITE_PRICE = INPUT_PRICE * 1.25
CACHE_READ_PRICE = INPUT_PRICE * 0.1

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

        messages.append({"role": "user", "content": line})

        error = None
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=64000,
                system=SYSTEM,
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
            messages.pop()
            continue

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
            messages.pop()
            continue
        if reply.stop_reason == "max_tokens":
            print("[reply cut off at max_tokens]")

        messages.append({"role": "assistant", "content": reply.content})
