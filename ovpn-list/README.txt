# Drop your .ovpn profiles here, OR download from PublicVPNList:
#
#   .\download_publicvpnlist.bat
#   .\download_publicvpnlist.bat JP 10
#   python download_publicvpnlist.py --country JP --max 10 --clear
#
# If this folder has one or more *.ovpn files, AutoGate uses ONLY these
# (after TCP live-check on remote host:port) and skips remote scrapers.
#
# Examples:
#   my-server.ovpn
#   pvl_JP_1.2.3.4_443.ovpn
#
# Env (see .env):
#   OVPN_LIST_PRIORITY=1     # prefer this folder when it has files
#   OVPN_LIST_LIVE_CHECK=1   # TCP probe before publish to ./ovpn
#   OVPN_LIVE_CHECK_TIMEOUT=3
