# 🐧 Linux 시스템 엔지니어링 및 커널 진단 마스터 가이드

현업 백엔드 및 인프라 엔지니어를 위한 실전 Linux 진단, 트러블슈팅, 성능 분석 종합 학습 가이드북 및 실습 랩(Lab)입니다.

단순한 명령어 문법 암기를 넘어, **"시스템이 왜 느려졌는가?", "어느 계층(CPU, 메모리, I/O, 네트워크)에서 병목이 발생하는가?", "장애 상황을 어떻게 빠르게 격리하고 복구할 것인가?"** 에 대한 체계적인 엔지니어링 방법론을 도커(Docker) 기반 격리 환경에서 실습합니다.

---

## 💡 왜 시스템 레벨의 Linux 엔지니어링인가?

1. **지표 뒤에 숨겨진 커널 내부 동작 이해**: 로드 애버리지(Load Average), 메모리 버퍼/캐시(Buffer/Cache), 파일 디스크립터(File Descriptor), TCP 상태 머신(TIME_WAIT, CLOSE_WAIT)의 실체를 명확히 이해합니다.
2. **프로덕션 장애 시뮬레이션 환경 제공**: CPU 스파이크, OOM(Out of Memory) 킬러 작동, Inode 고갈, 열린 채 삭제된 파일로 인한 디스크 풀, 소켓 누수 등 실제 운영 환경에서 빈번한 시스템 인시던트를 직접 재현하고 진단합니다.
3. **가상 컴퓨터 및 컨테이너 샌드박스**: 로컬 개발 머신에 영향을 주지 않고 최신 Ubuntu 24.04 기반 Docker Compose 환경에서 안전하게 커널 파라미터 및 시스템 콜을 실습할 수 있습니다.
4. **견고한 패키지 및 의존성 라이프사이클 관리**: DPKG와 APT의 분리 아키텍처, 프로덕션 배포 시 의도치 않은 라이브러리 판올림을 방지하는 버전 고정(`apt-mark hold`), 최신 표준 GPG 키링 격리(`signed-by`) 및 잠금 파일 충돌 해결 원리를 체계화합니다.

---

## 📂 프로젝트 구조

```text
.
├── README.md                                  // 프로젝트 소개, 시작 가이드, 전체 학습 목차 플래너
├── CHEATSHEET.md                              // 핵심 진단 명령어 및 옵션 요약 치트시트
├── docker-compose.yml                         // 실습용 멀티 컨테이너 환경 정의
├── docs/                                      // 단계별 실습 가이드 문서
│   ├── 00-environment-setup.md                // 00. Docker 기반 진단 랩 환경 구축 및 툴체인
│   ├── 01-package-management.md               // 01. 패키지 관리 아키텍처 및 저장소(Repository) 관리
│   ├── 02-process-and-signals.md              // 02. 프로세스 생명주기 및 시그널(Signal) 제어
│   ├── 03-cpu-analysis.md                     // 03. CPU 병목 및 로드 애버리지(Load Average) 진단
│   ├── 04-memory-and-oom.md                   // 04. 가상 메모리 아키텍처 및 OOM Killer 분석
│   ├── 05-disk-io-and-filesystems.md          // 05. 스토리지 I/O 및 파일시스템 트러블슈팅
│   ├── 06-network-troubleshooting.md          // 06. 네트워크 스택, 소켓 상태 및 패킷 캡처
│   ├── 07-dns-and-http-diagnostics.md         // 07. DNS 조회 및 L7 애플리케이션 지연 진단
│   ├── 08-systemd-and-journalctl.md           // 08. 서비스 관리와 구조화된 시스템 로그 분석
│   ├── 09-system-calls-and-strace.md          // 09. 시스템 콜(Syscall) 추적과 프로세스 디버깅
│   ├── 10-linux-security-and-permissions.md   // 10. 권한 격리, Capabilities 및 파일 보안
│   ├── 11-linux-namespaces-and-cgroups.md     // 11. 컨테이너 내부 원리(Namespace & cgroups v2)
│   ├── 12-kernel-parameters-and-tuning.md     // 12. 커널 파라미터(sysctl) 및 리소스 한도(ulimit)
│   └── 13-production-troubleshooting-playbook.md // 13. [종합 실전] 프로덕션 복합 장애 대응 플레이북
└── examples/                                  // 실습 데모 코드 및 시나리오 재현 도구
    ├── basic-app/                             // 리눅스 기본 진단 도구 및 부하 생성 스크립트 모음
    │   ├── Dockerfile
    │   └── scripts/
    │       ├── check_tools.sh                 // 15대 필수 시스템 진단 도구 검증기
    │       ├── network_latency_benchmark.sh   // L7 레이턴시 구간 정밀 분해 계측기
    │       ├── simulate_fd_leak.py            // 파일 디스크립터 누수 시뮬레이터
    │       └── simulate_zombie.py             // 좀비 프로세스 생성 시뮬레이터
    └── final-project/                         // 실전 장애 시뮬레이션 웹 애플리케이션
        ├── pyproject.toml                     // Poetry 기반 의존성 정의
        ├── poetry.lock
        ├── Dockerfile
        └── app/                               // 의도적 장애(Memory Leak, FD Leak, Slow Socket) 주입 API
```

---

## 🚀 시작하기 (Getting Started)

### 1. 사전 요구사항 확인
시스템에 다음 도구들이 설치되어 있는지 확인합니다.

```bash
# Docker 및 Docker Compose 버전 확인 (Docker v24+, Compose v2+ 권장)
docker --version
docker compose version

# Python 및 Poetry 버전 확인 (Python 3.11+, Poetry 1.8+ 권장)
python3 --version
poetry --version
```

### 2. 실습 프로젝트 클론 및 디렉터리 이동

```bash
cd learning-linux
```

### 3. 실습 컨테이너 환경 구동

모든 실습은 격리된 Ubuntu 24.04 컨테이너에서 수행되므로 호스트 시스템에 영향을 주지 않습니다.

```bash
# 실습 컨테이너 클러스터 빌드 및 백그라운드 구동
docker compose up -d --build

# 실행 중인 컨테이너 상태 확인
docker compose ps

# 메인 분석 실습 서버(linux-lab) 쉘 접속
docker compose exec linux-lab bash
```

---

## 📚 학습 목차 (커리큘럼 플래너)

학습 단계는 **기초 환경 및 리소스 진단**, **심층 시스템 및 네트워크 분석**, **커널/컨테이너 아키텍처 및 실전 인시던트 플레이북**의 3개 영역으로 구성되어 있습니다.

| 번호 | 단계 (문서 링크) | 주요 주제 및 학습 목표 | 실습 시나리오 |
| :---: | :--- | :--- | :--- |
| **Part 1** | **기초 환경 및 핵심 시스템 리소스 진단** | | |
| **00** | [00-environment-setup.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/00-environment-setup.md) | Docker 기반 진단 랩 환경 구축 및 핵심 분석 패키지 설치 | `linux-lab` 컨테이너 빌드 및 sysstat, iproute2, procps 검증 |
| **01** | [01-package-management.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/01-package-management.md) | DPKG/APT 분리 아키텍처, GPG 키링 보안 격리, 버전 고정 | `dpkg -S/L` 출처 역추적, `apt-mark hold`, lock 경합 해소, 캐시 청소 |
| **02** | [02-process-and-signals.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/02-process-and-signals.md) | 프로세스 생명주기 관리, 상태 코드(R, S, D, Z) 및 시그널 제어 | 좀비 프로세스 재현, D-state(Uninterruptible) 원인 규명, Graceful Shutdown |
| **03** | [03-cpu-analysis.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/03-cpu-analysis.md) | CPU 사용률과 Load Average 차이 분석 및 스레드 병목 진단 | `stress-ng` 부하 주입, `pidstat` 코어별 병목 스레드 식별, cgroup throttling |
| **04** | [04-memory-and-oom.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/04-memory-and-oom.md) | 가상 메모리(VIRT/RES/SHR/PSS), 버퍼/캐시 회수 및 OOM 킬러 | 파이썬 메모리 누수 발생 후 OOM 킬러 호출 로그 분석, `oom_score_adj` 제어 |
| **05** | [05-disk-io-and-filesystems.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/05-disk-io-and-filesystems.md) | 스토리지 I/O 대기시간(%util, await), Inode 고갈, 디스크 용량 추적 | `lsof`를 이용해 프로세스가 잡고 있는 삭제 파일(Unlinked Open File) 추적 및 공간 회수 |
| **Part 2** | **심층 시스템 관측 및 네트워크 분석** | | |
| **06** | [06-network-troubleshooting.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/06-network-troubleshooting.md) | 네트워크 인터페이스 모니터링, TCP 소켓 상태 머신 및 패킷 분석 | `ss -s`, `tcpdump`를 이용한 3-Way Handshake 및 TIME_WAIT/CLOSE_WAIT 소켓 누수 진단 |
| **07** | [07-dns-and-http-diagnostics.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/07-dns-and-http-diagnostics.md) | DNS 리졸빙 메커니즘(/etc/resolv.conf) 및 cURL을 통한 L7 지연 계측 | `curl -w` 기반 DNS 타임아웃, TCP 연결, TLS 핸드셰이크, TTFB 구간별 지연 측정 |
| **08** | [08-systemd-and-journalctl.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/08-systemd-and-journalctl.md) | systemd 유닛 생명주기 관리, 실패 정책 설정 및 구조화된 저널 로그 검색 | 백그라운드 데몬 작성, 로그 로테이션 설정, `journalctl` 부팅별/우선순위별 필터링 |
| **09** | [09-system-calls-and-strace.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/09-system-calls-and-strace.md) | 시스템 콜 추적을 통한 무응답(Hang) 프로세스 원인 규명 | `strace`를 이용해 파일 오픈 실패, 네트워크 소켓 블로킹, 락 경합 실시간 추적 |
| **Part 3** | **커널/컨테이너 내부 아키텍처 및 실전 장애 대응** | | |
| **10** | [10-linux-security-and-permissions.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/10-linux-security-and-permissions.md) | Linux 파일 권한 체계, umask, POSIX ACLs 및 리눅스 Capabilities 격리 | 루트 권한 없는 80포트 바인딩(CAP_NET_BIND_SERVICE) 및 최소 권한 원칙 적용 |
| **11** | [11-linux-namespaces-and-cgroups.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/11-linux-namespaces-and-cgroups.md) | 컨테이너 런타임의 심장: Namespaces(PID, NET, MNT)와 cgroups v2 | `unshare`와 `nsenter`로 컨테이너 환경 수동 격리 및 메모리/CPU 쿼터 강제 부여 |
| **12** | [12-kernel-parameters-and-tuning.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/12-kernel-parameters-and-tuning.md) | 커널 런타임 매개변수(`sysctl`) 튜닝과 프로세스 리소스 한도(`ulimit`) | 대규모 트래픽 처리를 위한 `somaxconn`, `tcp_tw_reuse`, `file-max` 최적화 |
| **13** | [13-production-troubleshooting-playbook.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/13-production-troubleshooting-playbook.md) | [종합 실전] 복합 장애 시나리오 진단 및 응급 복구 엔지니어링 | Web 앱 소켓 고갈 + 디스크 풀 + CPU 스파이크 복합 인시던트 트러블슈팅 및 사후 보고서 |

---

## 📋 빠른 참조 (Quick Reference)

명령어 문법과 옵션, 핵심 패턴만을 빠르게 찾아보고 싶다면 아래 치트시트를 참조하세요.

👉 **[CHEATSHEET.md 바로가기](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/CHEATSHEET.md)**

---

## 🛠️ 권장 실습 규칙

1. **명령어의 파괴적 영향 검토**: 운영 환경에서는 시스템 상태를 확인하기 위한 명령어가 오히려 시스템을 마비시킬 수 있습니다(예: 과도한 버퍼를 요청하는 `tcpdump`, 전체 파일시스템 대상의 무분별한 `find /`). 본 가이드에서는 안전한 진단 옵션을 명시합니다.
2. **USE(Utilization, Saturation, Errors) 방법론 적용**:
   - **Utilization (사용률)**: 자원이 얼마나 사용되고 있는가?
   - **Saturation (포화도)**: 자원이 처리 한계를 넘어 대기 큐(Wait Queue)를 형성하고 있는가?
   - **Errors (오류)**: 자원 처리 과정에서 에러가 발생했는가?
3. **가설 기반 접근**: 단순히 명령어를 임의로 실행하지 않고, 증상을 확인한 후 원인에 대한 가설을 세우고 이를 검증하는 명령어를 단계별로 실행합니다.
