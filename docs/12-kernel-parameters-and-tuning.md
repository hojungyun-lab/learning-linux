# 12. 커널 파라미터 튜닝과 리소스 한도

## 🎯 학습 목표 (Goal)
- 대규모 트래픽을 처리하는 백엔드 서버를 위한 핵심 커널 파라미터(`sysctl`, `/proc/sys`)의 작동 메커니즘을 파악합니다.
- TCP 연결 백로그(`somaxconn`, `tcp_max_syn_backlog`), 포트 범위(`ip_local_port_range`), 가상 메모리 성향(`vm.swappiness`, `vm.overcommit_memory`)을 최적화합니다.
- 프로세스의 파일 디스크립터 한도(`ulimit -n`)를 이해하고, 이미 실행 중인 프로세스의 리소스 한도를 무중단으로 확장할 수 있는 **`prlimit` 도구 활용법**을 마스터합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. 프로덕션 고성능 커널 파라미터 5대 핵심 그룹
기본 커널 파라미터는 범용 데스크톱/소형 서버 기준이므로, 초당 수천~수만 건의 요청을 처리하는 웹 서버나 분산 서비스에서는 병목이 발생합니다:

| 카테고리 | 커널 파라미터 | 기본값 | 권장 튜닝값 | 시스템 엔지니어링 관점의 핵심 이유 |
| :--- | :--- | :---: | :---: | :--- |
| **TCP 소켓 백로그** | `net.core.somaxconn` | 128 / 4096 | `65535` | 애플리케이션의 `accept()` 대기 큐 크기. 트래픽 폭주 시 연결 드롭(Drop) 방지. |
| **SYN 대기 큐** | `net.ipv4.tcp_max_syn_backlog` | 512 / 1024 | `16384` | 3-Way Handshake 도중 SYN_RECV 상태의 연결을 보관하는 큐. SYN 플러딩 방어. |
| **소켓 재사용** | `net.ipv4.tcp_tw_reuse` | 0 | `1` | 송신(Outbound) 요청 시 TIME_WAIT 소켓을 안전하게 즉각 재사용하여 포트 고갈 방지. |
| **가용 포트 범위** | `net.ipv4.ip_local_port_range` | 32768 60999 | `10240 65535` | 외부 API나 마이크로서비스 호출 시 할당 가능한 Ephemeral Port를 약 55,000개로 대폭 확장. |
| **스왑 성향** | `vm.swappiness` | 60 | `10` 또는 `1` | 물리 메모리가 부족할 때 프로세스 메모리를 스왑 아웃(Swap-out)하는 적극성. 레이턴시 민감 서비스는 낮춤. |
| **메모리 오버커밋** | `vm.overcommit_memory` | 0 | `1` | Redis 백그라운드 스냅샷(`BGSAVE`) 등 대규모 `fork()`를 수행하는 서비스에서 메모리 할당 거부 방지. |

### 2. ulimit의 한계와 prlimit을 통한 무중단 한도 확장
- **`ulimit -Sn` (Soft Limit)**: 프로세스가 실제로 준수해야 하는 현재의 한도. 프로세스가 직접 Hard Limit까지 올릴 수 있음.
- **`ulimit -Hn` (Hard Limit)**: 오직 root 권한자만이 올릴 수 있는 상한선.
- **문제점**: `/etc/security/limits.conf`에 한도를 추가해도 **이미 실행 중인 데몬 프로세스에는 반영되지 않으며**, 적용을 위해 서비스를 재시작하면 서비스 중단(Downtime)이 발생합니다.
- **해결책 (`prlimit`)**: 커널의 `prlimit64()` 시스템 콜을 호출하여, **실행 중인 프로세스의 PID를 지정해 서비스 중단 없이 즉시 리소스 한도를 변경**할 수 있습니다.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 현재 커널 파라미터 조회
현재 시스템의 주요 네트워크 및 메모리 튜닝 파라미터를 점검합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. TCP 백로그 크기 조회
sysctl net.core.somaxconn

# 2. 로컬 포트 범위 조회
sysctl net.ipv4.ip_local_port_range

# 3. 스왑 민감도 조회
sysctl vm.swappiness

# 4. 시스템 전체 파일 디스크립터 최대 한도
sysctl fs.file-max
```

### Step 2. 런타임 커널 파라미터 동적 적용 실습
재부팅 없이 메모리 상에서 커널 파라미터를 즉시 변경합니다.

```bash
# somaxconn 한도를 65535로 증설
sysctl -w net.core.somaxconn=65535

# tcp_tw_reuse 활성화
sysctl -w net.ipv4.tcp_tw_reuse=1

# 변경 결과 확인
sysctl net.core.somaxconn net.ipv4.tcp_tw_reuse
```

> [!NOTE]
> `sysctl -w` 명령은 런타임 메모리에 즉시 적용되지만 재부팅 시 초기화됩니다. 영구 반영을 위해서는 `/etc/sysctl.d/99-custom-tuning.conf` 파일에 작성 후 `sysctl -p`를 실행해야 합니다.

### Step 3. prlimit을 이용한 실행 중인 프로세스의 FD 한도 무중단 변경
실행 중인 프로세스의 리소스 한도를 확인하고 동적으로 확장합니다.

```bash
# 1. 타깃 프로세스(chaos-target)의 현재 리소스 한도 조회 (PID 1)
# NOFILE(오픈 파일 수)의 Soft/Hard 값 확인
prlimit --pid 1 --nofile
```

*출력 예시:*
```text
RESOURCE DESCRIPTION               SOFT  HARD UNITS
NOFILE   max number of open files  1024 65536 files
```

현재 Soft 한도가 1024로 낮게 잡혀 있습니다. 서비스 재시작 없이 이를 65536으로 확장합니다:

```bash
# 2. 프로세스 재시작 없이 Soft 한도를 65536으로 즉시 상향
prlimit --pid 1 --nofile=65536:65536

# 3. 변경 결과 확인
prlimit --pid 1 --nofile
```

*출력 분석:*
```text
RESOURCE DESCRIPTION               SOFT  HARD UNITS
NOFILE   max number of open files 65536 65536 files
```
- 프로세스가 중단되지 않은 상태에서 최대 오픈 파일 한도가 65,536개로 즉각 확장되었습니다. 이제 대규모 동시 접속이 인입되어도 `Too many open files` 에러가 발생하지 않습니다.

---

## 🎯 마무리 및 다음 단계

커널 런타임 튜닝(`sysctl`)의 핵심 파라미터와 `prlimit`을 통한 무중단 리소스 한도 확장 엔지니어링을 완성했습니다.

다음 단계인 마지막 **[13-production-troubleshooting-playbook.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/13-production-troubleshooting-playbook.md)**에서는 지금까지 학습한 모든 기법(CPU, 메모리, Inode/Unlinked 파일, TCP 소켓, 시스템 콜)을 집대성하여, **실제 프로덕션 복합 장애 시나리오를 직접 격리, 진단, 조치하고 사후 분석 보고서(Post-mortem)를 작성하는 종합 실전 모의훈련**을 진행합니다.
