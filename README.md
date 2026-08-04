# redis-clone

A Redis-compatible server built from scratch on raw TCP sockets, speaking real RESP2 so genuine Redis clients (`redis-cli`, `redis-py`) can talk to it unmodified.

## What this is

A learning project built to understand how systems like Redis actually work under the hood: event-driven networking with `asyncio`, the RESP wire protocol, in-memory data structures, write-ahead-log durability, and primary/replica replication. It's not a production database — no clustering, no scripting, no auth — but every layer it does have is implemented for real, not mocked out, and tested against a genuine `redis-py` client rather than a custom harness.

## Features

- **Protocol layer** — full RESP2 encoding/decoding (simple strings, errors, integers, bulk strings, arrays, nil).
- **Server layer** — asyncio TCP server, one coroutine per connection, command dispatch table.
- **Storage layer** — in-memory key-value store with TTL support (passive expiry on access, active background sweep):
  `PING`, `GET`, `SET`, `DEL`, `EXPIRE`, `TTL`, `EXISTS`, `INCR`, `DECR`, `APPEND`, `MSET`, `MGET`, `TYPE`.
- **Persistence layer** — append-only write log (one JSON-encoded command per line); full crash recovery by replaying the log on startup.
- **Replication layer** — one primary, one replica: full resync of existing data on connect, live streaming of subsequent writes, and the replica rejects writes from clients while still serving reads.

## Quick start

```
python3 -m venv .venv
.venv/bin/pip install pytest redis
.venv/bin/python server.py
```

Listens on `127.0.0.1:6379` by default — talk to it with `redis-cli` in another terminal.

## Usage examples

Basic commands:

```
redis-cli SET foo bar
redis-cli GET foo
redis-cli EXPIRE foo 3600
redis-cli TTL foo
redis-cli INCR counter
redis-cli MSET a 1 b 2
redis-cli MGET a b c
```

By default the server writes its append-only log to `appendonly.log` in the current directory; pass a different path as the first argument:

```
.venv/bin/python server.py mydata.aof
```

Running a replica of a primary (in a second terminal, on a different port):

```
.venv/bin/python server.py replica.aof --port 6380 --replicaof 127.0.0.1 6379
```

```
redis-cli -p 6380 GET foo        # existing primary data, via full resync
redis-cli -p 6380 SET nope x     # (error) READONLY You can't write against a read only replica.
```

## Architecture

- `protocol.py` — RESP encoding and decoding. Reused identically for client traffic and for the replication stream, since both speak the same wire format.
- `server.py` — the asyncio TCP server, the command dispatch table, and the glue between storage, persistence, and replication: every successful mutating command is applied to the store, appended to the log, and forwarded to a connected replica from a single code path.
- `store.py` — the in-memory `dict`-backed key-value store, including TTL bookkeeping. No locking: since command handlers don't `await` mid-operation, each one runs to completion atomically relative to every other connection under the single-threaded event loop.
- `persistence.py` — a generic append-only log (`PersistenceLog.append` / `replay`). It has no idea what a Redis command is; it just persists and replays whatever list of strings it's given.
- Replication reuses persistence's replay machinery rather than being a separate protocol: a full resync is the same "replay a sequence of commands" logic, just fed from a live socket instead of a file.

## Benchmark results

`redis-benchmark`, standalone server, default settings (fsync on every write), `-n 20000 -r 100000`:

| Command | req/sec | p50 latency |
|---|---|---|
| GET | 101,010 | 0.487 ms |
| TTL | 90,090 | 0.551 ms |
| TYPE | 87,336 | 0.551 ms |
| MGET | 84,034 | 0.591 ms |
| EXISTS | 80,972 | 0.567 ms |
| DEL | 23,229 | 2.143 ms |
| INCR | 23,256 | 2.135 ms |
| DECR | 23,148 | 2.143 ms |
| APPEND | 22,573 | 2.199 ms |
| SET | 22,523 | 2.199 ms |
| EXPIRE | 22,297 | 2.231 ms |
| MSET (10 keys/request) | 14,859 | 3.343 ms |

Reads cluster around 80k–110k req/sec, sub-millisecond. Every mutating command clusters tightly around 22–23k req/sec regardless of which one it is — the in-memory mutation is cheap; the `os.fsync()` call the persistence layer makes on every write is the actual bottleneck, and it costs about the same fixed amount no matter what's being written. `MSET` batches 10 keys behind a single fsync, so its real per-key throughput (~148k keys/sec) is the highest of any command here.

## Running the tests

```
.venv/bin/python -m pytest
```

Tests run against a real `redis-py` client (not raw sockets), and include concurrency stress tests (many simultaneous connections racing on the same keys) and end-to-end crash-recovery and replication tests that spawn real server subprocesses.

## What's not implemented

Deliberately out of scope, to keep this a focused learning project rather than an open-ended one: clustering/sharding, Lua scripting, pub/sub, transactions (`MULTI`/`EXEC`), ACLs/auth/TLS, a binary storage format, and list/set/hash/sorted-set data types. Replication supports exactly one primary and one replica, full resync only — no partial resync, no chained replication, no runtime `REPLICAOF`.
