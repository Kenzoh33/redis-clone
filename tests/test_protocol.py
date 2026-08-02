from protocol import (
    encode_array,
    encode_bulk_string,
    encode_error,
    encode_integer,
    encode_simple_string,
)


def test_encode_simple_string():
    assert encode_simple_string("PONG") == b"+PONG\r\n"


def test_encode_error():
    assert encode_error("ERR unknown command 'FOO'") == b"-ERR unknown command 'FOO'\r\n"


def test_encode_integer():
    assert encode_integer(42) == b":42\r\n"
    assert encode_integer(-1) == b":-1\r\n"


def test_encode_bulk_string():
    assert encode_bulk_string("foo") == b"$3\r\nfoo\r\n"


def test_encode_bulk_string_nil():
    assert encode_bulk_string(None) == b"$-1\r\n"


def test_encode_array():
    values = [encode_bulk_string("foo"), encode_bulk_string("bar")]
    assert encode_array(values) == b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n"


def test_encode_array_nil():
    assert encode_array(None) == b"*-1\r\n"
