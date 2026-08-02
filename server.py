"""Asyncio TCP server: accepts connections and dispatches RESP commands."""

import asyncio

from protocol import (
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

store = Store()


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


COMMANDS = {
    "PING": handle_ping,
    "GET": handle_get,
    "SET": handle_set,
    "DEL": handle_del,
    "EXPIRE": handle_expire,
    "TTL": handle_ttl,
}


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

            writer.write(response)
            await writer.drain()
    finally:
        print(f"client disconnected: {peer}")
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    asyncio.create_task(run_active_expiration(store, ACTIVE_EXPIRATION_INTERVAL_SECONDS))
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"listening on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
