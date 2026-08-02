# redis-clone

A Redis server built from scratch on raw TCP sockets with `asyncio`, speaking real RESP so genuine Redis clients (`redis-cli`, `redis-py`) can talk to it unmodified. Learning project — see `CLAUDE.md` for the full scope and `progress.md` for a running log.

Currently implemented: the RESP protocol layer, the TCP server with connection handling, and an in-memory storage layer backing `PING`, `GET`, `SET`, and `DEL`.

## Run the server

```
python3 -m venv .venv
.venv/bin/pip install pytest redis
.venv/bin/python server.py
```

Listens on `127.0.0.1:6379` — talk to it with `redis-cli` in another terminal.

## Run the tests

```
.venv/bin/python -m pytest
```
