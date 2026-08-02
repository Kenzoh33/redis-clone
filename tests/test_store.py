from store import Store


def test_get_missing_key_returns_none():
    store = Store()
    assert store.get("nosuchkey") is None


def test_set_then_get():
    store = Store()
    store.set("foo", "bar")
    assert store.get("foo") == "bar"


def test_set_overwrites_existing_value():
    store = Store()
    store.set("foo", "bar")
    store.set("foo", "baz")
    assert store.get("foo") == "baz"


def test_delete_existing_key_returns_one_and_removes_it():
    store = Store()
    store.set("foo", "bar")
    assert store.delete("foo") == 1
    assert store.get("foo") is None


def test_delete_missing_key_returns_zero():
    store = Store()
    assert store.delete("nosuchkey") == 0


def test_delete_multiple_keys_returns_count_of_existing_ones():
    store = Store()
    store.set("a", "1")
    store.set("b", "2")
    assert store.delete("a", "b", "c") == 2
    assert store.get("a") is None
    assert store.get("b") is None
