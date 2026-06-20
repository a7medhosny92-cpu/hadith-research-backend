"""Native desktop window for the Hadith Research app (via pywebview).

Starts the FastAPI app on a background thread and opens a native OS window showing
the simple Arabic UI (served at ``/app``) — so it looks and feels like a desktop
application, with Arabic rendered correctly by the embedded web view.

Run:
    pip install -e ".[desktop]"
    python -m app.desktop          # or the console script:  hadith-app
"""

from __future__ import annotations

import threading
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8765
UI_URL = f"http://{HOST}:{PORT}/app"


def _serve() -> None:
    """Run uvicorn in this (non-main) thread — signal handlers disabled."""
    import uvicorn

    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    server.install_signal_handlers = lambda: None  # only the main thread may set those
    server.run()


def _wait_until_up(timeout: float = 20.0) -> bool:
    """Poll /health until the server answers (or give up after ``timeout`` s)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    import webview  # the optional 'desktop' extra

    threading.Thread(target=_serve, daemon=True).start()
    _wait_until_up()
    # text_select=True: let the user select & copy text with the mouse. pywebview defaults it to
    # False (which disables selection window-wide, overriding the page's user-select:text CSS); the
    # CSS then keeps only the interactive chrome (buttons/chips) unselectable.
    webview.create_window(
        "بحث وتحقيق الحديث — Hadith Research", UI_URL, width=1024, height=760, text_select=True
    )
    webview.start()


if __name__ == "__main__":
    main()
