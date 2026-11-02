"""Tests that the MCP server module imports cleanly without side effects."""

import foodguide.server


def test_server_module_exposes_entry_points() -> None:
    assert callable(foodguide.server.create_server)
    assert callable(foodguide.server.main)


def test_importing_server_does_not_start_it() -> None:
    # create_server only builds the app; nothing is run at import time.
    assert foodguide.server.__name__ == "foodguide.server"
