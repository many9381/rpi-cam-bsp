# Raspberry Pi 5 Wi-Fi 자동 접속

`rpi5-minimal`, `rpi5-camera`, `rpi5-camera-hailo` 이미지에는 Pi 5 내장
Wi-Fi용 드라이버, BCM43455 펌웨어, 서명된 regulatory DB,
`wpa_supplicant`, `iw`, `rfkill`을 포함한다. QEMU는 기존 유선 구성을 유지한다.

## 로컬 접속 정보

**빌드하는 체크아웃의** `keys/wifi.json`을 로컬 편집기로 작성하고
`chmod 600 keys/wifi.json`을 실행한다. 필드는 아래 세 개만 사용한다.
값은 예시이며 실제 접속 정보로 교체한다.

```json
{
  "ssid": "YOUR_AP_NAME",
  "psk": "YOUR_64_HEX_CHARACTER_PSK",
  "country": "KR"
}
```

SSID는 UTF-8 기준 1~32바이트, PSK는 **정확히 64자리 16진수 원시 키**다.
8~63자리 일반 비밀번호가 아니므로 `wpa_passphrase`에 다시 입력하지 않는다.
국가 코드는 실제 사용 국가의 두 자리 코드다. 한국은 `KR`이며 소문자 입력도
대문자로 정규화한다. WPA2-PSK AP용이며 WPA3-only/기업용 802.1X는 지원하지 않는다.

`keys/*`는 기존 Git 제외 규칙으로 보호한다. 다음 명령은 내용 없이 제외 여부만 확인한다.

```bash
git check-ignore keys/wifi.json
stat -c '%a %n' keys/wifi.json
```

레시피, kas YAML, 환경 변수, 커밋 메시지, 테스트, 터미널 명령 인자에 실제 SSID나
PSK를 복사하지 않는다. `git add -f keys/wifi.json`도 사용하지 않는다.
다른 경로가 필요하면 BitBake 설정의 `RPI5_WIFI_CONFIG_FILE`에 공백·콜론·glob 문자
(`*`, `?`, `[`, `]`)가 없는 절대 경로만 지정한다. 파일 크기는 최대 4096바이트다.
설정 파일이 없으면 자동 접속은 비활성화되며 유선 접속은 계속 사용할 수 있다.
존재하지만 형식·권한이 잘못된 파일은 빌드를 실패시킨다.

## 이미지 생성과 보안 범위

`rpi5-wifi` 패키지는 공용 서비스·DHCP 정책만 설치한다. 접속 정보는
`rpi5-wifi-provision.bbclass`가 `do_rootfs` 후처리에서 읽어
`/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`에 root 소유, `0600`으로 설치한다.
상위 디렉토리는 `0700`이다. PSK는 따옴표 없는 원시 키로, SSID는 설정 구문에
영향을 주지 않는 16진수로 기록한다. 16진수 인코딩은 암호화가 아니다.

접속 정보는 `SRC_URI`나 패키지 작업에 전달하지 않으므로 레시피 RPM과 패키지
sstate에는 들어가지 않는다. 로컬 파일의 생성·수정·삭제는 rootfs 작업 서명에 반영된다.
설정을 지우고 재빌드하면 생성된 접속 설정도 제거된다. 이미 기록된 SSD는 새 이미지를
기록하거나 장치에서 설정을 변경하기 전까지 바뀌지 않는다.

**최종 이미지/WIC와 작업 rootfs에는 PSK가 평문으로 들어간다.** 해당 이미지,
백업, SSD는 비밀 자료로 보관하고 공개 배포하지 않는다. root/sudo 권한자는 읽을 수 있다.
장치 로그나 네트워크 진단 결과에는 AP 이름이 나타날 수 있으므로 원본 로그도
공개하지 않는다. Git 제외는 암호화나 접근 통제가 아니며, 별도 이미지 캐시·배포 서버를
사용한다면 그 저장소에도 접근 제어가 필요하다.

기존 빌드 이미지는 자동으로 갱신되지 않는다. 변경을 커밋한 뒤 새 build ID로
[빌드 환경 준비](build-qemu.md) → 최소 이미지 빌드 →
[새 이미지에 대한 SSD 기록 확인](usb-ssd-bringup.md) 순서를 따른다.
QEMU 검증은 선택 사항이다. 정식 카메라 이미지 설치·검수에는 동일 build ID의 최소 이미지 실기기 검증을 유지한다.

## BCM43455 인증 호환성

`rpi5-wifi`는 `/etc/modprobe.d/rpi5-wifi.conf`에
`options brcmfmac feature_disable=0x2000`을 설치한다. 고정된 Raspberry Pi
6.18 드라이버의 `BRCMF_FEAT_FWSUP`(bit 13)만 비활성화해 WPA 인증을
`wpa_supplicant`에서 처리한다. 암호화 방식과 로컬 PSK는 그대로 유지한다.

2026-10-11 실기기 조사에서 설정 파일·서비스·장치 인식은 정상이었지만,
AP association 직후 10초마다 인증 시간 초과와 `CONN_FAILED`가 반복됐다.
`wpa_supplicant 2.11`과 펌웨어 인증 위임 시 완료 통지를 보내지 않는
`brcmfmac` 조합의 [업스트림 보고](https://lists.infradead.org/pipermail/hostap/2024-August/042893.html)와
일치하며, 고정된 드라이버 코드에서도 PSK 연결 완료 시 해당 통지가 빠져 있다.
`iw phy phy0 info`에는 station PSK/802.1X 인증 위임 기능이 활성화돼 있었다.

이 설정은 모듈을 처음 로드할 때 적용되므로 새 이미지를 설치하고 재부팅해야 한다.
재부팅 후 `iw phy phy0 info`에 `4WAY_HANDSHAKE_STA_PSK`와
`4WAY_HANDSHAKE_STA_1X`가 없어야 한다. `4WAY_HANDSHAKE_AP_PSK`는 별개다.
커널을 갱신할 때 bit 위치와 인증 완료 통지 수정을 확인한 후 우회 설정 유지 여부를
검토한다. 드라이버·펌웨어 파일 존재 검사만으로 실제 접속 성공을 판정하지 않는다.

## 부팅 및 확인

빌드 호스트에서는 `bitbake -c rootfs rpi5-minimal-image` 완료 후
`python tests/host/verify_wifi_rootfs.py <생성된-rootfs-경로>`로 필수 커널 모듈,
펌웨어, 서비스 활성화 링크와 비밀 설정 권한을 확인할 수 있다. 특히 커널 6.18의
`brcmfmac-wcc`/`brcmfmac-cyw` 모듈은 동적 로딩 대상이라 명시적으로 포함한다.
이 검사는 무선 연결 실기기 시험을 대체하지 않는다.

`wlan0` 장치가 나타날 때 서비스가 시작하며, 설정이 없으면 건너뛴다.
AP가 없더라도 부팅 완료를 기다리게 하지 않는다. 무선 DHCP/IPv6 경로는 기존
유선 경로보다 낮은 우선순위를 사용한다. 서비스는 Wi-Fi 소프트 차단을 해제하고
연결 실패 시 `wpa_supplicant`의 재접속 동작을 유지한다.

SSH 또는 로컬 콘솔에서 다음을 확인한다. 출력은 공개 저장소에 커밋하지 않는다.

```bash
systemctl status rpi5-wifi.service --no-pager
networkctl status wlan0
ip -brief address show wlan0
ip route
iw reg get
# 아래 두 명령은 root 권한이 필요하다. 기본 rpiadmin sudo 허용 목록에는 없다.
sudo wpa_cli -i wlan0 status
sudo stat -c '%U:%G %a' /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

실기기에서 association, DHCP, 재부팅 후 재접속을 확인해야 자동 접속 검증이 완료된다.
5 GHz AP는 국가 규제와 AP 채널 설정에 영향을 받는다. 실패하면 유선 SSH를 유지한 채
`rfkill list`, `journalctl -u rpi5-wifi.service`, 커널의 `brcmfmac` 로그를 확인한다.

기본 `rpiadmin` 계정의 읽기 전용 진단은 허용된 `sudo journalctl -b --no-pager`로
부팅 로그를 확인한다. `rpi5-wifi.service`의 `active` 상태뿐 아니라
`CTRL-EVENT-CONNECTED`, `wlan0`의 DHCP 주소, 재부팅 후 재접속을 함께 확인한다.
