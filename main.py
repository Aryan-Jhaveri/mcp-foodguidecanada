#!/usr/bin/env python3
"""Compat shim: run the foodguide CLI without installing the package.

Prefer the installed entry point (`uv run foodguide`). This shim only exists
so `python main.py` keeps working from a source checkout.
"""

from foodguide.cli import main

if __name__ == "__main__":
    main()
