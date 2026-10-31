import os
import sys

import anthropic

MODEL = "claude-haiku-5-5"

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(f"ANTHROPIC_API_KEY is not set. Put it in .env and run: uv run --env-file .env {sys.argv[0]}")

    client = anthropic.Anthropic()

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

        with client.messages.stream(
            model=MODEL,
            max_tokens=64000,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": line}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
        print()
