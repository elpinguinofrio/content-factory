"""Unit tests for config_loader."""

import unittest
from pathlib import Path

from mock_dating.agent.config_loader import Config, load_config


class ConfigLoaderTests(unittest.TestCase):
    def test_load_default_config(self) -> None:
        config = load_config()
        self.assertIsInstance(config, Config)
        self.assertEqual(config.persona.display_name, "Alex")
        self.assertIn("dogs", config.preferences.likes)
        self.assertEqual(config.runtime.mode, "auto")

    def test_snapshot_is_plain_dict(self) -> None:
        config = load_config()
        snap = config.snapshot()
        self.assertIn("persona", snap)
        self.assertIn("preferences", snap)
        self.assertIn("runtime", snap)
        self.assertEqual(snap["persona"]["display_name"], "Alex")

    def test_load_from_custom_dir(self) -> None:
        # Fallback: default package dir still works when explicitly passed.
        default_dir = Path(__file__).resolve().parent.parent / "agent" / "config"
        config = load_config(default_dir)
        self.assertEqual(config.persona.display_name, "Alex")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
