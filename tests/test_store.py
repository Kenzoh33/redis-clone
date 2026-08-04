import asyncio

from store import Store, run_active_expiration


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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


def test_expire_missing_key_returns_false():
    store = Store()
    assert store.expire("nosuchkey", 10) is False


def test_expire_existing_key_returns_true_and_sets_ttl():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    assert store.expire("foo", 10) is True
    assert store.ttl("foo") == 10


def test_expire_nonpositive_seconds_deletes_immediately():
    store = Store()
    store.set("foo", "bar")
    assert store.expire("foo", 0) is True
    assert store.get("foo") is None


def test_ttl_of_key_without_expiry_returns_minus_one():
    store = Store()
    store.set("foo", "bar")
    assert store.ttl("foo") == -1


def test_ttl_of_missing_key_returns_minus_two():
    store = Store()
    assert store.ttl("nosuchkey") == -2


def test_ttl_counts_down_as_clock_advances():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 10)
    clock.advance(4)
    assert store.ttl("foo") == 6


def test_set_clears_existing_ttl():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 10)
    store.set("foo", "baz")
    assert store.ttl("foo") == -1


def test_get_returns_none_and_removes_key_after_passive_expiry():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)

    clock.advance(6)
    assert store.get("foo") is None
    assert "foo" not in store._data


def test_key_expires_via_sweep_whether_or_not_it_is_ever_read_again():
    # No get()/ttl() call on "foo" at any point - sweep_expired() alone
    # (what the active-expiration background loop calls on each tick)
    # must be the thing that removes it.
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)
    store.set("untouched", "still here")

    clock.advance(10)
    removed_count = store.sweep_expired()

    assert removed_count == 1
    assert "foo" not in store._data
    assert "foo" not in store._expires_at
    assert store._data["untouched"] == "still here"


def test_ttl_positive_immediately_after_expire_with_real_clock():
    # Uses the real default clock (not FakeClock) - the fake-clock tests
    # above start at t=0 with no advance, which can't reveal a bug in how
    # a real, nonzero timestamp is computed. This can.
    store = Store()
    store.set("temp", "val")
    assert store.expire("temp", 2) is True
    assert store.ttl("temp") > 0
    assert store.get("temp") == "val"


def test_active_expiration_loop_removes_expired_key_without_a_read():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)

    async def scenario() -> None:
        task = asyncio.create_task(run_active_expiration(store, interval=0.01))
        clock.advance(10)
        await asyncio.sleep(0.05)  # let the loop tick at least once
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    assert "foo" not in store._data


def test_exists_counts_only_existing_keys():
    store = Store()
    store.set("a", "1")
    store.set("b", "2")
    assert store.exists("a", "b", "c") == 2


def test_exists_counts_duplicate_keys_twice():
    store = Store()
    store.set("a", "1")
    assert store.exists("a", "a") == 2


def test_exists_does_not_count_expired_key():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)
    clock.advance(6)
    assert store.exists("foo") == 0


def test_incr_missing_key_starts_at_zero():
    store = Store()
    assert store.incr("counter") == 1


def test_incr_existing_integer_value():
    store = Store()
    store.set("counter", "10")
    assert store.incr("counter") == 11


def test_incr_non_integer_value_raises_value_error():
    store = Store()
    store.set("counter", "not a number")
    try:
        store.incr("counter")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_incr_does_not_clear_existing_ttl():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("counter", "1")
    store.expire("counter", 10)
    store.incr("counter")
    assert store.ttl("counter") == 10


def test_decr_missing_key_starts_at_zero():
    store = Store()
    assert store.decr("counter") == -1


def test_decr_existing_integer_value():
    store = Store()
    store.set("counter", "10")
    assert store.decr("counter") == 9


def test_append_to_missing_key_creates_it():
    store = Store()
    assert store.append("foo", "bar") == 3
    assert store.get("foo") == "bar"


def test_append_to_existing_key_returns_new_length():
    store = Store()
    store.set("foo", "bar")
    assert store.append("foo", "baz") == 6
    assert store.get("foo") == "barbaz"


def test_append_does_not_clear_existing_ttl():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 10)
    store.append("foo", "baz")
    assert store.ttl("foo") == 10


def test_mset_sets_multiple_keys():
    store = Store()
    store.mset({"a": "1", "b": "2"})
    assert store.get("a") == "1"
    assert store.get("b") == "2"


def test_mset_clears_ttl_on_each_key():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("a", "1")
    store.expire("a", 10)
    store.mset({"a": "2"})
    assert store.ttl("a") == -1


def test_mget_returns_values_in_order_with_none_for_missing():
    store = Store()
    store.set("a", "1")
    store.set("c", "3")
    assert store.mget("a", "b", "c") == ["1", None, "3"]


def test_mget_does_not_return_expired_value():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)
    clock.advance(6)
    assert store.mget("foo") == [None]


def test_type_of_existing_key_returns_string():
    store = Store()
    store.set("foo", "bar")
    assert store.type("foo") == "string"


def test_type_of_missing_key_returns_none():
    store = Store()
    assert store.type("nosuchkey") == "none"


def test_type_of_expired_key_returns_none():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)
    clock.advance(6)
    assert store.type("foo") == "none"


def test_snapshot_of_empty_store_is_empty():
    store = Store()
    assert store.snapshot() == []


def test_snapshot_includes_keys_without_ttl():
    store = Store()
    store.set("a", "1")
    store.set("b", "2")
    assert set(store.snapshot()) == {("a", "1", -1), ("b", "2", -1)}


def test_snapshot_includes_positive_ttl_for_keys_with_expiry():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 10)
    assert store.snapshot() == [("foo", "bar", 10)]


def test_snapshot_excludes_expired_key():
    clock = FakeClock()
    store = Store(clock=clock)
    store.set("foo", "bar")
    store.expire("foo", 5)
    clock.advance(6)
    assert store.snapshot() == []
