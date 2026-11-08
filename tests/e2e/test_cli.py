import os
import subprocess
import sys
import sysconfig
from pathlib import Path


def test_cli_help(tmp_path: Path) -> None:
    scripts_directory = Path(sysconfig.get_path("scripts"))
    executable_name = "warmpass" if sys.platform != "win32" else "warmpass.exe"
    executable = scripts_directory / executable_name

    result = subprocess.run(
        [str(executable), "--help"],
        cwd=tmp_path,
        env={**os.environ, "HOME": str(tmp_path), "NO_COLOR": "1"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
