# Hướng dẫn tự connect proxy: VPNGate, WARP, Psiphon

Tài liệu mô tả cách **tự kết nối và sử dụng** từng nguồn egress mà AutoGate tích hợp, **không cần** bật full stack HAProxy. Mục tiêu: hiểu từng thành phần và có proxy local để tool/curl dùng được.

> **Phạm vi sử dụng:** chỉ dùng trên hệ thống/mạng bạn sở hữu hoặc được phép kiểm thử. Tuân thủ ToS của VPNGate, Cloudflare WARP, Psiphon và luật hiện hành.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [VPNGate (OpenVPN → HTTP proxy)](#2-vpngate-openvpn--http-proxy)
3. [Cloudflare WARP (SOCKS5)](#3-cloudflare-warp-socks5)
4. [Psiphon (HTTP + SOCKS)](#4-psiphon-http--socks)
5. [So sánh & chọn nhanh](#5-so-sánh--chọn-nhanh)
6. [Checklist kiểm tra](#6-checklist-kiểm-tra)
7. [Chạy song song vài proxy](#7-chạy-song-song-vài-proxy)
8. [Ánh xạ với code AutoGate](#8-ánh-xạ-với-code-autogate)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Tổng quan kiến trúc

AutoGate **không tự sinh** proxy ma thuật. Nó gộp nhiều đường ra Internet rồi expose qua HAProxy:

```text
Tool / curl
    │  HTTP proxy
    ▼
HAProxy :56789  (round-robin)          ← rotating pool
    ├── warp:1080                      Cloudflare WARP (SOCKS)
    ├── psiphon001:8080                Psiphon (HTTP)
    ├── proxy001:8888                  ProxyBroker (public HTTP)
    └── vpn00..vpn19:8080              VPNGate + OpenVPN + tinyproxy

Worker cố định (không round-robin cả pool):
    127.0.0.1:56800 → vpn00
    127.0.0.1:56801 → vpn01
    ...
```

| Nguồn | Trong AutoGate | Proxy type expose | Ý tưởng tự dùng |
|-------|----------------|-------------------|-----------------|
| **VPNGate** | `ovpn_proxy_XX` | HTTP `:8080` | Tải `.ovpn` → OpenVPN → (tuỳ chọn) tinyproxy |
| **WARP** | service `warp` | SOCKS `:1080` | Docker `caomingjun/warp` hoặc app 1.1.1.1 |
| **Psiphon** | `psiphon001` | HTTP `:8080`, SOCKS `:1080` | ConsoleClient + config JSON |

**Tự connect từng cái** = bỏ HAProxy, nói chuyện thẳng với port local của từng nguồn.

Môi trường gợi ý trong repo này: **Windows 11 + PowerShell + Docker (thường qua WSL2)**.

---

## 2. VPNGate (OpenVPN → HTTP proxy)

### 2.1. Ý tưởng

1. Lấy danh sách server free từ VPNGate.
2. Tải / decode file cấu hình **OpenVPN** (`.ovpn`).
3. Connect OpenVPN → traffic đi qua IP server VPNGate.
4. (Tuỳ chọn) Chạy **HTTP proxy** (tinyproxy) trên tunnel để tool dùng `curl -x http://...`.

Trong repo:

| File | Vai trò |
|------|---------|
| `proxy/vpngate.py` | Tải API, ghi `*.ovpn` vào `/ovpn` |
| `slave/ovpn.sh` | Chọn random 1 file `.ovpn`, chạy `openvpn` |
| `slave/tinyproxy.sh` | Đợi `tun0` có IPv4, bind tinyproxy qua tunnel |
| `slave/tinyproxy.conf` | HTTP proxy listen `:8080` |

### 2.2. Bước 1 — Tải list server

**API chính thức:**

```text
http://www.vpngate.net/api/iphone/
```

PowerShell:

```powershell
Invoke-WebRequest -Uri "http://www.vpngate.net/api/iphone/" -OutFile "vpngate.csv"
```

Hoặc web UI: [https://www.vpngate.net/en/](https://www.vpngate.net/en/) → chọn server → **OpenVPN Config file**.

### 2.3. Bước 2 — Tạo file `.ovpn` từ API

Cột `OpenVPN_ConfigData_Base64` trong CSV là nội dung `.ovpn` đã base64 (cùng logic `proxy/vpngate.py`).

Script Python mẫu (lấy tối đa 3 server US):

```python
import base64
import csv
import urllib.request

url = "http://www.vpngate.net/api/iphone/"
text = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
lines = [
    line[1:] if line.startswith("#") else line
    for line in text.splitlines()
    if line.strip() and not line.startswith("*")
]
rows = list(csv.DictReader(lines))

count = 0
for row in rows:
    if row.get("CountryShort", "").upper() != "US":
        continue
    name = row["HostName"]
    ovpn = base64.b64decode(row["OpenVPN_ConfigData_Base64"]).decode("utf-8")
    with open(f"{name}.ovpn", "w", encoding="utf-8") as f:
        f.write(ovpn)
    print("wrote", name)
    count += 1
    if count >= 3:
        break
```

**Lọc country khác:** đổi `"US"` thành `"JP"`, `"KR"`, `"VN"`, v.v. (mã `CountryShort` 2 chữ).

Repo thường đã có file trong `./ovpn/*.ovpn` (có thể cũ; nếu connect fail hãy tải lại từ API).

### 2.4. Bước 3 — Connect OpenVPN

#### Cách A — OpenVPN GUI trên Windows (đơn giản)

1. Cài [OpenVPN Community / OpenVPN GUI](https://openvpn.net/community-downloads/).
2. Copy file `.ovpn` vào thư mục config (thường `C:\Program Files\OpenVPN\config\`).
3. Chuột phải icon tray OpenVPN → **Connect**.
4. Kiểm tra IP:

```powershell
curl.exe http://ifconfig.me
```

> Khi connect thành công, **toàn bộ traffic PC** đi qua VPN (không cần `-x`), trừ khi bạn chỉ route một phần (policy routing nâng cao).

#### Cách B — Lệnh OpenVPN (Linux / WSL / container)

```bash
sudo openvpn --config my-server.ovpn \
  --data-ciphers "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC"
```

(Cipher list giống `slave/ovpn.sh`.)

Cần quyền `NET_ADMIN` và thiết bị `/dev/net/tun`.

#### Cách C — Docker (gần runtime AutoGate)

```powershell
docker run --rm -it `
  --cap-add=NET_ADMIN `
  --device /dev/net/tun `
  -v "${PWD}/my.ovpn:/vpn.ovpn:ro" `
  --name vpngate-one `
  alpine/openvpn
# hoặc image OpenVPN client bạn quen; entrypoint chạy openvpn --config /vpn.ovpn
```

### 2.5. Bước 4 — Biến tunnel thành HTTP proxy (cho tool dùng `-x`)

Chỉ connect VPN thì browser/curl **mặc định** đã đi VPN. Muốn URL cố định kiểu `http://127.0.0.1:8080`:

1. OpenVPN lên → interface tunnel (`tun0`) có IPv4.
2. Chạy **tinyproxy** (hoặc 3proxy):
   - `Listen` trên interface LAN/container (ví dụ eth0).
   - `Bind` (outgoing) ra IP của `tun0` — đúng logic `slave/tinyproxy.sh`.
3. Publish port ra host, ví dụ `127.0.0.1:18080:8080`.

Dùng:

```powershell
curl.exe -x http://127.0.0.1:18080 http://ifconfig.me
```

**Flow đầy đủ VPNGate → HTTP proxy:**

```text
[VPNGate API] → .ovpn → [OpenVPN / tun0] → [tinyproxy :8080] → tool (-x)
```

### 2.6. Ưu / nhược VPNGate

| Ưu | Nhược |
|----|--------|
| Free, nhiều server/geo | Server public chết nhanh, chậm |
| Dễ lấy `.ovpn` | IP hay bị blacklist |
| Có thể pin country | Cần TUN + quyền admin |

---

## 3. Cloudflare WARP (SOCKS5)

### 3.1. Ý tưởng

WARP là client mạng của Cloudflare. Trong AutoGate:

- Image: `caomingjun/warp`
- Service: `warp` trong `docker-compose.yml`
- HAProxy backend: `server warp warp:1080`
- Persist state: volume `./data` → `/var/lib/cloudflare-warp`

### 3.2. Cách 1 — Docker (khuyến nghị khi cần proxy URL)

```powershell
New-Item -ItemType Directory -Force -Path ".\warp-data" | Out-Null

docker run -d --name my-warp `
  --restart always `
  --cap-add NET_ADMIN `
  --sysctl net.ipv6.conf.all.disable_ipv6=0 `
  --sysctl net.ipv4.conf.all.src_valid_mark=1 `
  -v "${PWD}/warp-data:/var/lib/cloudflare-warp" `
  -p 127.0.0.1:1080:1080 `
  -e WARP_SLEEP=2 `
  caomingjun/warp
```

Đợi khoảng 10–30 giây, test **SOCKS5**:

```powershell
curl.exe -x socks5h://127.0.0.1:1080 http://ifconfig.me
```

> Dùng `socks5h://` (resolve DNS qua proxy) thay vì `socks5://` khi tool hỗ trợ.

**License WARP+ (tuỳ chọn):**

```powershell
docker run -d --name my-warp `
  --cap-add NET_ADMIN `
  --sysctl net.ipv6.conf.all.disable_ipv6=0 `
  --sysctl net.ipv4.conf.all.src_valid_mark=1 `
  -v "${PWD}/warp-data:/var/lib/cloudflare-warp" `
  -p 127.0.0.1:1080:1080 `
  -e WARP_SLEEP=2 `
  -e WARP_LICENSE_KEY=your-key-here `
  caomingjun/warp
```

Tham khảo image: [caomingjun/warp trên Docker Hub](https://hub.docker.com/r/caomingjun/warp).

### 3.3. Cách 2 — App WARP desktop (Windows)

1. Cài [Cloudflare WARP / 1.1.1.1](https://1.1.1.1/).
2. Bật **Connected** → traffic **cả máy** đi qua WARP.
3. Thường **không** có sẵn `socks5://127.0.0.1:1080` cho scraper/tool.

→ Cần proxy URL cố định cho nhiều tool: dùng **Cách 1 Docker**.

### 3.4. Ưu / nhược WARP

| Ưu | Nhược |
|----|--------|
| Setup 1 lệnh Docker | Geo/IP ít đa dạng hơn VPNGate |
| Ổn định hơn public VPN | SOCKS, không phải HTTP (một số tool cần chuyển đổi) |
| IP Cloudflare tương đối “sạch” | Phụ thuộc ToS Cloudflare |

### 3.5. Dừng / xoá container WARP

```powershell
docker stop my-warp
docker rm my-warp
```

---

## 4. Psiphon (HTTP + SOCKS)

### 4.1. Ý tưởng

Psiphon mở tunnel circumvention và expose **local proxy**:

| Protocol | Port mặc định (AutoGate) |
|----------|---------------------------|
| HTTP proxy | `8080` |
| SOCKS proxy | `1080` |

Trong repo:

| File | Vai trò |
|------|---------|
| `psiphon/psiphon.config` | Config chuẩn (channel, sponsor, server list) |
| `psiphon/run.sh` | Build runtime config, pin region/port, start client |
| `PsiphonDockerfile` | Build ConsoleClient |
| `psiphon_data/` | State tunnel (persist) |

Biến môi trường hữu ích:

| Biến | Ý nghĩa | Mặc định |
|------|---------|----------|
| `EGRESS_REGION` | Pin geo (`US`, `JP`, `SG`…) | rỗng = any |
| `HTTP_PORT` | Local HTTP proxy | `8080` |
| `SOCKS_PORT` | Local SOCKS | `1080` |
| `CONFIG_URL` | URL tải config mới | (trong compose có URL fallback) |
| `HEALTHCHECK_URL` | URL test qua proxy | ví dụ `https://ifconfig.io/ip` |

### 4.2. Cách 1 — Docker Compose trong repo (đơn giản)

Psiphon trong compose **không publish port ra host** (chỉ mạng nội bộ `172.21.0.132`). Muốn dùng tay, thêm tạm vào service `psiphon001`:

```yaml
ports:
  - "127.0.0.1:18081:8080"   # HTTP
  - "127.0.0.1:11081:1080"   # SOCKS
```

Rồi:

```powershell
# Từ thư mục gốc AutoGate (Docker/WSL)
docker compose up -d --build psiphon001
```

Test:

```powershell
curl.exe -x http://127.0.0.1:18081 http://ifconfig.me
curl.exe -x socks5h://127.0.0.1:11081 http://ifconfig.me
```

Pin region (tương đương `COUNTRY_FILTER` / `EGRESS_REGION`):

```powershell
# Ví dụ env khi up
$env:COUNTRY_FILTER = "US"
docker compose up -d --build psiphon001
```

### 4.3. Cách 2 — Binary ConsoleClient (nâng cao)

1. Build/lấy **Psiphon ConsoleClient** từ [psiphon-tunnel-core](https://github.com/Psiphon-Labs/psiphon-tunnel-core) hoặc dùng binary trong image `psiphonimg`.
2. Chuẩn bị JSON config (có thể copy `psiphon/psiphon.config` và chỉnh):

```json
{
  "DataRootDirectory": "./psiphon_data",
  "LocalHttpProxyPort": 8080,
  "LocalSocksProxyPort": 1080,
  "ListenInterface": "any",
  "EgressRegion": "US",
  "PropagationChannelId": "...",
  "SponsorId": "...",
  "RemoteServerListURLs": [],
  "RemoteServerListSignaturePublicKey": "...",
  "ServerEntrySignaturePublicKey": "..."
}
```

- `EgressRegion` rỗng = bất kỳ region.
- `"US"`, `"JP"`, `"SG"` = pin egress geo.

3. Chạy:

```text
psiphon -config psiphon.config
```

(Trên Linux image: `/usr/local/bin/psiphon -config /psiphon/data/psiphon.config`.)

4. Đợi tunnel sẵn sàng (vài chục giây đến vài phút lần đầu), rồi:

```powershell
curl.exe -x http://127.0.0.1:8080 https://ifconfig.io/ip
```

### 4.4. Ưu / nhược Psiphon

| Ưu | Nhược |
|----|--------|
| Vượt mạng hạn chế tốt | Build binary / config phức tạp hơn WARP |
| Có cả HTTP + SOCKS | Lần đầu tải server list có thể lâu |
| Pin `EgressRegion` | Phụ thuộc mạng Psiphon public |

---

## 5. So sánh & chọn nhanh

| Nguồn | Độ khó | Ổn định | Proxy type | Khi nào chọn |
|-------|--------|---------|------------|--------------|
| **VPNGate** | Dễ (GUI) | Thấp | Full VPN / + HTTP tinyproxy | Đổi IP free, thử geo, nhiều server |
| **WARP** | Rất dễ (1 Docker) | Cao | SOCKS5 | Một proxy sạch, ổn định |
| **Psiphon** | TB–khó | TB–cao | HTTP + SOCKS | Mạng chặn, cần circumvention |

### Workflow “muốn 1 proxy dùng ngay”

**Chỉ WARP:**

```powershell
docker run -d --name my-warp --cap-add NET_ADMIN `
  --sysctl net.ipv6.conf.all.disable_ipv6=0 `
  --sysctl net.ipv4.conf.all.src_valid_mark=1 `
  -p 127.0.0.1:1080:1080 `
  caomingjun/warp

curl.exe -x socks5h://127.0.0.1:1080 http://ifconfig.me
```

**Chỉ 1 VPNGate:**

1. Tải 1 file `.ovpn` từ API hoặc web.
2. OpenVPN GUI → Connect.
3. `curl.exe http://ifconfig.me` (cả máy qua VPN).

**Chỉ Psiphon:**

1. Publish port `18081:8080` trên `psiphon001`.
2. `docker compose up -d --build psiphon001`.
3. `curl.exe -x http://127.0.0.1:18081 http://ifconfig.me`.

---

## 6. Checklist kiểm tra

```powershell
# IP thật (không proxy)
curl.exe http://ifconfig.me

# HTTP proxy
curl.exe -x http://127.0.0.1:PORT http://ifconfig.me

# SOCKS5 (DNS qua proxy)
curl.exe -x socks5h://127.0.0.1:PORT http://ifconfig.me
```

| Kết quả | Ý nghĩa |
|---------|---------|
| IP qua proxy **khác** IP thật | Connect OK |
| Timeout / connection refused | Service chưa lên hoặc sai port |
| IP giống IP thật khi dùng `-x` | Proxy không forward / bypass |

---

## 7. Chạy song song vài proxy

### 7.1. Qua full AutoGate (có sẵn)

```bat
autogate.bat US 5
```

- Rotating: `http://127.0.0.1:56789`
- Worker cố định: `56800` … `56804`
- UI copy: `http://127.0.0.1:2087`
- Stats: `http://127.0.0.1:2086`

PowerShell song song 5 worker:

```powershell
$proxies = 56800..56804 | ForEach-Object { "http://127.0.0.1:$_" }
$jobs = $proxies | ForEach-Object {
  $p = $_
  Start-Job {
    param($proxy)
    curl.exe -s -x $proxy http://ifconfig.me
  } -ArgumentList $p
}
$jobs | Wait-Job | Receive-Job
$jobs | Remove-Job
```

### 7.2. Tự host 3 nguồn độc lập (ví dụ port)

| Nguồn | URL gợi ý |
|-------|-----------|
| WARP | `socks5h://127.0.0.1:1080` |
| Psiphon HTTP | `http://127.0.0.1:18081` |
| VPNGate + tinyproxy | `http://127.0.0.1:18080` |

Gán **1 URL / 1 thread** trong tool để sticky session theo task.

---

## 8. Ánh xạ với code AutoGate

```text
AutoGate/
├── proxy/
│   ├── vpngate.py          # Tải VPNGate → .ovpn
│   ├── haproxy.cfg         # Gộp warp / psiphon / vpnXX
│   └── run.sh              # HAProxy + refresh vpngate
├── slave/
│   ├── ovpn.sh             # openvpn --config random
│   ├── tinyproxy.sh        # HTTP proxy qua tun0
│   └── watchdog.sh         # Rotate định kỳ (ROTATING_DELAY)
├── psiphon/
│   ├── psiphon.config      # Config chuẩn
│   └── run.sh              # Start ConsoleClient
├── docker-compose.yml      # warp, psiphon001, ovpn_proxy_*, haproxy
└── data/                   # State WARP
```

Backend HAProxy (rút gọn từ `proxy/haproxy.cfg`):

```text
backend vpn
  server warp       warp:1080
  server proxy001   proxy001:8888
  server psiphon001 psiphon001:8080
  server vpn00      vpn00:8080
  ...
  server vpn19      vpn19:8080
```

---

## 9. Troubleshooting

| Triệu chứng | Hướng xử lý |
|-------------|-------------|
| VPNGate: empty / không có `.ovpn` | Kiểm tra truy cập `www.vpngate.net`; chạy lại logic `vpngate.py` hoặc tải web |
| OpenVPN fail ngay | Thử file `.ovpn` khác; server public hay down |
| WARP container restart loop | Cần `NET_ADMIN` + sysctl như compose; xem `docker logs my-warp` |
| `curl -x socks5://...` fail DNS | Đổi sang `socks5h://` |
| Psiphon không ra IP | Đợi health; xem log; thử `HEALTHCHECK_URL`; kiểm tra `EGRESS_REGION` có server không |
| Port đã dùng | Đổi host port map (`1080`, `18081`, …) |
| Docker trên Windows không có TUN | Chạy OpenVPN/WARP/Psiphon **trong WSL2/Linux VM**, không chỉ Hyper-V thiếu TUN |

---

## Phụ lục A — Bảng port tham chiếu

### Tự host (ví dụ tài liệu này)

| Dịch vụ | Host URL |
|---------|----------|
| WARP SOCKS | `socks5h://127.0.0.1:1080` |
| Psiphon HTTP | `http://127.0.0.1:18081` |
| Psiphon SOCKS | `socks5h://127.0.0.1:11081` |
| VPNGate HTTP (tinyproxy) | `http://127.0.0.1:18080` |

### Full AutoGate stack

| Host port | Ý nghĩa |
|-----------|---------|
| `56789` | Rotating HTTP proxy (HAProxy) |
| `2086` | HAProxy stats UI |
| `2087` | Proxy list UI (copy URL) |
| `56800–56819` | Dedicated worker (mỗi worker ~ 1 VPN tunnel) |

---

## Phụ lục B — Lệnh test một dòng

```powershell
# WARP
curl.exe -s -x socks5h://127.0.0.1:1080 http://ifconfig.me

# Psiphon
curl.exe -s -x http://127.0.0.1:18081 http://ifconfig.me

# AutoGate rotating
curl.exe -s -x http://127.0.0.1:56789 http://ifconfig.me

# AutoGate worker 0
curl.exe -s -x http://127.0.0.1:56800 http://ifconfig.me
```

---

## Tài liệu liên quan

- `README.md` — Quick start full stack, ports, `COUNTRY_FILTER`, `PROXY_WORKER_COUNT`
- `docker-compose.yml` — Định nghĩa service `warp`, `psiphon001`, `ovpn_proxy_*`
- [VPNGate](http://www.vpngate.net/)
- [Cloudflare WARP](https://www.cloudflare.com/warp/)
- [Psiphon tunnel core](https://github.com/Psiphon-Labs/psiphon-tunnel-core)

---

*Tài liệu thuộc thư mục `spec/` của project AutoGate. Cập nhật khi thay đổi cổng mặc định hoặc cách expose backend.*
