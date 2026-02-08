from pathlib import Path
from typing import Tuple


def load_credentials(path: Path | str = "scripts/.credentials") -> Tuple[str, str]:
    """Load credentials from a simple key=value file or two-line file.

    Accepts either:
    username=...\npassword=...
    or two lines: first is username, second is password.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If username or password can't be found.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Credentials file not found: {p}")

    lines = [
        ln.strip()
        for ln in p.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        raise ValueError("Credentials file is empty")

    # key=value format
    if any("=" in ln for ln in lines):
        data: dict[str, str] = {}
        for ln in lines:
            if "=" in ln:
                k, v = ln.split("=", 1)
                data[k.strip().lower()] = v.strip()
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            raise ValueError(
                "Credentials file must contain username and password (key=value)"
            )
        return username, password

    # fallback: assume first is username, second is password
    if len(lines) >= 2:
        return lines[0], lines[1]

    raise ValueError("Credentials file must contain username and password")
