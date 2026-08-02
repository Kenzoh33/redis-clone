"""Asyncio TCP server: accepts connections and dispatches RESP commands."""

import asyncio

from protocol import encode_bulk_string, encode_error, encode_simple_string, parse_command

HOST = "127.0.0.1"
PORT = 6379


def handle_ping(args: list[str]) -> bytes:
    if args:
        return encode_bulk_string(args[0])
    return encode_simple_string("PONG")


COMMANDS = {
    "PING": handle_ping,
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
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"listening on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
