# 01. 패키지 관리 아키텍처 및 저장소 관리

## 🎯 학습 목표 (Goal)
- Linux 저수준 패키지 관리자(`dpkg`)와 고수준 의존성 해결 도구(`apt`)의 계층적 동작 원리를 이해합니다.
- 프로덕션 환경에서 뜻하지 않은 패키지 업데이트로 인한 장애를 방지하는 **버전 고정(`apt-mark hold`)**, 최신 보안 표준인 **GPG 키링(`signed-by`) 기반 저장소 격리**, 그리고 **패키지 잠금 파일(`lock-frontend`) 충돌 해소 기법**을 실습합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. DPKG와 APT의 계층 아키텍처
Debian 및 Ubuntu 계열 Linux 시스템의 패키지 관리는 2단계 계층 구조로 이루어져 있습니다:

```text
+--------------------------------------------------------------+
|                   APT (apt / apt-get)                        |
| - 원격 저장소(Repository) 인덱스 동기화 (/var/lib/apt/lists/)  |
| - 의존성 그래프(Dependency Graph) 분석 및 자동 다운로드         |
+--------------------------------------------------------------+
                               | (의존성 패키지 다운로드 완료 후 호출)
                               v
+--------------------------------------------------------------+
|                         DPKG                                 |
| - 로컬 .deb 아카이브 압축 해제 및 파일시스템 배치              |
| - 설치/삭제 스크립트(preinst, postinst, prerm, postrm) 실행    |
| - 시스템 패키지 데이터베이스 갱신 (/var/lib/dpkg/status)      |
+--------------------------------------------------------------+
```

- **`dpkg`**: 로컬 `.deb` 파일 하나를 설치하거나 삭제하는 도구입니다. 원격 서버에서 파일을 다운로드하거나 누락된 라이브러리(의존성)를 찾아주는 기능이 없습니다.
- **`apt`**: 설정된 저장소 URL(`/etc/apt/sources.list`)에서 패키지 목록을 내려받아 의존성 트리를 계산하고, 필요한 모든 `.deb` 파일을 순서대로 다운로드한 뒤 내부적으로 `dpkg`를 호출하여 설치합니다.

### 2. 현대적인 저장소 보안: GPG 키링(Keyring) 분리
과거에는 `apt-key add` 명령을 통해 모든 저장소의 공개키를 전역 신뢰 파일(`/etc/apt/trusted.gpg`)에 등록했습니다. 이는 한 저장소의 키로 다른 저장소의 패키지 위변조를 검증할 수 있는 보안 취약점이 있었습니다.

현대 표준(Debian 11+, Ubuntu 22.04+)에서는 키를 반드시 격리합니다:
1. GPG 공개키를 `/etc/apt/keyrings/<name>.gpg` 파일로 독립 저장합니다.
2. 저장소 정의 시 `[signed-by=/etc/apt/keyrings/<name>.gpg]` 속성을 부여하여, **오직 해당 저장소의 패키지만 그 키로 검증**하도록 강제합니다.

### 3. 프로덕션 패키지 운영 핵심 패턴
- **버전 고정 (`apt-mark hold <package>`)**: OS 정기 업데이트나 `apt upgrade` 실행 시, 데이터베이스나 런타임 라이브러리가 예기치 않게 메이저 업데이트되어 호환성이 깨지는 사태를 원천 차단합니다.
- **잠금 파일 충돌 (`Could not get lock /var/lib/dpkg/lock-frontend`)**: 백그라운드 자동 업데이트(`unattended-upgrades`)가 작동 중일 때 발생합니다. `fuser`나 `lsof`로 점유 중인 프로세스를 찾아 안전하게 대기하거나 종료해야 합니다.
- **패키지 캐시 청소 (`apt clean`, `apt autoremove`)**: 다운로드된 `.deb` 아카이브 파일(`/var/cache/apt/archives/`)과 불필요해진 고아 라이브러리를 정리하여 루트 디스크 용량을 수 GB 이상 확보합니다.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 파일 출처 역추적 및 설치 파일 목록 조회 (dpkg)
시스템의 특정 실행 파일이 어떤 패키지에 의해 설치되었는지 역추적합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. curl 실행 파일이 어느 패키지에서 생성된 것인지 역추적
dpkg -S $(which curl)

# 2. curl 패키지가 시스템에 설치한 모든 파일 및 디렉터리 목록 조회
dpkg -L curl
```

*출력 예시:*
```text
curl: /usr/bin/curl
/.
/usr
/usr/bin
/usr/bin/curl
/usr/share
/usr/share/doc
/usr/share/doc/curl
...
```

### Step 2. 프로덕션 패키지 버전 고정 (apt-mark hold)
운영 중인 서비스의 핵심 패키지가 `apt upgrade`로 인해 임의 갱신되지 않도록 고정합니다.

```bash
# 1. curl 패키지 버전 고정 설정
apt-mark hold curl

# 2. 현재 버전이 고정(hold)된 패키지 목록 확인
apt-mark showhold

# 3. 고정 해제 (추후 계획된 점검 시 사용)
apt-mark unhold curl
```

### Step 3. 현대적 표준 GPG 키링을 적용한 저장소 추가
외부 공식 저장소(예: HashiCorp 또는 Docker 등)를 추가할 때 사용하는 표준 `signed-by` 방식을 실습합니다.

```bash
# 1. 키링 전용 디렉터리 생성 (보안 권한 0755)
mkdir -p -m 0755 /etc/apt/keyrings

# 2. 예시: 공식 GPG 공개키를 다운로드하여 바이너리 키링으로 변환 저장
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 3. signed-by 옵션을 명시한 sources.list.d 파일 생성
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" | tee /etc/apt/sources.list.d/docker.list

# 4. 저장소 인덱스 갱신 (에러 없이 서명이 검증되는지 확인)
apt-get update
```

### Step 4. 패키지 잠금 파일(Lock) 충돌 진단 및 해결
`apt`나 `dpkg` 실행 시 종종 마주치는 `Could not get lock` 오류를 진단하고 안전하게 해결합니다.

```bash
# 1. dpkg 프론트엔드 잠금 파일을 점유하고 있는 프로세스 PID 확인
fuser /var/lib/dpkg/lock-frontend

# 또는 lsof를 사용한 추적
lsof /var/lib/dpkg/lock-frontend
```

만약 프로세스가 정상적인 백그라운드 설치 중이라면 완료될 때까지 기다리는 것이 원칙이며, 프로세스가 비정상 종료되어 잔여 락 파일만 남은 경우에는 점유 프로세스가 완전히 종료된 것을 확인한 후 수동 조치합니다:
```bash
# 프로세스가 종료되었음에도 남아있는 손상 상태 복구
dpkg --configure -a
apt-get install -f
```

### Step 5. 패키지 아카이브 캐시 및 불필요 라이브러리 정리
컨테이너 빌드나 운영 서버의 디스크 사용량을 최적화합니다.

```bash
# 1. /var/cache/apt/archives/ 에 보관된 모든 다운로드 deb 파일 삭제
apt-get clean

# 2. 다른 패키지의 의존성으로 설치되었으나 지금은 불필요해진 고아 라이브러리 삭제
apt-get autoremove --purge -y

# 3. 디스크 절약 효과 확인
du -sh /var/cache/apt/archives
```

---

## 🎯 마무리 및 다음 단계

리눅스 패키지 시스템의 저수준(dpkg)과 고수준(apt) 분리 구조를 이해하고, 버전 고정(`apt-mark hold`), 최신 키링 격리, 락 파일 충돌 해결, 디스크 캐시 관리 기법을 정립했습니다.

다음 단계인 **[02-process-and-signals.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/02-process-and-signals.md)**에서는 커널의 **프로세스 생명주기, 상태 코드(R, S, D, Z)**와 시스템 시그널(`SIGTERM`, `SIGKILL`)의 동작 원리를 파악하고 좀비 프로세스를 추적하여 회수하는 방법을 실습합니다.
