# artifacts/README.md

각 실행은 `artifacts/BUILD_ID/` 아래에 `images`, `checksums`, `manifests`, `qemu-test`, `rpi5-test`, `camera-test`를 만든다. Hailo 이미지의 카메라 검증은 별도 `camera-hailo-test`에 기록한다. BUILD_ID 형식은 `UTC-git-sha`이며 이미지와 원시 로그는 Git에 추가하지 않는다. 외부 보관소에는 최근 정상 Raspberry Pi 이미지 세 개와 직전 정상 이미지를 유지한다.

Git에는 기본 이미지의 `artifacts/releases/BUILD_ID.json` 또는 Hailo 이미지의 `artifacts/releases/BUILD_ID-rpi5-camera-hailo.json` 형식의 작은 승인 요약만 추가할 수 있다. 요약은 build ID, 프로젝트 SHA, 외부 레이어 SHA, 이미지 SHA-256, 시험 결과, 승인 시각만 포함하고 개인 키·IP·장치 일련번호·원시 journal은 포함하지 않는다. Hailo 요약은 선택한 프로필과 AI 추론이 아직 검증되지 않았다는 상태도 명시한다. 상세 형식은 [증거 스키마](../docs/evidence-schema.md)를 참고한다.
