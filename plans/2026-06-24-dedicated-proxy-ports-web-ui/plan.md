---
title: "Kế hoạch thêm dedicated proxy ports và web UI copy URL"
description: "Giữ rotating proxy 56789, publish 10 worker ports 56800-56809 và thêm web UI nhẹ tại 127.0.0.1:2087."
status: pending
priority: P2
effort: 4h
branch: main
tags: [feature, infra, ui]
created: 2026-06-24
---

# Kế hoạch triển khai

## Mục tiêu
- Giữ proxy xoay vòng tại `56789 -> haproxy:9999`.
- Publish 10 cổng worker local-only `127.0.0.1:56800..56809 -> ovpn_proxy_00..09:8080`.
- Thêm web UI rất nhẹ tại `127.0.0.1:2087`, hiển thị URL proxy copy được và trạng thái chạy hiện tại.
- Không thêm framework nặng; ưu tiên Python stdlib trong image `haproxy`.

## Hiện trạng đã xác minh
- `haproxy` đang publish `2086:10000` và `56789:9999`, đồng thời link tới `ovpn_proxy_00..19` trong cùng network: `docker-compose.yml:6-18`, `docker-compose.yml:19-42`.
- Các worker `ovpn_proxy_00..09` đều dùng image OpenVPN + tinyproxy, lắng nghe `:8080`: `Dockerfile:1-14`, `docker-compose.yml:133-155`, `docker-compose.yml:156-178`, `docker-compose.yml:179-201`, `docker-compose.yml:202-224`, `docker-compose.yml:225-247`, `docker-compose.yml:248-270`, `docker-compose.yml:271-293`, `docker-compose.yml:294-316`, `docker-compose.yml:317-339`, `docker-compose.yml:340-361`.
- HAProxy backend đã có sẵn `vpn00..vpn09` trỏ tới `:8080`, đủ để suy ra health/runtime state mà không cần Docker socket: `proxy/haproxy.cfg:42-59`.
- Image `haproxy` đã cài `python3` và entrypoint hiện tại đã là shell supervisor, nên thêm một stdlib web server vào cùng container là phương án KISS nhất: `HaproxyDockerfile:6-14`, `proxy/run.sh:21-50`.
- README và launcher hiện mới quảng bá `56789` và stats UI `2086`: `README.md:110-116`, `autogate.sh:49-52`.

## Thiết kế chốt

### Data flow
1. Browser mở `http://127.0.0.1:2087`.
2. Web UI trong container `haproxy` đọc HAProxy stats nội bộ tại `http://127.0.0.1:10000/` hoặc `;csv` để lấy state cho `vpn00..vpn09`: `proxy/haproxy.cfg:23-35`, `proxy/haproxy.cfg:42-59`.
3. UI map `vpn00..vpn09` thành `http://127.0.0.1:56800..56809`, cộng thêm `http://127.0.0.1:56789`.
4. UI render HTML tĩnh + nút copy; không lưu state, không cần DB, không cần API ngoài process.

### Backwards compatibility
- Không đụng backend rotation logic, không đổi HAProxy round-robin path: `proxy/haproxy.cfg:37-69`.
- `56789` giữ nguyên để không phá caller hiện có.
- 10 cổng worker và `2087` là additive-only.
- Không có migration dữ liệu.

## Phases

### Phase 1: Publish dedicated ports
- Owner file: `docker-compose.yml`.
- Sửa `haproxy` để publish `127.0.0.1:2087:2087`.
- Sửa `ovpn_proxy_00..09` để publish lần lượt `127.0.0.1:56800:8080` ... `127.0.0.1:56809:8080`.
- Dependency: không blocker kỹ thuật; phase này phải xong trước smoke test E2E.
- Risk: Medium x High. Sai host binding có thể lộ port ra `0.0.0.0` hoặc trùng port host.
- Mitigation: luôn dùng prefix `127.0.0.1:`; verify bằng `docker compose config` trước khi `up`.
- Success: compose render đúng 11 port map mới; stack khởi động không conflict.
- Rollback: bỏ các dòng `ports` mới, recreate containers.

### Phase 2: Thêm web UI nhẹ trong image `haproxy`
- Owner files: `HaproxyDockerfile`, `proxy/run.sh`, `proxy/proxy-links-ui.py` `[NEW]`.
- Tạo script Python stdlib phục vụ HTML, parse HAProxy stats, đánh dấu `UP/DOWN/UNKNOWN`, và trả ra URL copyable.
- `run.sh` khởi chạy HAProxy trước, sau đó khởi chạy/giám sát process UI riêng; lỗi UI không được kéo HAProxy xuống.
- Dependency: cần chốt mapping `vpn00..09 -> 56800..56809`; không phụ thuộc thay đổi backend config.
- Risk: High x Medium. Supervisor logic sai có thể làm container restart loop hoặc che lỗi HAProxy.
- Mitigation: giữ nguyên path start HAProxy hiện có; bọc UI bằng `ensure_web_ui`; nếu parse stats fail thì UI vẫn render URL với trạng thái `UNKNOWN`.
- Success: `curl http://127.0.0.1:2087/` trả HTML có `56789`, `56800`, `56809`; kill một worker vẫn thấy UI phản ánh trạng thái thay vì 500.
- Rollback: bỏ port `2087`, xoá script UI khỏi image và `run.sh`, rebuild `haproxy`.

### Phase 3: Cập nhật docs và launcher
- Owner files: `README.md`, `autogate.sh`, `autogate.bat` nếu muốn echo nhanh URL UI trên Windows.
- Thêm bảng port mới, hướng dẫn mở UI/copy URL, và ví dụ test bằng `curl -x`.
- Dependency: phase 1-2 hoàn tất để docs khớp thực tế.
- Risk: Low x Low. Lệch docs với config.
- Mitigation: copy literal mapping từ compose vào README/script output.
- Success: docs và startup output nhắc đủ `56789`, `56800..56809`, `2086`, `2087`.
- Rollback: revert text/script output, không ảnh hưởng runtime.

## Files likely to modify
- `docker-compose.yml:6-18`, `docker-compose.yml:133-361` — thêm host port mapping cho `haproxy` và `ovpn_proxy_00..09`.
- `HaproxyDockerfile:1-14` — copy script UI vào image, expose port UI nếu cần.
- `proxy/run.sh:5-50` — supervise thêm process web UI.
- `README.md:110-116`, `README.md:160-162`, `README.md:205-221` — cập nhật port table, scale note, cấu trúc thư mục.
- `autogate.sh:49-52` — in thêm UI URL / dedicated port hint.
- `autogate.bat:43-52` — optional text parity cho Windows launcher.

## Test matrix
- Unit: nếu tách parser trong `proxy/proxy-links-ui.py`, test parse stats row -> URL row, fallback `UNKNOWN`, HTML escaping.
- Integration: `docker compose config`; `docker compose build haproxy`; `curl http://127.0.0.1:2087/`; xác nhận UI đọc được stats nội bộ.
- E2E: `curl -x http://127.0.0.1:56789 http://ifconfig.me/ip`; `curl -x http://127.0.0.1:56800 http://ifconfig.me/ip`; mở UI trong browser và dùng copy button.
- Failure drills: stop `ovpn_proxy_03`; UI vẫn load và hiển thị `56803` là `DOWN` hoặc `UNKNOWN`; rotating proxy vẫn không bị ảnh hưởng.

## Verification steps
1. `docker compose config`
2. `docker compose up -d --build haproxy ovpn_proxy_00 ovpn_proxy_01 ovpn_proxy_02 ovpn_proxy_03 ovpn_proxy_04 ovpn_proxy_05 ovpn_proxy_06 ovpn_proxy_07 ovpn_proxy_08 ovpn_proxy_09`
3. `curl http://127.0.0.1:2087/`
4. `curl -x http://127.0.0.1:56789 http://ifconfig.me/ip`
5. `curl -x http://127.0.0.1:56800 http://ifconfig.me/ip`
6. `curl -x http://127.0.0.1:56809 http://ifconfig.me/ip`
7. `docker compose ps`

## Notes
- Khuyến nghị không pin lại `56789`/`2086` sang `127.0.0.1` trong cùng thay đổi này để tránh breaking change ngoài mong muốn, vì compose hiện publish rộng hơn docs: `docker-compose.yml:14-16`, `README.md:114-115`.
- Nếu muốn harden cả `56789`/`2086`, tách thành follow-up nhỏ sau khi UI ổn định.
