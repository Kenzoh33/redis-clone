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
