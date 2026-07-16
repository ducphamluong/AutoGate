#!/usr/bin/env python3
"""Backward-compatible entrypoint — delegates to multi-source ovpn_refresh."""

from ovpn_refresh import main

if __name__ == "__main__":
    main()
