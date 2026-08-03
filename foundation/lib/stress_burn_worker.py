"""Isolated CPU burn worker — subprocess entry (Windows-safe, no rid_main re-exec)."""
from __future__ import annotations


def main() -> None:
    x = 1.0
    while True:
        x = (x * 1.000001 + 0.000001) % 100000.0


if __name__ == "__main__":
    main()
