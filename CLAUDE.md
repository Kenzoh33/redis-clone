# Redis Clone — Project Instructions

## What this is
An in-memory key-value server, built from raw TCP sockets, implementing the real RESP protocol closely enough that genuine Redis client libraries can talk to it without modification. This is a learning project: the goal is not just working code, but a working understanding of networking, concurrency, durability, and replication as they're actually implemented in production systems.

## Target architecture (v1.0 definition of done)
The finished project consists of:

- **Protocol layer** (`protocol.py`) — RESP encoding/decoding: simple strings, errors, integers, bulk strings, arrays, nil.
- **Server layer** (`server.py`) — asyncio TCP server, connection handling, command dispatch table.
- **Storage layer** (`store.py`) — in-memory hash map; GET, SET, DEL, EXISTS, INCR, DECR, APPEND, MSET, MGET, TYPE; TTL/EXPIRE with both passive and active expiration.
- **Persistence layer** (`persistence.py`) — append-only write log; full crash recovery by replay on startup.
- **Replication layer** (`replication.py`) — one primary, one replica; full resync on connect, live streaming of subsequent writes, replica enforced as read-only.
- **Verification** — a `pytest` suite proving correctness against a real `redis-py` client, a concurrency stress test proving no lost updates under simultaneous access, and `redis-benchmark` throughput/latency numbers for the finished server.

Every session's work should be traceable to one of these five layers or to verification. If a proposed task doesn't fit anywhere in this list, that's a signal to stop and ask rather than build it.

## Explicit non-goals
Do not implement, suggest, or scaffold toward any of the following unless directly instructed — they're common ways this kind of project quietly turns into a 3-month effort instead of a 2-week one:
- Clustering, sharding, or multi-node consensus (Raft, gossip protocols)
- Lua scripting (`EVAL`), pub/sub, transactions (`MULTI`/`EXEC`)
- ACLs, authentication, or TLS
- A custom binary storage format — the append-only log can stay human-readable
- Performance micro-optimization before the benchmark step (Day-13-equivalent) — correctness first, speed measurement later

## Stack
- Python 3.11+, `asyncio` — no web frameworks, sockets are the point
- `pytest` for tests; `redis-py` as a test client only, never a runtime dependency of the server
- `redis-benchmark` (official CLI) for load testing

## How we work together
1. At the start of a session, confirm the specific task before writing any code. If it isn't stated, ask what we're building today.
2. Implement only what was explicitly requested — no unrequested refactors, no "while I'm in here" additions, no scope from a later architecture layer.
3. If a task seems to need more scope than requested, stop, explain why in one or two sentences, and ask before proceeding.
4. Stay in Plan mode until the plan matches only the requested task.
5. At the end of a session: summarize what changed, list what was tested and how, append an entry to `PROGRESS.md` (see below), and propose a commit message.

## Teaching approach
This project exists so I understand systems concepts, not just to produce a finished artifact.
- Before implementing something that involves a new concept (sockets, an event loop, a race condition, write-ahead logging, replication), explain in plain language what it is and why this project needs it — a few sentences, not a lecture — before writing the code.
- When a design decision has real tradeoffs (e.g., passive vs. active expiry, full sync vs. incremental), name the tradeoff explicitly rather than silently picking one.
- If I ask "why" about something you built, treat that as a normal and expected part of the workflow, not a detour.

## Testing
- Every new command or behavior requires a passing `pytest` test before it's considered done.
- Any code touching shared state across coroutines requires a concurrency stress test (many simultaneous operations), not just a single-client test.
- Tests exercise the server via the real `redis-py` client library, not raw socket calls, to prove real protocol compatibility.

## Conventions
- Type hints on all function signatures.
- One module per concern, per the architecture list above — resist merging modules for convenience.
- Prefer straightforward, readable code over clever abstractions. If a simpler version exists that a systems-programming beginner could follow, prefer it.

## Progress tracking
Maintain `PROGRESS.md` at the project root as a running log. After each session, append a dated entry: what was built, what concept it taught, and what's next. Keep entries to 3-5 lines each — this is a log, not documentation. `PROGRESS.md` is not loaded automatically each session; read it at the start of a session if picking up prior context matters for the current task.

## Commits
One commit per completed unit of work, message stating what was built. Do not squash unrelated work into one commit.
