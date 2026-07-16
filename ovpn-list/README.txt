# Drop your .ovpn profiles here.
# If this folder has one or more *.ovpn files, AutoGate uses ONLY these
# (after TCP live-check on remote host:port) and skips remote scrapers.
#
# Examples:
#   my-server.ovpn
#   jp-home.ovpn
#
# Env (see .env):
#   OVPN_LIST_PRIORITY=1     # prefer this folder when it has files
#   OVPN_LIST_LIVE_CHECK=1   # TCP probe before publish to ./ovpn
#   OVPN_LIVE_CHECK_TIMEOUT=3
