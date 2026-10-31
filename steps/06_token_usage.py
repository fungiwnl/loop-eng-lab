import os
import sys

import anthropic

MODEL = "claude-haiku-5-5"
SYSTEM = "You are a helpful assistant in a terminal chat. Keep answers short unless asked for detail."

# USD per million tokens, Haiku 5.5 with prompts up to 100K tokens.
INPUT_PRICE = 0.10
OUTPUT_PRICE = 0.50

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(f"ANTHROPIC_API_KEY is not set. Put it in .env and run: uv run --env-file .env {sys.argv[0]}")

    client = anthropic.Anthropic()
    messages = []
    total_in = total_out = 0

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
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        cost = (total_in * INPUT_PRICE + total_out * OUTPUT_PRICE) / 1_000_000
        print(
            f"[in {usage.input_tokens:,}  out {usage.output_tokens:,}"
            f"  |  session in {total_in:,}  out {total_out:,}  ~${cost:.6f}]"
        )

        if reply.stop_reason == "refusal":
            category = reply.stop_details.category if reply.stop_details else None
            print(f"[declined: {category}]")
            messages.pop()
            continue
        if reply.stop_reason == "max_tokens":
            print("[reply cut off at max_tokens]")

        messages.append({"role": "assistant", "content": reply.content})
