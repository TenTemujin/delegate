#!/usr/bin/env python3
"""Build the agy-delegate desktop app with PyInstaller.
Run: python -m pip install -r packaging/requirements.txt && python packaging/build.py
Output (in dist/): agy-delegate-windows-x64.exe on Windows, agy-delegate-macos.zip (agy-delegate.app) on macOS,
plus <asset>.sha256. The binary is smoke-tested with --selftest before the build counts as done."""
import hashlib, os, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DIST, WORK = os.path.join(ROOT, "dist"), os.path.join(ROOT, "build")
DATA = ["panel.html", "assets", "plugins", ".claude-plugin"]   # read at runtime by panel.py / agyctl.py

def run(cmd):
    print("+", " ".join(cmd), flush=True); subprocess.run(cmd, check=True, cwd=ROOT)

def main():
    win, mac = os.name == "nt", sys.platform == "darwin"
    if not (win or mac): sys.exit("desktop binaries are built for Windows and macOS; Linux uses install.sh + app.py")
    shutil.rmtree(DIST, ignore_errors=True); shutil.rmtree(WORK, ignore_errors=True)
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "agy-delegate",
            "--distpath", DIST, "--workpath", WORK, "--specpath", WORK,
            "--icon", os.path.join(ROOT, "assets", "icon.ico" if win else "icon.icns")]
    for d in DATA:   # a file goes to the bundle root, a folder keeps its name
        dest = d if os.path.isdir(os.path.join(ROOT, d)) else "."
        args += ["--add-data", f"{os.path.join(ROOT, d)}{os.pathsep}{dest}"]
    args += ["--hidden-import", "monitor", "--hidden-import", "agyctl", "--hidden-import", "router",
             "--paths", os.path.join(ROOT, "plugins", "agy-delegate", "scripts"),
             "--paths", os.path.join(ROOT, "plugins", "agy-delegate", "skills", "agy-delegate", "scripts")]
    if win: args += ["--onefile"]
    else: args += ["--osx-bundle-identifier", "io.github.tentemujin.agy-delegate"]
    run(args + [os.path.join(ROOT, "app.py")])
    if win:
        asset = os.path.join(DIST, "agy-delegate-windows-x64.exe"); os.replace(os.path.join(DIST, "agy-delegate.exe"), asset)
        binary = asset
    else:
        app = os.path.join(DIST, "agy-delegate.app"); asset = os.path.join(DIST, "agy-delegate-macos.zip")
        run(["ditto", "-c", "-k", "--keepParent", app, asset])
        binary = os.path.join(app, "Contents", "MacOS", "agy-delegate")
    run([binary, "--selftest"])   # the packaged binary must serve every endpoint before it ships
    h = hashlib.sha256(open(asset, "rb").read()).hexdigest()
    with open(asset + ".sha256", "w", encoding="utf-8", newline="\n") as f:   # LF: sha256sum -c rejects CRLF
        f.write(f"{h}  {os.path.basename(asset)}\n")
    print(f"built {asset} ({os.path.getsize(asset) // 1024} KB) sha256 {h}")

if __name__ == "__main__":
    main()
