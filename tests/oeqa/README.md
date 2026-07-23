# tests/oeqa/README.md

Yocto 6.0 `testimage`의 QEMU 대상은 `allow-empty-password`, `empty-root-password`, `allow-root-login`을 요구한다. 이 프로젝트의 공개키 전용 `rpiadmin` 및 root 로그인 금지 정책과 양립하지 않으므로 해당 기능을 이미지에 추가하지 않는다.

QEMU 런타임 합격 판정은 localhost SLIRP SSH를 사용하는 `scripts/test-qemu.sh`가 담당한다. 이 디렉터리는 보안상 의도된 선택을 기록하며 OEQA 런타임 모듈을 활성화하지 않는다.
