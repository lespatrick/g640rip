"""Desktop Native GUI launcher for Canon G640 micro-RIP using pywebview and macOS WebKit."""

import threading
import time
import socket
import webview
import uvicorn
from .server import app


def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def launch_desktop_gui(host: str = "127.0.0.1", port: int = 8640):
    """
    Launch native macOS desktop application window.
    Spawns background ASGI server and embeds UI in native Cocoa / WKWebView.
    """
    # Start uvicorn server in daemon thread if not already running
    if not _is_port_in_use(port, host):
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        # Wait until port is ready
        retries = 30
        while retries > 0 and not _is_port_in_use(port, host):
            time.sleep(0.1)
            retries -= 1

    # Create native Cocoa window via pywebview
    window = webview.create_window(
        title="Canon PIXMA G640 Micro-RIP",
        url=f"http://{host}:{port}",
        width=1320,
        height=880,
        min_size=(1080, 720),
        text_select=True,
    )

    webview.start(debug=False)

