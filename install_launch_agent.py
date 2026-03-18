"""安装 macOS LaunchAgent，使 TFT-Sniper 登录后自动启动。"""

import os
from pathlib import Path
import plistlib
import subprocess
import sys

LABEL = "com.hh.tft-sniper"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _build_plist() -> dict:
    repo_root = _repo_root()
    python_path = Path(sys.executable).resolve()
    main_path = repo_root / "main.py"
    stdout_path = Path("/tmp") / "tft-sniper.launchd.out.log"
    stderr_path = Path("/tmp") / "tft-sniper.launchd.err.log"

    return {
        "Label": LABEL,
        "ProgramArguments": [str(python_path), str(main_path)],
        "WorkingDirectory": str(repo_root),
        "RunAtLoad": True,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
    }


def _launchctl(*args):
    return subprocess.run(
        ["launchctl", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def main():
    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    with open(plist_path, "wb") as f:
        plistlib.dump(_build_plist(), f)

    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", domain, str(plist_path))

    result = _launchctl("bootstrap", domain, str(plist_path))
    if result.returncode != 0:
        print("❌ LaunchAgent 安装失败")
        if result.stderr.strip():
            print(result.stderr.strip())
        sys.exit(result.returncode or 1)

    restart = _launchctl("kickstart", "-k", f"{domain}/{LABEL}")
    if restart.returncode != 0:
        print("⚠️ LaunchAgent 已写入，但立即启动失败")
        if restart.stderr.strip():
            print(restart.stderr.strip())
        print(f"   plist: {plist_path}")
        sys.exit(restart.returncode or 1)

    print("✅ LaunchAgent 已安装并启动")
    print(f"   Label: {LABEL}")
    print(f"   plist: {plist_path}")
    print(f"   Python: {Path(sys.executable).resolve()}")
    print("   以后登录后会自动启动，游戏运行时自动激活，退出后自动暂停")
    print("   如需卸载：")
    print(f"   launchctl bootout {domain} {plist_path}")
    print(f"   rm {plist_path}")


if __name__ == "__main__":
    main()
