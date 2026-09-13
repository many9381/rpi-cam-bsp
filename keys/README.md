# keys/README.md

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
