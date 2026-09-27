from __future__ import annotations

from typer.testing import CliRunner

from tradebot.cli import app

runner = CliRunner()


def test_config_command() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0, result.output
    assert "config ok" in result.output


def test_holdout_requires_flag() -> None:
    result = runner.invoke(app, ["holdout"])
    assert result.exit_code == 2
