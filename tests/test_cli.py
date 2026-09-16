from pathlib import Path

from wickhunter.cli import main


def test_cli_backtest_writes_reports(tmp_path, monkeypatch, capsys):
    csv_path = tmp_path / "m1.csv"
    csv_path.write_text(
        "time,open,high,low,close\n"
        "2026-01-01T09:00:00+00:00,100,105,98,104\n"
        "2026-01-01T09:01:00+00:00,104,106,103,105\n"
        "2026-01-02T09:00:00+00:00,100.5,100.8,99,99.5\n"
        "2026-01-02T09:01:00+00:00,99.5,101.5,99.2,101.2\n"
        "2026-01-02T09:02:00+00:00,101.2,106,101,105\n"
        "2026-01-02T09:03:00+00:00,105,106,104,105.5\n",
        encoding="utf-8",
    )
    output = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        ["wickhunter", "backtest", "--data", str(csv_path), "--output-dir", str(output)],
    )

    assert main() == 0
    captured = capsys.readouterr()
    assert '"total_trades": 1' in captured.out
    assert (output / "summary.json").exists()
    assert (output / "trades.csv").exists()
    assert (output / "rejected.csv").exists()
    assert (output / "audit.csv").exists()
