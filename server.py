"""Asyncio TCP server: accepts connections and dispatches RESP commands."""

import argparse
import asyncio
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
replica_writer: asyncio.StreamWriter | None = None
IS_REPLICA = False


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


def build_logged_command(name: str, command: list[str]) -> list[str]:
    if name == "EXPIRE":
        deadline = time.time() + int(command[2])
        return ["EXPIRE", command[1], str(deadline)]
    return [name, *command[1:]]


async def run_replica(host: str, port: int) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(encode_array([encode_bulk_string("SYNC")]))
    await writer.drain()
    while True:
        command = await parse_command(reader)
        if command is None:
            break
        apply_logged_command(command)
        persistence_log.append(command)


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

            if name == "SYNC":
                global replica_writer
                replica_writer = writer
                for key, value, ttl in store.snapshot():
                    writer.write(encode_array([encode_bulk_string(x) for x in ["SET", key, value]]))
                    if ttl != -1:
                        deadline = time.time() + ttl
                        writer.write(
                            encode_array([encode_bulk_string(x) for x in ["EXPIRE", key, str(deadline)]])
                        )
                await writer.drain()
                continue

            handler = COMMANDS.get(name)
            if handler is None:
                response = encode_error(f"ERR unknown command '{command[0]}'")
            elif IS_REPLICA and name in MUTATING_COMMANDS:
                response = encode_error("READONLY You can't write against a read only replica.")
            else:
                response = handler(command[1:])

                if name in MUTATING_COMMANDS and not response.startswith(b"-"):
                    logged_command = build_logged_command(name, command)
                    persistence_log.append(logged_command)
                    if replica_writer is not None:
                        replica_writer.write(
                            encode_array([encode_bulk_string(x) for x in logged_command])
                        )
                        await replica_writer.drain()

            writer.write(response)
            await writer.drain()
    finally:
        if writer is replica_writer:
            replica_writer = None
        print(f"client disconnected: {peer}")
        writer.close()
        await writer.wait_closed()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", nargs="?", default=DEFAULT_LOG_PATH)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--replicaof", nargs=2, metavar=("HOST", "PORT"))
    return parser.parse_args()


async def main() -> None:
    global persistence_log, IS_REPLICA

    args = parse_args()
    IS_REPLICA = args.replicaof is not None

    replay(args.log_path, apply=apply_logged_command)
    persistence_log = PersistenceLog(args.log_path)

    # create_task() doesn't hold a strong reference to the task it returns;
    # without keeping one ourselves, these background tasks can be garbage
    # collected mid-flight. background_tasks stays alive for main()'s whole
    # lifetime, which keeps them alive too.
    background_tasks: set[asyncio.Task] = set()
    background_tasks.add(
        asyncio.create_task(run_active_expiration(store, ACTIVE_EXPIRATION_INTERVAL_SECONDS))
    )

    if IS_REPLICA:
        primary_host, primary_port = args.replicaof
        background_tasks.add(asyncio.create_task(run_replica(primary_host, int(primary_port))))

    server = await asyncio.start_server(handle_client, HOST, args.port)
    print(f"listening on {HOST}:{args.port}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
