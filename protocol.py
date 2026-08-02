"""RESP (REdis Serialization Protocol) encoding and decoding."""

import asyncio

CRLF = b"\r\n"


def encode_simple_string(value: str) -> bytes:
    return b"+" + value.encode() + CRLF


def encode_error(message: str) -> bytes:
    return b"-" + message.encode() + CRLF


def encode_integer(value: int) -> bytes:
    return b":" + str(value).encode() + CRLF


def encode_bulk_string(value: str | None) -> bytes:
    if value is None:
        return b"$-1" + CRLF
    data = value.encode()
    return b"$" + str(len(data)).encode() + CRLF + data + CRLF


def encode_array(values: list[bytes] | None) -> bytes:
    if values is None:
        return b"*-1" + CRLF
    header = b"*" + str(len(values)).encode() + CRLF
    return header + b"".join(values)


async def parse_command(reader: asyncio.StreamReader) -> list[str] | None:
    """Read one RESP multibulk command (an array of bulk strings) from the client.

    Returns the command as a list of strings, or None if the client
    disconnected cleanly before sending a new command.
    """
    line = await reader.readline()
    if not line:
        return None

    if not line.startswith(b"*"):
        raise ValueError(f"expected array header, got: {line!r}")

    num_args = int(line[1:-2])
    args: list[str] = []
    for _ in range(num_args):
        length_line = await reader.readline()
        if not length_line.startswith(b"$"):
            raise ValueError(f"expected bulk string header, got: {length_line!r}")
        length = int(length_line[1:-2])

        data = await reader.readexactly(length + 2)
        args.append(data[:-2].decode())

    return args
