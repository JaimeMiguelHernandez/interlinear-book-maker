import json
import subprocess
from pathlib import Path

import pytest

from interlinear_book_maker.claude_cli import (EFFORT, MODEL, RETRY_WAIT_SECONDS, Client,
                               TransportError)

USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 1180,
         "cache_read_input_tokens": 0, "output_tokens": 93}


def _ok(rows):
    return 0, json.dumps({"type": "result", "subtype": "success",
                          "is_error": False, "api_error_status": None,
                          "result": json.dumps({"rows": rows}),
                          "structured_output": {"rows": rows}, "usage": USAGE})


def _error(result, status=None):
    return 1, json.dumps({"type": "result", "subtype": "success",
                          "is_error": True, "api_error_status": status,
                          "result": result})


ONE = [{"id": 1, "english": "The stench."}]


class FakeRun:
    """Records each call; reads the system-prompt file while it still exists."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.system_texts = []
        self.system_paths = []

    def __call__(self, argv, input):
        self.calls.append((argv, input))
        path = Path(argv[argv.index("--system-prompt-file") + 1])
        self.system_paths.append(path)
        self.system_texts.append(path.read_text(encoding="utf-8"))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _translate(run, slept=None):
    sleep = slept.append if slept is not None else (lambda _s: None)
    return Client("claude.CMD", run, sleep=sleep).translate(
        ["Der Gestank."], context="Es war ein Sommer.", entries=[],
        instructions=["Keep register formal."])


def _value(argv, flag):
    return argv[argv.index(flag) + 1]


def test_argv_isolates_the_call_and_pins_model_and_effort():
    run = FakeRun(_ok(ONE))
    _translate(run)
    argv, _ = run.calls[0]
    assert argv[:2] == ["claude.CMD", "-p"]
    assert _value(argv, "--model") == MODEL == "claude-sonnet-5"
    assert _value(argv, "--effort") == EFFORT == "low"
    assert _value(argv, "--tools") == ""
    assert _value(argv, "--setting-sources") == ""
    assert _value(argv, "--output-format") == "json"
    assert json.loads(_value(argv, "--json-schema"))["type"] == "object"
    for flag in ("--strict-mcp-config", "--disable-slash-commands",
                 "--no-session-persistence"):
        assert flag in argv


def test_the_system_prompt_goes_through_a_file_removed_afterwards():
    run = FakeRun(_ok(ONE))
    _translate(run)
    assert "Keep register formal." in run.system_texts[0]
    assert "Es war ein Sommer." in run.system_texts[0]
    assert not run.system_paths[0].exists()


def test_the_sentences_go_through_stdin_never_argv():
    run = FakeRun(_ok(ONE))
    _translate(run)
    argv, stdin = run.calls[0]
    assert stdin == "1. Der Gestank."
    assert not any("Gestank" in arg or "Sommer" in arg for arg in argv)


def test_translate_returns_translations_and_the_token_count():
    translations, tokens = _translate(FakeRun(_ok(ONE)))
    assert translations[0].text == "The stench."
    assert tokens == 2 + 1180 + 0 + 93


def test_a_429_usage_limit_stops_at_once():
    run, slept = FakeRun(_error("Rate limited", status=429)), []
    with pytest.raises(TransportError, match="^Claude usage limit reached"):
        _translate(run, slept)
    assert len(run.calls) == 1 and slept == []


def test_a_limit_message_without_a_status_also_stops_at_once():
    run = FakeRun(_error("You've hit your limit · resets 3pm"))
    with pytest.raises(TransportError, match="usage limit"):
        _translate(run)
    assert len(run.calls) == 1


def test_an_overloaded_reply_is_retried_after_a_minute():
    run, slept = FakeRun(_error("Overloaded", status=529), _ok(ONE)), []
    translations, _ = _translate(run, slept)
    assert translations[0].text == "The stench."
    assert len(run.calls) == 2 and slept == [RETRY_WAIT_SECONDS]


def test_a_timeout_is_retried():
    run = FakeRun(subprocess.TimeoutExpired("claude", 300), _ok(ONE))
    _translate(run)
    assert len(run.calls) == 2


def test_two_transient_failures_raise_transport_error():
    run = FakeRun(_error("Overloaded", status=529), _error("Overloaded", status=529))
    with pytest.raises(TransportError, match="2 attempts.*529"):
        _translate(run)
    assert len(run.calls) == 2


def test_other_errors_carry_the_cli_message_and_are_not_retried():
    run = FakeRun(_error("Not logged in · Please run /login"))
    with pytest.raises(TransportError, match="Not logged in"):
        _translate(run)
    assert len(run.calls) == 1


def test_non_json_output_raises_transport_error():
    run = FakeRun((1, "'claude' is not recognized as a command"))
    with pytest.raises(TransportError, match="not recognized"):
        _translate(run)
