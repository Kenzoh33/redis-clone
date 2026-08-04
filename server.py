"""Asyncio TCP server: accepts connections and dispatches RESP commands."""

import asyncio
import sys
import time

from persistence import PersistenceLog, replay
from protocol import (
    encode_array,
    encode_bulk_string,
    encode_error,
    encode_integer,
    encode_simple_string,
    parse_command,
)
from store import Store, run_active_expiration

HOST = "127.0.0.1"
PORT = 6379
ACTIVE_EXPIRATION_INTERVAL_SECONDS = 1.0
DEFAULT_LOG_PATH = "appendonly.log"

store = Store()
persistence_log: PersistenceLog | None = None


def handle_ping(args: list[str]) -> bytes:
    if args:
        return encode_bulk_string(args[0])
    return encode_simple_string("PONG")


def handle_get(args: list[str]) -> bytes:
    if len(args) != 1:
        return encode_error("ERR wrong number of arguments for 'get' command")
    return encode_bulk_string(store.get(args[0]))


def handle_set(args: list[str]) -> bytes:
    if len(args) != 2:
        return encode_error("ERR wrong number of arguments for 'set' command")
    store.set(args[0], args[1])
    return encode_simple_string("OK")


def handle_del(args: list[str]) -> bytes:
    if not args:
        return encode_error("ERR wrong number of arguments for 'del' command")
    return encode_integer(store.delete(*args))


def handle_expire(args: list[str]) -> bytes:
    if len(args) != 2:
        return encode_error("ERR wrong number of arguments for 'expire' command")
    try:
        seconds = int(args[1])
    except ValueError:
        return encode_error("ERR value is not an integer or out of range")
    return encode_integer(1 if store.expire(args[0], seconds) else 0)


def handle_ttl(args: list[str]) -> bytes:
    if len(args) != 1:
        return encode_error("ERR wrong number of arguments for 'ttl' command")
    return encode_integer(store.ttl(args[0]))


def handle_exists(args: list[str]) -> bytes:
    if not args:
        return encode_error("ERR wrong number of arguments for 'exists' command")
    return encode_integer(store.exists(*args))


def handle_incr(args: list[str]) -> bytes:
    if len(args) != 1:
        return encode_error("ERR wrong number of arguments for 'incr' command")
    try:
        return encode_integer(store.incr(args[0]))
    except ValueError:
        return encode_error("ERR value is not an integer or out of range")


def handle_decr(args: list[str]) -> bytes:
    if len(args) != 1:
        return encode_error("ERR wrong number of arguments for 'decr' command")
    try:
        return encode_integer(store.decr(args[0]))
    except ValueError:
        return encode_error("ERR value is not an integer or out of range")


def handle_append(args: list[str]) -> bytes:
    if len(args) != 2:
        return encode_error("ERR wrong number of arguments for 'append' command")
    return encode_integer(store.append(args[0], args[1]))


def handle_mset(args: list[str]) -> bytes:
    if not args or len(args) % 2 != 0:
        return encode_error("ERR wrong number of arguments for 'mset' command")
    store.mset(dict(zip(args[0::2], args[1::2])))
    return encode_simple_string("OK")


def handle_mget(args: list[str]) -> bytes:
    if not args:
        return encode_error("ERR wrong number of arguments for 'mget' command")
    return encode_array([encode_bulk_string(v) for v in store.mget(*args)])


def handle_type(args: list[str]) -> bytes:
    if len(args) != 1:
        return encode_error("ERR wrong number of arguments for 'type' command")
    return encode_simple_string(store.type(args[0]))


COMMANDS = {
    "PING": handle_ping,
    "GET": handle_get,
    "SET": handle_set,
    "DEL": handle_del,
    "EXPIRE": handle_expire,
    "TTL": handle_ttl,
    "EXISTS": handle_exists,
    "INCR": handle_incr,
    "DECR": handle_decr,
    "APPEND": handle_append,
    "MSET": handle_mset,
    "MGET": handle_mget,
    "TYPE": handle_type,
}

MUTATING_COMMANDS = {"SET", "DEL", "EXPIRE", "INCR", "DECR", "APPEND", "MSET"}


def apply_logged_command(args: list[str]) -> None:
    name, cmd_args = args[0], args[1:]
    if name == "EXPIRE":
        key, deadline_str = cmd_args
        store.expire(key, float(deadline_str) - time.time())
    else:
        COMMANDS[name](cmd_args)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    print(f"client connected: {peer}")

    try:
        while True:
            try:
                command = await parse_command(reader)
            except (ValueError, asyncio.IncompleteReadError) as exc:
                writer.write(encode_error(f"ERR protocol error: {exc}"))
                await writer.drain()
                break

            if command is None:
                break
            if not command:
                continue

            name = command[0].upper()
            handler = COMMANDS.get(name)
            if handler is None:
                response = encode_error(f"ERR unknown command '{command[0]}'")
            else:
                response = handler(command[1:])

                if name in MUTATING_COMMANDS and not response.startswith(b"-"):
                    if name == "EXPIRE":
                        deadline = time.time() + int(command[2])
                        persistence_log.append(["EXPIRE", command[1], str(deadline)])
                    else:
                        persistence_log.append([name, *command[1:]])

            writer.write(response)
            await writer.drain()
    finally:
        print(f"client disconnected: {peer}")
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    global persistence_log

    log_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG_PATH
    replay(log_path, apply=apply_logged_command)
    persistence_log = PersistenceLog(log_path)

    asyncio.create_task(run_active_expiration(store, ACTIVE_EXPIRATION_INTERVAL_SECONDS))
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"listening on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
