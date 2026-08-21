"""Fail fast when the installed Termux Python stack cannot import the project."""

from __future__ import annotations

import json
import platform

import fastapi
import pydantic
import starlette

from s10_control.main import create_app


EXPECTED = {
    "fastapi": "0.118.3",
    "pydantic": "1.10.26",
    "starlette": "0.48.0",
}


def main() -> int:
    observed = {
        "fastapi": fastapi.__version__,
        "pydantic": pydantic.__version__,
        "starlette": starlette.__version__,
    }
    if observed != EXPECTED:
        raise SystemExit(f"PYTHON_STACK_MISMATCH expected={EXPECTED!r} observed={observed!r}")
    app = create_app()
    if app.title != "S10 Control Server":
        raise SystemExit("PROJECT_IMPORT_FAILED")
    print(json.dumps({"state": "ready", "python": platform.python_version(), **observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
