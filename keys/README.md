# keys/README.md

카메라 이미지 빌드는 `keys/camera-firmware/`에 무결성 서명 키와 `device.json`을
한 번 생성한다. `integrity-private.pem`은 `0600`, 디렉토리는 `0700`이며,
공개키 `integrity-public.pem`만 BitBake에 전달한다. 개인키를 따로 백업하고
이미지 재설치 때 임의로 교체하지 않는다. 이 디렉토리 전체는 Git 제외 대상이다.

`device.json`의 `public_host` 초깃값은 `null`이다. Pi의 DHCP 주소를 미리 알거나
유선·Wi-Fi 중 하나를 고정하지 않아도 실제 HTTPS 접속 주소로 초기 설정할 수 있다.
고정 DNS 이름이나 별도 공개 주소를 쓰는 경우에만 IP 또는 DNS 이름을 지정한다.
설치 스크립트는
장비별 인증서와 SRTP 키를 생성하고 바이너리·최종 설정·부팅 커널을 서명한다.
개인 서명 키는 SSD에 넣지 않는다. 최초 관리자 등록은 웹에서 한 번 진행한다.
[앱 자동 초기 설정](../docs/runbooks/camera-firmware.md#device-provisioning)을 참고한다.

`null`인 경우 초기 TLS 인증서는 자체 서명된 `camera.local` 이름을 가진다.
DNS/mDNS 등록을 자동 제공하는 것은 아니며, IP로 접속할 때 인증서 신뢰와 이름
불일치 경고를 별도로 확인해야 한다. 신뢰할 수 있는 고정 DNS와 그 이름에 맞는
인증서를 사용하면 DHCP 주소 변경에 영향받지 않고 인증서 검증을 유지할 수 있다.

배포용 로그인 키는 로컬에서 다음 명령으로 생성한다.

```bash
ssh-keygen -t ed25519 -f keys/rpi5_admin -C rpi5-admin
chmod 600 keys/rpi5_admin
chmod 644 keys/rpi5_admin.pub
```

빌드는 `keys/rpi5_admin.pub`를 이미지에 주입하고, QEMU·실기기 시험은 `keys/rpi5_admin`을 사용한다. 두 파일 모두 Git에 추가하지 않는다. 공개키가 없거나 `ssh-keygen -l -f keys/rpi5_admin.pub` 검증에 실패하면 빌드 전 점검을 실패시킨다.

선택적 Wi-Fi 접속 정보는 이 체크아웃의 `keys/wifi.json`에만 저장하고 권한을
`0600`으로 제한한다. 이 파일도 Git 제외 대상이다. 실제 AP 이름과 PSK를 레시피나
문서에 기록하지 않는다. 파일 형식과 이미지 취급 주의사항은
[Wi-Fi 자동 접속 절차](../docs/runbooks/wifi.md)를 참고한다.

카메라 이미지의 SSD 설치 스크립트는 `sudo`를 호출한 사용자의 현재
`~/.codex/auth.json`을 읽어, 이미지 기록 후 SSD에만 로그인 정보를 복원한다.
인증 파일은 사용자 소유·권한 `0600`이어야 하며 이미지·빌드 캐시·Git에 넣지 않는다.
SSH 수동 복원에서 사용하는 `keys/codex-auth.json`도 Git 제외 대상이다.
자동 복원의 옵션과 동작은 [Codex 인증 절차](../docs/runbooks/codex.md)를 참고한다.

반복 설치 대상 SSD는 `keys/ssd-target.json`에 한 번 등록한다. USB SSD의
`vendor`, `model`, `serial` 문자열과 바이트 단위 정수 `size_bytes`를 저장하며,
이 파일도 Git에서 제외한다. `scripts/install-ssd.sh`는 이 정보로 장치명 변경을
추적하고 최신 완료 이미지를 자동 설치한다. 매번 스크립트를 생성하거나 이미지
경로·체크섬을 수정할 필요가 없다. 등록 및 실행 방법은
[자동 SSD 설치 절차](../docs/runbooks/usb-ssd-bringup.md#automatic-development-installation)를 참고한다.
