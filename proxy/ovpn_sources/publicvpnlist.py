"""PublicVPNList adapter — capped; short-lived downloads need live check.

Chrome recon (2026-07-16):
  - Country pages: /country/{slug}/ list server ids + /download/{id}/
  - /download/{id}/ is an HTML interstitial, NOT the .ovpn body
  - User must "Run current check" to mint a temporary file URL
  - Pure HTTP cannot obtain stable .ovpn without that interactive step

Feasibility: HTTP-only auto-download = NO (without browser/captcha workflow).
Adapter stays registered, returns [] with clear log unless a future API appears.
Optional OPENPROXYLIST-style override not available for short-lived URLs.
"""

from __future__ import annotations

import os
from typing import Set


class PublicVpnListSource:
    key = "publicvpnlist"

    def fetch(self, allowed_countries: Set[str]) -> list:
        # Keep env knobs documented for future enablement.
        _ = (
            allowed_countries,
            os.environ.get("PUBLICVPNLIST_MAX_PER_COUNTRY", "10"),
            os.environ.get("PUBLICVPNLIST_BUDGET_SECONDS", "90"),
        )
        print(
            "publicvpnlist skipped: no stable HTTP .ovpn API "
            "(download pages require interactive live-check for temporary links)",
            flush=True,
        )
        return []
