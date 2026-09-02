import os
import sys
import warnings
import webbrowser
import threading

# Suppress harmless requests dependency warning
warnings.filterwarnings("ignore")

from app import create_app
from app.extensions import socketio

# FF Custom Arena Server Configuration
app = create_app(os.environ.get("FLASK_ENV", "development"))

def open_browser(port):
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 60)
    print(" >>> FF CUSTOM ARENA SERVER STARTED SUCCESSFULLY! <<<")
    print(f" [*] Localhost URL: http://localhost:{port} (or http://127.0.0.1:{port})")
    print(" [*] Default Admin: username: subrat | password: subrat7894")
    print(" [*] Press CTRL+C to stop the server")
    print("=" * 60 + "\n")
    sys.stdout.flush()

    # Automatically open browser tab
    threading.Timer(1.5, open_browser, args=(port,)).start()

    # Flask's debug reloader starts a second Eventlet server on Windows,
    # causing WinError 10048 (port already in use). Keep debug mode, but
    # disable the incompatible automatic reloader there.
    try:
        socketio.run(
            app,
            host="0.0.0.0",
            port=port,
            debug=app.config["DEBUG"],
            use_reloader=False,
        )
    except OSError as e:
        if "10048" in str(e):
            print(f"\n[!] Error: Port {port} is already in use by another process.")
            print("[!] Please close other running instances or choose another PORT.\n")
        else:
            raise e
