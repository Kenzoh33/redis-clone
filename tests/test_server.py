import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import redis

HOST = "127.0.0.1"
PORT = 6379
SERVER_SCRIPT = Path(__file__).parent.parent / "server.py"


def _wait_for_port(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"server did not start listening on {host}:{port}")


@pytest.fixture()
def redis_server():
    proc = subprocess.Popen([sys.executable, str(SERVER_SCRIPT)])
    try:
        _wait_for_port(HOST, PORT)
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_ping(redis_server):
    # protocol=2: this server implements RESP2 only (no HELLO/RESP3 handshake).
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    assert client.ping() is True


def test_ping_with_message(redis_server):
    # redis-py's high-level ping()/execute_command() always coerces the PING
    # response to a bool (response == "PONG"), so we go through the client's
    # raw connection to observe the actual echoed bulk-string reply.
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    conn = client.connection_pool.get_connection()
    conn.send_command("PING", "hello")
    assert conn.read_response() == b"hello"


def test_unknown_command_returns_error(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    with pytest.raises(redis.ResponseError):
        client.execute_command("FOOBAR")
