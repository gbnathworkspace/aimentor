"""Issue #15: chat history sent to the LLM is windowed to bound token cost."""

from types import SimpleNamespace

from app.routers.mentor import _window_messages, _MAX_HISTORY_MESSAGES


def _msg(role, content="x"):
    return SimpleNamespace(role=role, content=content)


def test_trims_to_last_n():
    history = [_msg("user" if i % 2 == 0 else "assistant", str(i)) for i in range(60)]
    out = _window_messages(history, limit=10)
    assert len(out) <= 10
    # keeps the most recent, not the oldest
    assert out[-1]["content"] == "59"


def test_first_message_is_user():
    # Tail of the window starts on an assistant turn → must be dropped.
    history = [_msg("user"), _msg("assistant"), _msg("user"), _msg("assistant")]
    out = _window_messages(history, limit=2)  # tail = [user(idx2), assistant(idx3)]
    assert out[0]["role"] == "user"


def test_short_history_unchanged():
    history = [_msg("user", "hi"), _msg("assistant", "hello")]
    out = _window_messages(history, limit=_MAX_HISTORY_MESSAGES)
    assert [m["content"] for m in out] == ["hi", "hello"]
