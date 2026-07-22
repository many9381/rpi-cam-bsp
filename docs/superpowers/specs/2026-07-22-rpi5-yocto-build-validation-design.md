# Raspberry Pi 5 Yocto 이미지 빌드·검증 기획서

- 문서 상태: 설계 승인, 구현 전
- 기준일: 2026-07-22
- 대상 릴리스: Yocto Project 6.0 LTS `wrynose`
- 대상 보드: Raspberry Pi 5, 64-bit
- 빌드 호스트: x86_64 Ubuntu 24.04.4 LTS
- 1단계 부팅 매체: USB-to-SSD
- 2단계 카메라: Raspberry Pi Camera Module 3 Wide (`IMX708`)

## 1. 목적

이 문서는 빈 Git 저장소에서 Raspberry Pi 5용 Yocto 이미지를 재현 가능하게 크로스 빌드하고, QEMU 사전 시험과 Raspberry Pi 5 실기기 시험을 거쳐 배포 가능한 산출물을 만드는 전체 작업을 정의한다.

개발은 두 단계로 진행한다.

1. 최소 부팅 이미지
   - USB SSD 부팅
   - systemd
   - 유선 Ethernet DHCP
   - SSH 공개키 인증
   - 원격 상태 점검과 연속 3회 재부팅 검증
2. 헤드리스 카메라 이미지
   - 최소 부팅 이미지 상속
   - Camera Module 3 Wide 활성화
   - `libcamera`/`rpicam-apps` 기반 정지영상·영상 촬영
   - SSH를 통한 원격 시험과 결과 회수

QEMU는 Raspberry Pi 5 하드웨어를 대체하지 않는다. 동일한 ARM64 사용자 공간 이미지 구성을 `qemuarm64`에서 먼저 검사하고, Raspberry Pi 전용 부트 체인과 주변장치는 실기기에서 최종 판정한다.

## 2. 확정된 결정 사항

| 항목 | 결정 |
|---|---|
| Yocto 릴리스 | `wrynose` 6.0 LTS |
| 빌드 오케스트레이션 | 호스트 설치형 `kas` 우선, CI에서 `kas-container` 추가 |
| 소스 재현성 | 호환 브랜치와 40자리 Git SHA를 모두 고정 |
| Raspberry Pi 머신 | `raspberrypi5` |
| QEMU 머신 | `qemuarm64` |
| 1단계 이미지 | 최소 부팅, 유선 DHCP, SSH, 원격 진단 |
| 2단계 이미지 | Camera Module 3 Wide용 헤드리스 카메라 기능 추가 |
| 저장장치 | microSD가 아닌 USB-to-SSD로 정상 부팅 |
| 초기 네트워크 | 유선 Ethernet와 DHCP |
| 관리 경로 | SSH 공개키 인증을 기본 경로로 사용 |
| 로컬 콘솔 | 원격 부팅 탐색 실패 시에만 HDMI와 USB 키보드 사용 |
| UART | 장비가 없으므로 검증·복구 경로에서 제외 |
| QEMU 범위 | 공통 ARM64 사용자 공간과 서비스만 검증 |
| 실기기 합격 조건 | USB SSD 부팅, DHCP, SSH, SSD 루트 확인, 연속 3회 재부팅 성공 |

## 3. 범위

### 3.1 포함 범위

- Yocto 6.0 호스트 요구사항 확인
- `kas` 매니페스트와 잠금 정책
- 프로젝트 전용 `meta-rpi5-cam` 레이어
- 최소 이미지와 카메라 이미지 분리
- QEMU용 `qemuarm64` 빌드와 자동 스모크 시험
- Raspberry Pi 5용 Wic 이미지 생성
- 안전한 USB SSD 기록 절차
- EEPROM USB 부팅 사전 점검과 비상 복구
- Ethernet DHCP와 SSH 키 기반 원격 접속
- 실기기 3회 재부팅 시험
- Camera Module 3 Wide 감지와 촬영 시험
- 빌드·시험 증적 및 정상 이미지 보관
- 후속 CI 컨테이너화 방향

### 3.2 제외 범위

- Wi-Fi 프로비저닝
- Wayland/Weston 또는 데스크톱 GUI
- OTA 업데이트와 A/B 파티션
- Secure Boot와 디스크 암호화
- 양산 키 관리 및 장치별 인증서 발급
- 실시간 네트워크 영상 스트리밍
- Raspberry Pi 5 하드웨어의 완전한 QEMU 에뮬레이션
- USB SSD 전체 용량을 자동 확장하는 첫 부팅 파티션 변경

루트 파일시스템 자동 확장은 부팅 안정화와 분리한다. 1단계에서는 고정 크기 Wic 루트 파티션으로 합격 판정을 끝내고, 전체 SSD 용량 사용은 별도 저장장치 기능 변경으로 추가한다.

## 4. 핵심 제약과 설계 원칙

### 4.1 Yocto 6.0 소스 구조

Yocto 6.0부터 신규 릴리스는 과거의 통합 `poky` 저장소를 사용하지 않는다. `bitbake`, `openembedded-core`, `meta-yocto`를 별도 저장소로 체크아웃한다. `meta-openembedded`와 `meta-raspberrypi`도 같은 릴리스 계열로 맞춘다.

따라서 `kas`가 다음 저장소를 조합한다.

- BitBake
- OpenEmbedded-Core
- `meta-poky`를 제공하는 `meta-yocto`
- `meta-oe`, `meta-python`, `meta-multimedia`를 제공하는 `meta-openembedded`
- Raspberry Pi BSP를 제공하는 `meta-raspberrypi`
- 이 저장소 자체의 `meta-rpi5-cam`

### 4.2 QEMU와 실기기 분리

QEMU의 공식 Raspberry Pi 머신 모델은 Raspberry Pi 5를 포함하지 않는다. 다음 경계를 유지한다.

| QEMU에서 검증 | 실기기에서만 검증 |
|---|---|
| AArch64 사용자 공간 | EEPROM 부트 순서 |
| systemd 기동 | Raspberry Pi 펌웨어와 Device Tree |
| 사용자·SSH 설정 | RP1과 실제 Ethernet 컨트롤러 |
| 기본 네트워크 서비스 | USB-to-SSD 브리지와 전원 안정성 |
| 파일시스템 쓰기 | Camera Module 3 Wide와 `IMX708` |

QEMU 실패 시 Raspberry Pi 이미지를 SSD에 기록하지 않는다. QEMU 통과는 필요조건이며 실기기 합격을 대신하지 않는다.

### 4.3 무-UART 운용

정상 경로는 전원 인가부터 원격 SSH까지 로컬 입력 없이 진행한다. 초기 커널 패닉처럼 네트워크 이전에 발생한 문제는 UART 로그를 얻을 수 없으므로 다음 보완책을 사용한다.

- 정상 이미지의 커널 로그를 영구 journal에 저장
- DHCP, mDNS, ping, SSH를 시간 제한과 함께 순차 탐색
- 실패할 때만 HDMI와 키보드 연결
- 알려진 정상 Wic 이미지로 롤백
- EEPROM 문제일 때만 임시 microSD 복구 이미지 사용

## 5. 현재 빌드 호스트 평가

2026-07-22에 확인한 현재 호스트는 다음과 같다.

| 항목 | 현재 값 | Yocto 6.0 기준 | 판정 |
|---|---:|---:|---|
| CPU 아키텍처 | x86_64 | 지원 호스트 아키텍처 | 적합 |
| OS | Ubuntu 24.04.4 LTS | 공식 지원 배포판 | 적합 |
| 논리 CPU | 16 | 4코어 이상 권장 | 적합 |
| 물리 메모리 | 35 GiB | 최소 32 GiB | 적합 |
| Swap | 8 GiB | 빌드 피크 완충 | 적합 |
| 작업 볼륨 여유 공간 | 227 GiB | 최소 140 GB | 적합 |

두 머신의 빌드를 함께 유지하면 140 GB보다 더 많은 공간이 필요할 수 있다. 다음 정책으로 공간을 관리한다.

- `DL_DIR`과 `SSTATE_DIR`은 QEMU와 Raspberry Pi 빌드가 공유한다.
- 각 머신은 별도 `TMPDIR`을 사용한다.
- 성공한 배포 산출물과 로그를 보존한 뒤 오래된 `tmp/work`를 정리한다.
- 디스크 잔여 공간이 20 GB 아래로 내려가면 새 빌드를 시작하지 않는다.
- BitBake의 디스크 모니터링은 10 GB에서 작업 중지, 5 GB에서 즉시 중단하도록 구성한다.

Ubuntu 호스트에는 Yocto 공식 필수 패키지에 `python3-venv`, `bmap-tools`, `qemu-system-arm`, `openssh-client`, `avahi-utils`를 추가한다. `kas`는 프로젝트 가상환경에 `kas==5.4`로 고정한다.

## 6. 소스 버전과 업데이트 정책

초기 구현은 2026-07-22에 조회한 다음 커밋 세트로 시작한다.

| 저장소 | 브랜치 | 초기 고정 SHA |
|---|---|---|
| `bitbake` | `2.18` | `fae9db3168dbff1b8c76fe9c6726a9687ff97514` |
| `openembedded-core` | `wrynose` | `b5a6cada82d7ffb362bda9081c354dcc0b6ee264` |
| `meta-yocto` | `wrynose` | `824795b885b25e074a2880fbcd54e1a6c875d47d` |
| `meta-openembedded` | `wrynose` | `d97b5602d7f64422c94b7311466cda7f6b1962d5` |
| `meta-raspberrypi` | `wrynose` | `f62c67921474370829d24a4fa01ef88543f3906b` |

이 세트는 첫 파싱·빌드·QEMU·실기기 시험을 모두 통과한 뒤 검증 기준선이 된다. `kas` 잠금 파일에도 같은 SHA를 기록한다.

업데이트는 다음 규칙을 따른다.

1. 브랜치 tip을 빌드 때마다 자동 추적하지 않는다.
2. 한 변경에서 전체 레이어의 호환성을 함께 평가한다.
3. 새 SHA 세트로 QEMU와 Raspberry Pi 시험을 모두 다시 실행한다.
4. 합격한 변경만 잠금 파일과 정상 이미지 기준선을 갱신한다.
5. 기존 잠금 파일은 롤백이 가능하도록 Git 이력에 남긴다.

## 7. 저장소와 구성 아키텍처

```text
yocto-rpi5-cam-firmware/
├── kas/
│   ├── base.yml
│   ├── lock.yml
│   ├── qemuarm64-minimal.yml
│   ├── rpi5-minimal.yml
│   └── rpi5-camera.yml
├── meta-rpi5-cam/
│   ├── conf/layer.conf
│   ├── recipes-core/images/
│   │   ├── rpi5-minimal-image.bb
│   │   └── rpi5-camera-image.bb
│   └── recipes-core/device-config/
│       ├── device-config.bb
│       └── files/
│           ├── 20-wired.network
│           ├── sshd_config.d-rpi5.conf
│           └── rpi5-admin-sudoers
├── keys/
│   └── README.md
├── scripts/
│   ├── host-preflight.sh
│   ├── build.sh
│   ├── flash-ssd.sh
│   ├── discover-rpi5.sh
│   ├── test-qemu.sh
│   ├── test-rpi5.sh
│   └── test-camera.sh
├── tests/
│   ├── host/
│   └── oeqa/
├── artifacts/
│   └── README.md
└── docs/
    └── superpowers/
        ├── specs/
        └── plans/
```

### 7.1 `kas/base.yml`

- 분리된 Yocto 저장소 URL, 브랜치와 SHA를 선언한다.
- `meta`, `meta-poky`, 프로젝트 로컬 레이어를 공통으로 활성화한다.
- 다운로드와 sstate 캐시 위치를 공통 지정한다.
- `DISTRO = "poky"`, `INIT_MANAGER = "systemd"`를 명시한다.
- 라이선스 매니페스트와 빌드 정보 생성을 활성화한다.
- 사용자별 비밀정보나 SSH 키 경로는 저장하지 않는다.

### 7.2 머신별 `kas` 구성

`qemuarm64-minimal.yml`:

- `base.yml`을 포함한다.
- `MACHINE = "qemuarm64"`를 사용한다.
- Raspberry Pi BSP 레이어를 활성화하지 않는다.
- `rpi5-minimal-image`의 공통 사용자 공간을 빌드한다.
- 빌드 디렉터리는 `build/qemuarm64`로 분리한다.

`rpi5-minimal.yml`:

- `base.yml`을 포함한다.
- `meta-raspberrypi`를 활성화한다.
- `MACHINE = "raspberrypi5"`를 사용한다.
- `BOOT_MEDIA = "usb"`를 사용한다.
- 1단계에서는 단일 SSD만 연결한다는 조건으로 `CMDLINE_ROOT_PARTITION = "/dev/sda2"`를 사용한다.
- Wic 이미지와 bmap 파일을 함께 생성한다.
- 빌드 디렉터리는 `build/raspberrypi5-minimal`로 분리한다.

`rpi5-camera.yml`:

- `rpi5-minimal.yml`을 포함한다.
- `meta-multimedia`의 선언된 의존성에 따라 `meta-oe`, `meta-python`, `meta-multimedia`를 함께 활성화한다.
- `RASPBERRYPI_CAMERA_V3 = "1"`을 설정한다.
- Raspberry Pi 5의 소프트웨어 H.264 인코딩을 위해 `libcamera-apps`의 `libav` 기능과 `rpidistro-ffmpeg`의 `x264` 기능을 활성화한다.
- 카메라 개발 이미지에 한해 `commercial` 라이선스 플래그를 명시적으로 허용한다.
- 외부 배포 전 GPL 소스 제공 의무와 제품 라이선스 정책을 검토한다.
- 타깃을 `rpi5-camera-image`로 교체한다.
- 빌드 디렉터리는 `build/raspberrypi5-camera`로 분리한다.

### 7.3 이미지 경계

`rpi5-minimal-image`는 하드웨어에 종속되지 않는 사용자 공간을 정의한다.

- systemd와 systemd-networkd
- 유선 DHCP
- OpenSSH 서버
- SSH 키 전용 관리 계정
- `sudo`, `iproute2`, `util-linux`, `procps`, `ethtool`
- 영구 journal
- 빌드 식별 정보

`rpi5-camera-image`는 최소 이미지에 다음만 추가한다.

- `libcamera-apps` 레시피가 제공하는 `rpicam-*` 명령
- `libcamera` 런타임
- `v4l-utils`와 분리 패키지 `media-ctl`
- `libav`와 `libx264` 기반 소프트웨어 H.264 인코딩
- IMX708 Device Tree overlay
- 원격 카메라 검증 스크립트가 요구하는 파일 형식 검사 도구

GUI, Qt, OpenCV, TensorFlow Lite, GStreamer 스트리밍 스택은 초기 카메라 이미지에 포함하지 않는다.

## 8. 1단계 실행 흐름

### 8.1 호스트 준비

호스트 준비 스크립트는 다음을 검사하고 결과를 종료 코드로 반환한다.

- x86_64와 지원 Ubuntu 버전
- CPU, RAM, Swap, 디스크 공간
- `en_US.UTF-8` locale
- Git, Python, tar, make, gcc 최소 버전
- 필수 패키지와 `bmaptool`, QEMU, SSH 클라이언트
- 현재 사용자의 빌드 디렉터리 쓰기 권한
- BitBake를 root로 실행하지 않는지 여부
- SSH 공개키 파일 존재와 올바른 공개키 형식

기본 명령 흐름은 다음과 같다.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'kas==5.4'
./scripts/host-preflight.sh
```

### 8.2 소스와 메타데이터 검증

```bash
kas checkout kas/qemuarm64-minimal.yml
kas shell kas/qemuarm64-minimal.yml -c 'bitbake-layers show-layers'
kas shell kas/qemuarm64-minimal.yml -c 'bitbake -p'
kas shell kas/rpi5-minimal.yml -c 'bitbake-layers show-layers'
kas shell kas/rpi5-minimal.yml -c 'bitbake -p'
```

이 단계의 합격 조건은 다음과 같다.

- 모든 저장소가 잠금 파일의 SHA와 일치한다.
- 모든 레이어가 `wrynose` 또는 BitBake 2.18과 호환된다.
- 중복 레시피와 치명적인 BitBake 경고가 없다.
- 두 구성 모두 전체 메타데이터를 파싱한다.

### 8.3 이미지 빌드

```bash
kas build kas/qemuarm64-minimal.yml
kas build kas/rpi5-minimal.yml
```

QEMU 이미지를 먼저 빌드한다. 이 빌드가 실패하면 Raspberry Pi 이미지 빌드와 SSD 기록을 진행하지 않는다.

각 성공 빌드는 다음 정보를 남긴다.

- 프로젝트 Git SHA
- 모든 외부 레이어 SHA
- BitBake와 kas 버전
- 이미지 패키지 목록
- 라이선스 매니페스트
- 빌드 로그
- 산출물 SHA-256

### 8.4 QEMU 시험

QEMU는 root 권한이 필요하지 않은 user-mode 네트워크를 기본으로 한다.

```bash
kas shell kas/qemuarm64-minimal.yml -c 'runqemu qemuarm64 nographic slirp'
```

`test-qemu.sh`는 별도 프로세스로 QEMU를 시작하고 제한 시간 안에 다음을 자동 확인한다.

1. 커널이 부팅되고 systemd multi-user target에 도달한다.
2. `uname -m` 결과가 `aarch64`이다.
3. systemd 상태가 `running`이다.
4. 유선 네트워크 구성 서비스와 SSH 서비스가 active이다.
5. SSH 비밀번호 인증과 root 로그인이 거부된다.
6. `rpiadmin` 공개키 인증이 성공한다.
7. 루트 파일시스템에 임시 파일을 쓰고 읽고 삭제할 수 있다.
8. 정상 종료 후 QEMU 프로세스와 임시 네트워크 자원이 남지 않는다.

QEMU 시작 제한 시간은 180초로 한다. 실패 시 콘솔 로그, systemd 실패 유닛, QEMU 실행 명령을 증적으로 보관한다.

### 8.5 Raspberry Pi 산출물 승인

SSD 기록 대상으로 승격하려면 다음 파일이 모두 존재해야 한다.

- Raspberry Pi 5 Wic 이미지 또는 압축 Wic 이미지
- 대응하는 `.wic.bmap`
- SHA-256 체크섬 파일
- 패키지와 라이선스 매니페스트
- 외부 레이어 SHA 목록
- 성공한 QEMU 시험 결과

QEMU 결과가 없거나 이미지와 체크섬의 빌드 ID가 다르면 기록을 금지한다.

## 9. USB SSD 기록 설계

`flash-ssd.sh`는 전체 블록 장치를 덮어쓰므로 안전장치를 필수로 한다.

### 9.1 대상 장치 판별

스크립트는 기록 전에 다음 정보를 표시한다.

- 장치 경로
- 제조사와 모델
- 일련번호
- 전송 방식
- 전체 용량
- 파티션과 마운트 위치

다음 조건에서는 즉시 중단한다.

- 대상이 파티션 경로이다.
- 대상 또는 하위 파티션이 현재 `/`, `/boot`, `/home`, 작업 디렉터리를 포함한다.
- 전송 방식이 USB가 아니다.
- 대상 용량이 이미지보다 작다.
- 대상 장치가 두 개 이상으로 모호하다.
- 명령행에 전체 장치 경로와 확인 문구가 함께 제공되지 않았다.

장치명 `/dev/sdX` 자체는 신뢰하지 않는다. `lsblk`의 부모 관계와 루트 장치 비교로 시스템 디스크 여부를 판정한다.

### 9.2 기록과 사후 확인

1. 대상 파티션을 정상 unmount한다.
2. Wic 체크섬을 먼저 검증한다.
3. `bmaptool copy`로 이미지와 bmap을 사용해 기록한다.
4. 커널에 파티션 테이블을 다시 읽힌다.
5. 부트 파티션을 읽기 전용으로 열어 커널, Device Tree, `config.txt`, 부트 명령행을 확인한다.
6. 루트 파티션의 파일시스템 형식을 확인한다.
7. 기록 장치 모델·일련번호·이미지 SHA·기록 시각을 로그에 남긴다.
8. SSD를 안전하게 분리한다.

기록 스크립트는 `dd`를 자동 대체 경로로 사용하지 않는다. `bmaptool` 실패 원인을 해결한 뒤 다시 실행한다.

## 10. Raspberry Pi 5 USB 부팅 준비

### 10.1 하드웨어 조건

- Raspberry Pi 5
- 품질이 확인된 USB-to-SATA 또는 USB-to-NVMe 브리지와 SSD
- 유선 Ethernet 연결
- 동일 LAN의 x86 빌드 호스트
- 5V/5A 27W급 전원 어댑터 또는 별도 전원형 SSD 인클로저
- 비상 점검용 micro-HDMI 모니터와 USB 키보드
- EEPROM 복구에만 사용할 수 있는 임시 microSD

Raspberry Pi 5는 3A 전원 사용 시 USB 주변장치 전류가 600mA로 제한된다. USB SSD 부팅 안정성을 위해 5A 전원에서 제공되는 더 높은 주변장치 전류 여유를 사용한다.

### 10.2 부팅 순서

정상 시험은 microSD를 제거한 상태로 수행한다. EEPROM `BOOT_ORDER`에 USB-MSD 값 `4`가 포함되어야 한다.

USB SSD가 부팅되지 않을 때만 다음 비상 경로를 사용한다.

1. HDMI 부트로더 진단 화면과 LED 패턴을 확인한다.
2. SSD 브리지·케이블·USB 포트·전원 조합을 확인한다.
3. 다른 Linux 호스트에서 SSD가 USB mass-storage 장치로 안정적으로 동작하는지 확인한다.
4. 임시 microSD의 Raspberry Pi Bootloader Recovery 이미지로 EEPROM을 갱신한다.
5. USB-MSD가 포함된 부팅 순서를 적용한 뒤 microSD를 제거한다.
6. 같은 Wic SSD로 다시 시험한다.

USB Attached SCSI 동작에서만 불안정한 브리지는 다른 검증된 브리지로 교체하는 것을 우선한다. 커널 quirk는 하드웨어 교체가 불가능할 때만 적용한다.

## 11. 원격 실기기 검증

### 11.1 접속 보안

- 계정명은 `rpiadmin`으로 고정한다.
- 패스워드는 잠근다.
- SSH `PasswordAuthentication`과 `PermitRootLogin`을 비활성화한다.
- 공개키는 `keys/rpi5_admin.pub`에서 빌드 시 주입하며 해당 파일은 Git 추적에서 제외한다.
- 키 파일이 없으면 이미지 빌드를 실패시킨다.
- `rpiadmin`에는 상태 조회와 재부팅에 필요한 제한된 `sudo` 명령만 허용한다.
- 개발용 `debug-tweaks`, 빈 root 비밀번호, 공용 기본 비밀번호를 사용하지 않는다.

### 11.2 원격 탐색

호스트명은 `rpi5-minimal`로 한다. 전원 인가 후 다음 순서로 최대 5분 동안 탐색한다.

1. `rpi5-minimal.local` mDNS 조회
2. 이전 DHCP 주소에 ping
3. 공유기 또는 지정 DHCP 조회 방식으로 MAC/IP 확인
4. SSH 호스트 키 응답 확인
5. `rpiadmin` 공개키 인증

첫 부팅은 180초, 이후 재부팅은 각 120초 안에 SSH가 복구되어야 한다. 5분 안에 어떤 네트워크 신호도 없을 때만 HDMI와 키보드를 연결한다.

### 11.3 1단계 합격 시험

`test-rpi5.sh`는 다음을 기록하고 판정한다.

1. SSH 공개키 인증 성공
2. `uname -m`이 `aarch64`
3. `/proc/device-tree/model`이 Raspberry Pi 5
4. systemd 전체 상태가 `running`
5. Ethernet 링크가 올라오고 DHCP 주소가 존재
6. 기본 경로가 유선 인터페이스를 사용
7. `/`의 원본 블록 장치가 USB SSD의 두 번째 파티션
8. microSD 장치가 루트 또는 부트 소스로 사용되지 않음
9. 루트 파일시스템 읽기·쓰기 성공
10. 패스워드 SSH와 root SSH 거부
11. 현재 boot ID 저장

그다음 원격 재부팅을 세 번 수행한다. 각 회차마다 다음 조건을 만족해야 한다.

- 120초 이내 SSH 복구
- 직전과 다른 boot ID
- 같은 USB SSD에서 루트 마운트
- systemd 상태 `running`
- DHCP와 기본 경로 정상

세 회차 중 하나라도 실패하면 1단계는 불합격이다. HDMI 보조 점검 결과로 자동 합격 판정을 덮어쓰지 않는다.

## 12. 2단계 Camera Module 3 Wide 확장

### 12.1 진입 조건

2단계는 동일 레이어 잠금 세트로 1단계 QEMU 및 Raspberry Pi 시험이 모두 통과한 뒤 시작한다. 카메라는 Raspberry Pi 전원을 완전히 끈 상태에서 올바른 CAM 커넥터에 연결한다.

### 12.2 빌드 구성

`rpi5-camera.yml`은 다음 차이만 추가한다.

- `meta-openembedded`의 `meta-oe`, `meta-python`, `meta-multimedia` 활성화
- `RASPBERRYPI_CAMERA_V3 = "1"`
- `libcamera-apps`, `libcamera`, `v4l-utils`, `media-ctl` 설치
- `PACKAGECONFIG:append:pn-libcamera-apps = " libav"`
- `PACKAGECONFIG:append:pn-rpidistro-ffmpeg = " x264"`
- 개발 이미지 범위에서 `LICENSE_FLAGS_ACCEPTED += " commercial"`
- 이미지 이름과 호스트명을 카메라 변형으로 구분

`meta-raspberrypi`의 `RASPBERRYPI_CAMERA_V3` 설정은 부트 파티션에 `dtoverlay=imx708`을 추가한다. Camera Module 3 Wide는 일반 Module 3과 같은 IMX708 드라이버를 사용하며 렌즈 특성은 센서 모드와 튜닝 데이터로 처리한다.

`wrynose`의 `libcamera-apps` 레시피는 `rpicam-*` 실행 파일을 제공하며 기본 DRM 지원으로 구성된다. 시험에서는 화면 미리보기를 사용하지 않고 `--nopreview`를 지정한다. Raspberry Pi 5에는 H.264 하드웨어 인코더가 없으므로 `libav`와 `libx264`를 명시적으로 사용한다.

`rpidistro-ffmpeg`는 `commercial` 라이선스 플래그와 GPL 계열 구성 요소를 포함한다. 개발 이미지에서의 사용은 명시적으로 기록하고, 이미지를 외부 배포하기 전 소스 제공 의무와 제품 라이선스 정책을 별도 검토한다.

### 12.3 카메라 합격 시험

`test-camera.sh`는 SSH를 통해 다음을 실행한다.

```bash
rpicam-hello --list-cameras
rpicam-still --nopreview --autofocus-mode auto --timeout 2s --output /var/tmp/camera3-wide.jpg
rpicam-vid --nopreview --timeout 10s --width 1920 --height 1080 --framerate 30 --codec libav --libav-format h264 --libav-video-codec libx264 --output /var/tmp/camera3-wide.h264
```

합격 조건은 다음과 같다.

1. 커널 로그와 media graph에서 IMX708을 확인한다.
2. `rpicam-hello --list-cameras`에 IMX708과 센서 모드가 표시된다.
3. 자동초점 정지영상 촬영 명령이 성공한다.
4. JPEG 파일이 비어 있지 않고 JPEG 형식으로 판별된다.
5. 10초 H.264 촬영 명령이 성공한다.
6. 영상 파일이 비어 있지 않고 H.264 비트스트림으로 판별된다.
7. 두 파일의 SHA-256을 기록하고 SCP로 호스트에 회수한다.
8. 재부팅 후 IMX708 감지와 정지영상 촬영을 다시 통과한다.

카메라 시험은 QEMU에서 실행하지 않는다. QEMU 카메라 이미지 빌드는 의존성 파싱과 패키징 확인에만 활용할 수 있으며 하드웨어 합격 증적으로 인정하지 않는다.

## 13. 장애 처리와 복구

| 증상 | 1차 조치 | 다음 조치 |
|---|---|---|
| `kas checkout` 실패 | 네트워크·프록시·저장소 URL 확인 | 깨진 부분 checkout을 재사용하지 않고 동일 SHA로 재시도 |
| BitBake 파싱 실패 | 레이어 SHA와 `LAYERSERIES_COMPAT` 확인 | 잠금 세트 전체의 호환성 재검토 |
| QEMU 부팅 실패 | 콘솔 로그와 systemd 실패 유닛 수집 | Raspberry Pi 이미지 기록 중단 |
| SSD 대상 판별 실패 | `lsblk` 정보와 연결 장치 수 확인 | 사용자가 장치를 분리·재연결한 뒤 처음부터 재검증 |
| Pi 전원 반응 없음 | 27W 전원, 케이블, SSD 소비전류 확인 | 별도 전원형 인클로저 또는 검증된 브리지 사용 |
| 부트 파일을 못 찾음 | microSD 제거, SSD 부트 파티션 확인 | EEPROM USB-MSD 순서 복구 |
| 커널 이후 네트워크 없음 | Ethernet 링크와 DHCP 서버 확인 | HDMI 로그인 후 networkd와 journal 수집 |
| SSH만 실패 | 시간 동기화, 계정·키·sshd 상태 확인 | HDMI에서 공개키와 sshd 설정 검증 |
| 재부팅 후 복귀 실패 | 이전 boot journal과 SSD 오류 확인 | 정상 이미지로 SSD 재기록 |
| IMX708 미감지 | 전원 차단 후 FFC 방향과 CAM 포트 확인 | overlay, 커널 로그, media graph 확인 |
| 촬영 실패 | `rpicam-hello --list-cameras`와 버전 기록 | 튜닝 데이터, 메모리, 전원 상태 확인 |

모든 실패는 다음 정보를 함께 보존한다.

- 빌드 ID와 이미지 SHA
- 외부 레이어 SHA
- QEMU 콘솔 또는 SSH 명령 로그
- 실기기 boot ID
- `journalctl -b`와 직전 부팅 journal
- `dmesg`, `lsblk`, `findmnt`, `networkctl`
- 카메라 시험에서는 `rpicam-hello --version`과 센서 목록

## 14. 산출물과 증적 관리

빌드 ID는 UTC 빌드 시각과 프로젝트 Git short SHA의 조합으로 만든다. 각 빌드는 `artifacts` 아래에 다음 구조로 보관한다.

```text
artifacts/
└── build-id/
    ├── images/
    ├── checksums/
    ├── manifests/
    ├── layer-revisions.txt
    ├── qemu-test/
    ├── rpi5-test/
    └── camera-test/
```

대용량 이미지와 로그는 Git에 커밋하지 않는다. Git에는 매니페스트, 잠금 파일, 스크립트, 시험 정의, 릴리스별 체크섬과 결과 요약만 남긴다.

최소 세 개의 최근 정상 Raspberry Pi 이미지를 보관한다. 새 기준선 승격 후에도 직전 정상 이미지를 삭제하지 않는다.

## 15. 단계별 마일스톤과 종료 조건

### M0. 저장소 골격과 재현성

산출물:

- `kas` 구성과 잠금 파일
- 프로젝트 레이어 골격
- 호스트 사전 점검
- `.gitignore`와 키 관리 설명

종료 조건:

- 새 checkout에서 두 머신의 메타데이터 파싱 성공
- 모든 외부 저장소 SHA가 잠금 파일과 일치

### M1. 공통 최소 이미지와 QEMU

산출물:

- `rpi5-minimal-image`
- qemuarm64 빌드
- 자동 QEMU 스모크 시험

종료 조건:

- QEMU의 8개 합격 항목 통과
- 시험 로그와 이미지 체크섬 생성

### M2. Raspberry Pi 5 USB SSD 이미지

산출물:

- Raspberry Pi 5 Wic와 bmap
- 안전한 SSD 기록 스크립트
- EEPROM/USB 부팅 점검 절차

종료 조건:

- SSD 기록 사후 확인 성공
- microSD 없이 Raspberry Pi 5 부팅

### M3. 원격 실기기 안정화

산출물:

- DHCP/mDNS 탐색
- SSH 보안 설정
- 실기기 자동 시험

종료 조건:

- USB SSD, DHCP, SSH, systemd 검사 통과
- 연속 3회 재부팅과 원격 복귀 성공

### M4. Camera Module 3 Wide

산출물:

- `rpi5-camera-image`
- IMX708 overlay 설정
- 원격 정지영상·영상 시험

종료 조건:

- IMX708 감지, 자동초점 JPEG, 10초 H.264 촬영 성공
- 재부팅 후 재감지와 재촬영 성공

### M5. CI 재현성

산출물:

- 버전과 digest가 고정된 `kas-container` CI 환경
- 파싱, QEMU 빌드·시험, Pi 이미지 빌드 파이프라인
- 승인된 산출물과 체크섬 게시

종료 조건:

- 깨끗한 CI runner에서 동일 잠금 파일로 반복 빌드 성공
- 일반 CI runner는 블록 장치 기록 권한을 갖지 않음
- 실기기 시험은 전용 하드웨어 runner 또는 수동 승인 단계로 분리

## 16. 주요 위험과 완화책

| 위험 | 영향 | 완화책 |
|---|---|---|
| `wrynose` 안정 브랜치 이동 | 동일 설정에서 산출물 변경 | 전체 Git SHA와 kas 버전 고정 |
| 통합 `poky` 저장소 사용 | Yocto 6.0 소스 누락 | 분리된 BitBake/OE-Core/meta-yocto 사용 |
| Raspberry Pi 5 QEMU 부재 | BSP 오류를 가상 시험에서 놓침 | QEMU와 실기기 시험의 역할을 명시적으로 분리 |
| USB SSD 전력 부족 | 간헐 부팅·파일시스템 오류 | 27W 전원 또는 별도 전원형 인클로저 |
| USB-SATA/NVMe 브리지 비호환 | EEPROM 또는 Linux 단계 부팅 실패 | 검증된 브리지 사용, UAS 문제 시 교체 우선 |
| UART 부재 | 초기 부팅 장애 가시성 저하 | 원격 탐색, 영구 journal, HDMI 비상 경로, 정상 이미지 롤백 |
| SSD 장치 오인 | 호스트 데이터 손실 | 시스템 디스크 검사와 이중 확인, bmaptool 전용 기록 |
| DHCP 주소 변경 | SSH 자동화 실패 | mDNS 우선, DHCP 조회 대체, 고정 hostname |
| SSH 키 누락 | 원격 관리 불가 | 키가 없으면 빌드 실패, 비밀번호 우회 금지 |
| IMX708 케이블·overlay 오류 | 카메라 미감지 | 전원 차단 연결 절차와 명시적 V3 설정 |
| 카메라 사용자 공간 불일치 | 촬영 명령 실패 | 레이어 잠금과 실제 `rpicam-*` 버전 증적 |
| H.264 소프트웨어 인코딩 부하 | 프레임 드롭 또는 발열 | 1080p30 기준 시험, libx264 명시, 온도와 CPU 사용률 기록 |
| H.264/GPL 라이선스 의무 | 외부 배포 지연 | 개발 이미지 허용 범위 기록, 출시 전 라이선스 검토 |

## 17. 최종 완료 정의

프로젝트의 1단계는 다음 조건을 모두 만족할 때 완료된다.

- 빈 작업 공간에서 잠금된 소스로 재현 빌드 가능
- qemuarm64 스모크 시험 통과
- Raspberry Pi 5용 Wic와 bmap, 체크섬 생성
- 안전장치가 있는 스크립트로 USB SSD 기록
- microSD 없이 Raspberry Pi 5 부팅
- 유선 DHCP와 SSH 공개키 접속 성공
- 루트 파일시스템이 USB SSD에 존재
- 연속 3회 재부팅 후 원격 접속과 상태 검사 성공
- 모든 빌드·시험 증적 보존

2단계는 1단계를 계속 만족하면서 다음 조건을 추가로 충족할 때 완료된다.

- Camera Module 3 Wide의 IMX708 감지
- 자동초점 JPEG 촬영 및 호스트 회수
- 10초 H.264 촬영 및 호스트 회수
- 카메라 시험 후 재부팅과 재촬영 성공
- GUI 없이 SSH만으로 전체 카메라 검증 가능

## 18. 공식 참고 자료

- [Yocto Project 6.0 시스템 요구사항](https://docs.yoctoproject.org/6.0/ref-manual/system-requirements.html)
- [Yocto Project 6.0 Quick Build와 분리 저장소 구성](https://docs.yoctoproject.org/6.0/brief-yoctoprojectqs/index.html)
- [Yocto Project 릴리스 현황](https://wiki.yoctoproject.org/wiki/Releases)
- [kas 사용자 가이드](https://kas.readthedocs.io/en/latest/userguide.html)
- [meta-raspberrypi wrynose 브랜치](https://github.com/agherzan/meta-raspberrypi/tree/wrynose)
- [Raspberry Pi 5 머신 정의](https://github.com/agherzan/meta-raspberrypi/blob/wrynose/conf/machine/raspberrypi5.conf)
- [meta-raspberrypi USB 부팅·카메라 설정](https://github.com/agherzan/meta-raspberrypi/blob/wrynose/docs/extra-build-config.md)
- [Yocto bmaptool 이미지 기록](https://docs.yoctoproject.org/dev/dev-manual/bmaptool.html)
- [QEMU Raspberry Pi 머신 지원 범위](https://www.qemu.org/docs/master/system/arm/raspi.html)
- [Raspberry Pi USB mass-storage 부팅](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#usb-mass-storage-boot)
- [Raspberry Pi EEPROM `BOOT_ORDER`](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_ORDER)
- [Raspberry Pi 카메라 소프트웨어와 `rpicam-apps`](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [Raspberry Pi 5 계열 H.264 인코딩 성능 자료](https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-010033-WP-1-H.264%20encoding%20performance%20on%20Raspberry%20Pi%205_series%20computers.pdf)
