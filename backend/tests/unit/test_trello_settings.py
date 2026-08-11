import app.trello_settings as trello_settings
from app.trello_settings import clear_trello_settings, load_trello_settings, save_trello_settings


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(trello_settings, "SETTINGS_PATH", tmp_path / "trello_settings.json")


def test_load_returns_none_when_nothing_saved(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert load_trello_settings() is None


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    save_trello_settings("real-key", "real-token")

    loaded = load_trello_settings()

    assert loaded == {"api_key": "real-key", "token": "real-token"}


def test_save_creates_the_parent_directory_if_missing(tmp_path, monkeypatch):
    nested = tmp_path / "does" / "not" / "exist" / "trello_settings.json"
    monkeypatch.setattr(trello_settings, "SETTINGS_PATH", nested)

    save_trello_settings("k", "t")

    assert nested.exists()
    assert load_trello_settings() == {"api_key": "k", "token": "t"}


def test_clear_removes_a_saved_connection(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    save_trello_settings("k", "t")

    clear_trello_settings()

    assert load_trello_settings() is None


def test_clear_is_a_no_op_when_nothing_was_ever_saved(tmp_path, monkeypatch):
    # Disconnecting when there's nothing to disconnect shouldn't raise -
    # the dashboard's Disconnect button should be safe to click any time.
    _isolate(tmp_path, monkeypatch)
    clear_trello_settings()
    assert load_trello_settings() is None


def test_load_ignores_a_malformed_settings_file(tmp_path, monkeypatch):
    path = tmp_path / "trello_settings.json"
    path.write_text("not valid json{{{")
    monkeypatch.setattr(trello_settings, "SETTINGS_PATH", path)

    assert load_trello_settings() is None


def test_load_ignores_a_settings_file_missing_a_field(tmp_path, monkeypatch):
    path = tmp_path / "trello_settings.json"
    path.write_text('{"api_key": "k"}')
    monkeypatch.setattr(trello_settings, "SETTINGS_PATH", path)

    assert load_trello_settings() is None
