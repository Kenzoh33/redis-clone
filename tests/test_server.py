import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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


def test_set_get_roundtrip(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    assert client.set("foo", "bar") is True
    assert client.get("foo") == b"bar"


def test_get_missing_key_returns_none(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    assert client.get("nosuchkey") is None


def test_del_returns_count_and_removes_key(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    client.set("foo", "bar")
    assert client.delete("foo") == 1
    assert client.get("foo") is None
    assert client.delete("foo") == 0


@pytest.mark.parametrize("command,args", [("get", ()), ("set", ("onlyonearg",))])
def test_wrong_arity_returns_error(redis_server, command, args):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    with pytest.raises(redis.ResponseError):
        client.execute_command(command.upper(), *args)


def test_concurrent_set_get_no_cross_talk(redis_server):
    # Many simultaneous connections each writing/reading a distinct key,
    # proving the shared dict in store.py isn't corrupted under concurrency.
    def set_and_get(i: int) -> tuple[int, bytes | None]:
        client = redis.Redis(host=HOST, port=PORT, protocol=2)
        key = f"key:{i}"
        value = f"value:{i}"
        client.set(key, value)
        return i, client.get(key)

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(set_and_get, range(200)))

    for i, value in results:
        assert value == f"value:{i}".encode()


def test_expire_existing_key(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    client.set("foo", "bar")
    assert client.expire("foo", 100) is True
    assert 0 < client.ttl("foo") <= 100


def test_expire_missing_key_returns_false(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    assert client.expire("nosuchkey", 10) is False


def test_ttl_no_expiry_returns_minus_one(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    client.set("foo", "bar")
    assert client.ttl("foo") == -1


def test_ttl_missing_key_returns_minus_two(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    assert client.ttl("nosuchkey") == -2


def test_passive_expiration_end_to_end(redis_server):
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    client.set("foo", "bar")
    client.expire("foo", 1)
    time.sleep(1.2)
    assert client.get("foo") is None
    assert client.ttl("foo") == -2


def test_concurrent_delete_no_lost_updates(redis_server):
    # Many connections race to delete the same set of pre-existing keys.
    # The counts they each report deleting must sum to exactly the number
    # of keys that existed - no double-counting a key two clients both saw.
    client = redis.Redis(host=HOST, port=PORT, protocol=2)
    keys = [f"race:{i}" for i in range(100)]
    for key in keys:
        client.set(key, "x")

    def delete_all() -> int:
        worker_client = redis.Redis(host=HOST, port=PORT, protocol=2)
        return worker_client.delete(*keys)

    with ThreadPoolExecutor(max_workers=20) as pool:
        deleted_counts = list(pool.map(lambda _: delete_all(), range(20)))

    assert sum(deleted_counts) == len(keys)
    for key in keys:
        assert client.get(key) is None
