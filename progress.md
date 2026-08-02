## 2026-08-01

Built `protocol.py` (RESP encode/decode: simple string, error, integer, bulk
string, array, all with nil variants; `parse_command` reads a multibulk
command off an `asyncio.StreamReader`) and `server.py` (asyncio TCP server on
127.0.0.1:6379, per-connection handler loop, one-entry dispatch table for
`PING`). This is the first end-to-end slice: protocol layer + server layer,
no storage yet.

Taught: why asyncio (single-threaded concurrency via an event loop instead of
blocking on slow clients) and the RESP wire format (type-byte-prefixed
values, commands arrive as arrays of bulk strings).

Tested via real `redis-py` client (pinned to `protocol=2` — this server
speaks RESP2 only, `redis-py` now defaults to attempting a RESP3 `HELLO`
handshake which we don't implement): `test_protocol.py` unit-tests each
encoder, `test_server.py` starts the server as a subprocess and confirms
`PING` → `PONG`, `PING hello` → echoed bulk string, and an unknown command
returns a RESP error. 10/10 passing. Also confirmed manually with real
`redis-cli` (installed via `brew install redis`): `PING` → `PONG`,
`PING "hello there"` → echoed, `foobar` → clean RESP error.

Next: pick the first real command(s) for the storage layer — likely
GET/SET/DEL to start.

## 2026-08-01 (2)

Built `store.py` (`Store` class wrapping a plain `dict[str, str]`: `get`,
`set`, `delete(*keys)` returning count removed, matching real `DEL`'s
multi-key semantics) and wired `GET`/`SET`/`DEL` into `server.py`'s
dispatch table as a single shared `store = Store()` instance. Wrong-arity
calls now return a RESP error instead of crashing.

Taught: why plain un-locked dict ops are safe to share across concurrent
connections under asyncio — a coroutine only yields at `await`, and
`Store`'s methods contain none, so each call runs atomically relative to
every other connection. That stops holding the moment a handler needs to
`await` mid-operation (e.g. persistence later).

Tested: `tests/test_store.py` (unit tests, no networking) and new cases in
`tests/test_server.py` via real `redis-py` — SET/GET round-trip, GET on
missing key, DEL count + removal, wrong-arity errors, and two concurrency
stress tests (50 threads doing distinct SET+GET pairs with no cross-talk;
20 threads racing to DEL the same 100 pre-existing keys, with counts
summing to exactly 100 — no lost updates). 23/23 passing. Also manually
verified via real `redis-cli`.

Next: EXISTS, INCR/DECR, APPEND, MSET/MGET, TYPE — remaining storage-layer
commands — or start the persistence layer.
