import base64
import csv
import datetime
import os
import re
import shutil
import tempfile
import urllib.request

API_URL = "http://www.vpngate.net/api/iphone/"
OVPN_DIR = "/ovpn"
TIMEOUT_SECONDS = 30
CONFIG_FIELD = "OpenVPN_ConfigData_Base64"


def log(message):
    print(datetime.datetime.now(), message, flush=True)


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def download_csv():
    with urllib.request.urlopen(API_URL, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def country_filter():
    countries = os.environ.get("COUNTRY_FILTER", "")
    return {country.strip().upper() for country in countries.split(",") if country.strip()}


def csv_rows(csv_text):
    lines = []
    for line in csv_text.splitlines():
        if line.startswith("*") or not line.strip():
            continue
        if line.startswith("#"):
            line = line[1:]
        lines.append(line)
    return csv.DictReader(lines)


def write_configs(csv, output_dir):
    written = 0
    allowed_countries = country_filter()
    if allowed_countries:
        log(f"vpngate - country filter: {','.join(sorted(allowed_countries))}")

    for row in csv_rows(csv):
        country = row.get("CountryShort", "").upper()
        if allowed_countries and country not in allowed_countries:
            continue

        name = safe_name(row.get("HostName", "vpn"))
        try:
            ovpn_text = base64.b64decode(row.get(CONFIG_FIELD, "")).decode("utf-8")
        except Exception as exc:
            log(f"vpngate - download - skip {name}: {exc}")
            continue

        with open(os.path.join(output_dir, f"{name}.ovpn"), "w", encoding="utf-8") as file:
            file.write(ovpn_text)
        written += 1
        log(f"vpngate - download - write: {name}")
    return written


def replace_configs(source_dir):
    os.makedirs(OVPN_DIR, exist_ok=True)

    new_files = set(os.listdir(source_dir))
    for filename in os.listdir(source_dir):
        shutil.move(os.path.join(source_dir, filename), os.path.join(OVPN_DIR, filename))

    for root, _, files in os.walk(OVPN_DIR):
        for filename in files:
            if filename not in new_files:
                os.unlink(os.path.join(root, filename))


def main():
    log("vpngate download - start")
    with tempfile.TemporaryDirectory() as temp_dir:
        csv = download_csv()
        written = write_configs(csv, temp_dir)
        if written == 0:
            raise RuntimeError("VPNGate returned no usable ovpn configs")
        replace_configs(temp_dir)
        log(f"vpngate - download - end ({written} configs)")


if __name__ == "__main__":
    main()
