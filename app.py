#!/usr/bin/env python3
"""agy-delegate desktop app: the control panel in a native window (Tailgate look: solid paper, ink and one orange;
the OS glass effects are applied but the page paints over them). Run: python3 app.py   (--prepare: only set up the runtime)

The only third-party piece, pywebview, is installed automatically on first run into a private venv
(~/.agy-delegate/venv), never into your system Python. If that is impossible (offline, no venv module), the same
panel opens in the browser instead."""
import os, socket, subprocess, sys, threading, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or sys.stderr is None:   # windowed build has no console: keep a log instead of crashing on print
    _log = os.path.join(os.path.expanduser("~"), ".agy-delegate", "app.log"); os.makedirs(os.path.dirname(_log), exist_ok=True)
    sys.stdout = sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)
sys.path[:0] = [HERE, os.path.join(HERE, "plugins", "agy-delegate", "scripts")]
import agyctl   # noqa: E402

PYWEBVIEW = "pywebview==6.2.1"
VENV = os.path.join(agyctl.home(), ".agy-delegate", "venv")
VPY = os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python")


def have_webview():
    try: import webview  # noqa: F401
    except Exception: return False
    return True

def prepare(log=print):
    """Create the private venv with pywebview if missing. Returns True when the venv can show the window."""
    if os.path.exists(VPY) and subprocess.run([VPY, "-c", "import webview"], capture_output=True).returncode == 0: return True
    log("Setting up the desktop app runtime (one time, ~30 s)...")
    try:
        if not os.path.exists(VPY): subprocess.run([sys.executable, "-m", "venv", VENV], check=True, capture_output=True, timeout=300)
        r = subprocess.run([VPY, "-m", "pip", "install", "--disable-pip-version-check", "-q", PYWEBVIEW], capture_output=True, text=True, timeout=900)
        if r.returncode: log((r.stdout + r.stderr).strip()[-2000:]); return False
        return subprocess.run([VPY, "-c", "import webview"], capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        log(f"desktop runtime unavailable ({e})"); return False


def windows_glass(hwnd):
    """Blur what is behind the window: DWM acrylic backdrop on Windows 11, accent blur-behind on Windows 10."""
    import ctypes
    from ctypes import wintypes
    dark = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))   # dark title bar
    if sys.getwindowsversion().build >= 22000:   # Windows 11: native rounded corners
        corner = ctypes.c_int(2)   # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    if sys.getwindowsversion().build >= 22621:
        backdrop = ctypes.c_int(3)   # DWMSBT_TRANSIENTWINDOW (acrylic)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        return
    class ACCENT(ctypes.Structure):
        _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int), ("color", ctypes.c_uint), ("anim", ctypes.c_int)]
    class DATA(ctypes.Structure):
        _fields_ = [("attr", ctypes.c_int), ("data", ctypes.POINTER(ACCENT)), ("size", ctypes.c_size_t)]
    # Windows 10 DWM blur ignores window regions (square blur behind rounded corners), so the window is made fully
    # transparent (ACCENT_ENABLE_TRANSPARENTGRADIENT, alpha 0) and the page paints its own rounded tinted glass.
    accent = ACCENT(2, 2, 0x00000000, 0)
    data = DATA(19, ctypes.pointer(accent), ctypes.sizeof(accent))   # WCA_ACCENT_POLICY
    ctypes.windll.user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data))


def round_corners_win10(form, radius=18):
    """Windows 10 has no rounded-corner attribute: clip the window to a rounded region, redone on every resize."""
    import ctypes
    if sys.getwindowsversion().build >= 22000: return
    from System import EventHandler
    from System.Windows.Forms import FormWindowState
    def apply(*_):
        h = form.Handle.ToInt32()
        if form.WindowState == FormWindowState.Maximized: ctypes.windll.user32.SetWindowRgn(h, None, True); return
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, form.Width + 1, form.Height + 1, radius * 2, radius * 2)
        ctypes.windll.user32.SetWindowRgn(h, rgn, True)   # the window owns rgn from here on
    form.Resize += EventHandler(apply); apply()


def free_port(pref):
    with socket.socket() as s:
        try: s.bind(("127.0.0.1", pref)); return pref
        except OSError: s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def serve():
    import panel
    from http.server import ThreadingHTTPServer
    port = free_port(int(os.environ.get("AGY_PANEL_PORT", 8765)))
    srv = ThreadingHTTPServer(("127.0.0.1", port), panel.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=panel.maybe_auto_update, daemon=True).start()
    return f"http://127.0.0.1:{port}"

class WindowApi:
    """Called by the traffic-light buttons of the frameless window (window.pywebview.api.*)."""
    def __init__(self): self._w, self._max = None, False   # private: pywebview exposes public attributes to JS
    def close(self): self._w.destroy()
    def minimize(self): self._w.minimize()
    def toggle_maximize(self):
        (self._w.restore if self._max else self._w.maximize)(); self._max = not self._max

def run_window(url):
    import webview
    mac, api = sys.platform == "darwin", WindowApi()
    # macOS keeps its titled window (transparent title bar: native traffic lights and rounded corners)
    osname = "mac" if mac else "win10" if os.name == "nt" and sys.getwindowsversion().build < 22000 else "win"
    w = api._w = webview.create_window("agy-delegate", f"{url}/?shell=native&os={osname}",
                                      width=1120, height=760, min_size=(560, 600), frameless=not mac, easy_drag=False, transparent=True, vibrancy=mac,
                                      background_color="#0b0e24", js_api=api)
    if os.name == "nt":
        def on_shown():
            try:
                from System import Action
                from System.Drawing import Color
                form = w.native
                def paint():   # with DWM blur, GDI black is alpha 0: the blurred desktop shows through
                    form.BackColor = Color.Black; windows_glass(form.Handle.ToInt32()); round_corners_win10(form)
                form.Invoke(Action(paint))
            except Exception as e: print("glass effect unavailable:", e)
        w.events.shown += on_shown
    webview.start(private_mode=False, storage_path=os.path.join(agyctl.home(), ".agy-delegate", "webview"))

def selftest():
    """Packaged-binary check used by CI: serve the panel and hit every read endpoint once, without a window."""
    import json, urllib.request
    base = serve()
    for path, check in (("/api/ping", lambda b: json.loads(b)["app"] == "agy-delegate-panel"), ("/", lambda b: b"agy-delegate" in b),
                        ("/api/status", lambda b: "plugins" in json.loads(b)), ("/api/stats", lambda b: "windows" in json.loads(b)),
                        ("/api/router", lambda b: "choices" in json.loads(b)), ("/assets/icon-256.png", lambda b: b[1:4] == b"PNG")):
        with urllib.request.urlopen(base + path, timeout=30) as r: body = r.read()
        if not check(body): print("selftest FAILED:", path); return 1
        print("selftest ok:", path)
    print("selftest passed, version", agyctl.local_version(), "webview" if have_webview() else "no webview"); return 0

def main(argv):
    if "--selftest" in argv: sys.exit(selftest())
    if "--prepare" in argv: sys.exit(0 if prepare() else 1)
    old = sys.executable + ".old"   # left by a previous self-update of the packaged app
    if agyctl.FROZEN and os.path.exists(old):
        try: os.remove(old)
        except OSError: pass
    if not have_webview() and os.path.abspath(sys.executable) != os.path.abspath(VPY) and "--browser" not in argv:
        if prepare():   # re-run inside the private venv
            sys.exit(subprocess.call([VPY, os.path.abspath(__file__)] + argv))
    url = serve()
    if have_webview() and "--browser" not in argv:
        try: return run_window(url)
        except Exception as e: print("native window failed, opening the browser:", e)
    print(f"agy-delegate panel: {url}  (Ctrl-C to stop)"); webbrowser.open(url)
    try: threading.Event().wait()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main(sys.argv[1:])
