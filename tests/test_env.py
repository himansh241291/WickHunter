from pathlib import Path

from wickhunter.env import load_local_env


def test_load_local_env_preserves_existing_environment(monkeypatch, tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'GROWW_API_KEY="from-file"\n'
        "GROWW_API_SECRET=secret-from-file\n"
        "# comment\n"
        "export EXTRA=value\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("GROWW_API_KEY", "from-process")
    monkeypatch.delenv("GROWW_API_SECRET", raising=False)
    monkeypatch.delenv("EXTRA", raising=False)

    load_local_env(env_file)

    assert __import__("os").environ["GROWW_API_KEY"] == "from-process"
    assert __import__("os").environ["GROWW_API_SECRET"] == "secret-from-file"
    assert __import__("os").environ["EXTRA"] == "value"


def test_load_local_env_ignores_missing_file(tmp_path: Path):
    load_local_env(tmp_path / "missing.env")
