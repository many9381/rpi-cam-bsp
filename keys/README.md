# keys/README.md

배포용 로그인 키는 로컬에서 다음 명령으로 생성한다.

```bash
ssh-keygen -t ed25519 -f keys/rpi5_admin -C rpi5-admin
chmod 600 keys/rpi5_admin
chmod 644 keys/rpi5_admin.pub
```

빌드는 `keys/rpi5_admin.pub`를 이미지에 주입하고, QEMU·실기기 시험은 `keys/rpi5_admin`을 사용한다. 두 파일 모두 Git에 추가하지 않는다. 공개키가 없거나 `ssh-keygen -l -f keys/rpi5_admin.pub` 검증에 실패하면 빌드 전 점검을 실패시킨다.
