from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from blink.models import Repo
from blink.config import Config
from blink.store import Store
from blink.scanner import Scanner
from blink.tui.app import BlinkApp
from blink.tui.app_review import ReviewOrchestrator


@pytest.fixture
def app_with_store():
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="test-repo", path="/tmp/test"))

    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._config = MagicMock(spec=Config)
    app._config.preferred_ide = None
    app._config.nerd_fonts = False
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._search_bar = MagicMock()
    app._search_bar.text = ""
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = None
    app._repo_list_window = MagicMock()
    app._detail_window = MagicMock()
    app._edit_status_window = MagicMock()
    app._focus_pane = "list"
    app._search_active = False
    app._search_filtering = False
    app._footer_highlight_until = 0.0
    app._last_ctrl_c = 0.0
    app._ctrl_c_quit_hint = False
    app._app = MagicMock()
    app._ide_selecting = False
    app._ide_select_cursor = 0
    app._ide_pending_path = None
    app._committing_paths = set()
    app._pulling_paths = set()
    app._review = ReviewOrchestrator(app)
    yield app, store, rid
