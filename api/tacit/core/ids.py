import os
import time

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def new_id(prefix: str) -> str:
    """Sortable, prefixed ids: <prefix>_<time-ordered 26 chars>. Readable in logs, unique enough for one org."""
    t = int(time.time() * 1000)
    ts = ""
    for _ in range(10):
        ts = _ALPHABET[t & 31] + ts
        t >>= 5
    rnd = "".join(_ALPHABET[b & 31] for b in os.urandom(16))
    return f"{prefix}_{ts}{rnd}"
