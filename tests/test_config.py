from src.config import load_config


def test_load_config_defaults(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
trading_mode: simulation
polymarket:
  rest_base_url: https://example.com
alerts:
  discord_webhook_url: https://example.com/webhook
"""
    )
    config = load_config(str(config_path))
    assert config.trading_mode == "simulation"
    assert config.polymarket.rest_base_url == "https://example.com"
    assert config.alerts.discord_webhook_url == "https://example.com/webhook"
