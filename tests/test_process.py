import sys

from warmpass.process import run_subprocess


def test_subprocess_closes_stdin_and_captures_utf8_output_with_replacement() -> None:
    code = (
        "import sys; "
        "assert sys.stdin.read() == ''; "
        "sys.stdout.buffer.write(b'out \\xc3\\xa9\\xff'); "
        "sys.stderr.buffer.write(b'err \\xff')"
    )

    completed = run_subprocess([sys.executable, "-c", code], timeout=30, check=True)

    assert completed.stdout == "out é\ufffd"
    assert completed.stderr == "err \ufffd"
