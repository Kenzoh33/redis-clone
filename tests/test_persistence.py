import json

from persistence import PersistenceLog, replay


def test_append_writes_json_line(tmp_path):
    log = PersistenceLog(tmp_path / "log")
    log.append(["SET", "foo", "bar"])
    log.close()

    lines = (tmp_path / "log").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == ["SET", "foo", "bar"]


def test_append_multiple_lines_in_order(tmp_path):
    log = PersistenceLog(tmp_path / "log")
    log.append(["SET", "a", "1"])
    log.append(["SET", "b", "2"])
    log.append(["DEL", "a"])
    log.close()

    lines = (tmp_path / "log").read_text().splitlines()
    assert [json.loads(line) for line in lines] == [
        ["SET", "a", "1"],
        ["SET", "b", "2"],
        ["DEL", "a"],
    ]


def test_replay_calls_apply_for_each_line_in_order(tmp_path):
    path = tmp_path / "log"
    path.write_text('["SET", "a", "1"]\n["SET", "b", "2"]\n["DEL", "a"]\n')

    calls = []
    replay(path, calls.append)

    assert calls == [["SET", "a", "1"], ["SET", "b", "2"], ["DEL", "a"]]


def test_replay_missing_file_is_noop(tmp_path):
    calls = []
    replay(tmp_path / "nosuchfile", calls.append)
    assert calls == []


def test_replay_empty_file_is_noop(tmp_path):
    path = tmp_path / "log"
    path.write_text("")

    calls = []
    replay(path, calls.append)
    assert calls == []
