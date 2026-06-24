import base64
import datetime
import os
import re
import shutil
import tempfile
import urllib.request

API_URL = "http://www.vpngate.net/api/iphone/"
OVPN_DIR = "/ovpn"
TIMEOUT_SECONDS = 30
CONFIG_PATTERN = re.compile(r"^([^,]{3,}),.+,([a-zA-Z0-9+=]{100,})", flags=re.MULTILINE)


def log(message):
    print(datetime.datetime.now(), message, flush=True)


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def download_csv():
    with urllib.request.urlopen(API_URL, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def write_configs(csv, output_dir):
    written = 0
    for match in CONFIG_PATTERN.finditer(csv):
        name = safe_name(match.group(1))
        try:
            ovpn_text = base64.b64decode(match.group(2)).decode("utf-8")
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
