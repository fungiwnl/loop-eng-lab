# loop-eng-lab

A small lab for learning how LLM prompt loops work, built up one step at a time in Python with the Anthropic SDK.

Each script in `steps/` is the previous one plus one new mechanism, so the diff between neighbours is the lesson:

```
diff steps/04_history.py steps/05_hardening.py
```

All steps use `claude-haiku-5-5` to keep costs low.

## Setup

Requirements:
- [uv](https://docs.astral.sh/uv/)
- An API key from the Claude Console (Settings → API Keys). A Max plan includes monthly API credits once a Console organization is linked to it.

Put the key in `.env` (git-ignored):

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Run any step with:

```
uv run --env-file .env steps/<step>.py
```

Type at the `>` prompt. `/quit`, Ctrl-D or Ctrl-C exits. Without `--env-file`, a step exits with "ANTHROPIC_API_KEY is not set".

## Steps

### 02 — Skeleton loop (`02_skeleton.py`)

A REPL (Read–Eval–Print Loop) with no model: read a line, echo it, repeat. Blank lines are skipped. `/quit`, Ctrl-D (`EOFError`) and Ctrl-C (`KeyboardInterrupt`) exit without a traceback. Doesn't need the API key.

### 03 — One-shot model call (`03_one_shot.py`)

The echo becomes a streamed call to Claude. `stream.text_stream` yields only the text of the reply, so the (empty) thinking block Haiku may start with isn't printed.

Try: `My name is Brian.` then `What's my name?`. It doesn't know, because each request contains only the line you just typed. The API is stateless.

### 04 — Conversation history (`04_history.py`)

The script keeps a `messages` list and sends all of it every turn. The assistant's whole `reply.content` goes back into the list, not just its text, because thinking blocks must be returned unchanged.

Try the name test again: now it remembers.

Gaps: Ctrl-C during a reply, a bad key or no network all end in a traceback.

### 05 — Hardening (`05_hardening.py`)

- A `system` prompt.
- API errors are caught most specific first (connection, rate limit, any other status) and printed, and the loop keeps going.
- Ctrl-C during a reply cancels that reply only.
- A failed turn removes its user message: a question with no answer in the history would make the next request invalid.
- `stop_reason` is checked: a `refusal` is reported and dropped, and a `max_tokens` cut-off is flagged.

Try: Ctrl-C halfway through a long answer, or change `MODEL` to a made-up name to see a 404 handled.

### 06 — Token usage per turn (`06_token_usage.py`)

After each reply it prints that request's input and output tokens, the session totals and an estimated cost.

Try: a few short turns. Input tokens grow every turn, even when your message is short, because the whole history is sent again. Output tokens include thinking, which isn't displayed.

### 07 — Prompt caching (`07_prompt_caching.py`)

`cache_control={"type": "ephemeral"}` caches the conversation up to the latest message. On the next request, the unchanged prefix is read from the cache at 0.1× the input price; writing to the cache costs 1.25×. Entries expire after 5 minutes without use.

Try: ask for a long answer (e.g. `explain how HTTP caching works in about 600 words`), then two short follow-ups. Prefixes under 512 tokens aren't cached, so the first turn shows `cache write 0`. The second writes the history to the cache, and the third reads it back.

Caching is a prefix match: changing anything earlier in the request (system prompt, effort, an old message) means a cache miss from that point on.

### 08 — Tool-use loop (`08_tool_loop.py`)

The chat becomes an agent. The model gets two tools, `list_files` and `read_file`, and an inner loop runs until it stops asking for them:

1. Send the history and the tool definitions.
2. If `stop_reason` is `tool_use`, run every requested tool and send all the results back in one user message.
3. Repeat until the model answers with text.

The model chooses the paths, so the tools only accept files inside this project and refuse hidden ones (`.env`, `.git`, `.venv`). A tool error goes back to the model as a result marked `is_error`, so it can try something else. One turn can now span several messages, so a failed turn is rolled back to where it started.

Try: `Which step files exist, and what does the skeleton step do?` and watch one question turn into several requests, with the cache read growing on each. Then `Read the .env file.`
