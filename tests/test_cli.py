import json

from wickhunter.cli import main


def test_cli_backtest_writes_reports(tmp_path, monkeypatch, capsys):
    csv_path = tmp_path / "m1.csv"
    csv_path.write_text(
        "time,open,high,low,close\n"
        "2026-01-01T09:00:00+00:00,100,105,98,104\n"
        "2026-01-01T09:01:00+00:00,104,106,103,105\n"
        "2026-01-02T09:00:00+00:00,100.5,100.8,97,99.5\n"
        "2026-01-02T09:01:00+00:00,99.5,101.5,99.2,101.2\n"
        "2026-01-02T09:02:00+00:00,101.2,106,101,105\n"
        "2026-01-02T09:03:00+00:00,105,106,104,105.5\n",
        encoding="utf-8",
    )
    output = tmp_path / "reports"
    monkeypatch.setattr("sys.argv", ["wickhunter", "backtest", "--data", str(csv_path),
        "--output-dir", str(output), "--minimum-rr", "1.0"])
    assert main() == 0
    captured = capsys.readouterr()
    assert '"total_trades": 1' in captured.out
    assert (output / "summary.json").exists()
    assert (output / "trades.csv").exists()
    assert (output / "rejected.csv").exists()
    assert (output / "audit.csv").exists()


def test_cli_paper_replay_writes_ledger(tmp_path, monkeypatch, capsys):
    ticks = tmp_path / "ticks.csv"
    ticks.write_text("time,price\n2026-01-02T09:00:00+00:00,100\n"
                     "2026-01-02T09:01:00+00:00,100\n"
                     "2026-01-02T09:02:00+00:00,101\n"
                     "2026-01-02T09:03:00+00:00,105\n", encoding="utf-8")
    intents = tmp_path / "intents.json"
    intents.write_text(json.dumps([{"time": "2026-01-02T09:01:00+00:00",
        "trigger": 101, "stop": 99, "target": 105}]), encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr("sys.argv", ["wickhunter", "paper-replay", "--ticks", str(ticks),
        "--intents", str(intents), "--ledger", str(ledger)])
    assert main() == 0
    assert ledger.exists()
    assert "POSITION_CLOSED" in ledger.read_text(encoding="utf-8")


def test_cli_generate_intents_exports_strategy_buy(tmp_path, monkeypatch, capsys):
    csv_path = tmp_path / "m1.csv"
    csv_path.write_text(
        "time,open,high,low,close\n"
        "2026-01-01T09:00:00+00:00,100,105,95,104\n"
        "2026-01-02T09:00:00+00:00,96,96.5,94,94.5\n"
        "2026-01-02T09:01:00+00:00,94.5,96.5,94,96\n"
        "2026-01-02T09:02:00+00:00,96,97,95.5,96.5\n",
        encoding="utf-8",
    )
    output = tmp_path / "buy-intents.json"
    monkeypatch.setattr("sys.argv", ["wickhunter", "generate-intents", "--data", str(csv_path),
        "--output", str(output)])
    assert main() == 0
    intents = json.loads(output.read_text(encoding="utf-8"))
    assert len(intents) == 1
    assert intents[0]["trigger"] == 96.5
    assert intents[0]["stop"] == 94.0
    assert intents[0]["target"] == 105.0
    assert "BUY intents: 1" in capsys.readouterr().out
