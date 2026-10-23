# 03. CPU 병목 및 로드 애버리지(Load Average) 진단

## 🎯 학습 목표 (Goal)
- **"CPU 사용률(CPU Utilization)"**과 **"로드 애버리지(Load Average)"**의 구조적 차이점을 명확히 규명합니다.
- CPU가 100% 포화된 상황에서 `mpstat`과 `pidstat`을 활용해 코어별 쏠림 현상과 병목을 유발하는 특정 스레드를 초 단위로 식별하는 능력을 배양합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. 로드 애버리지(Load Average)의 진정한 정의
`uptime` 또는 `top` 명령어로 확인하는 로드 애버리지(1분, 5분, 15분 수치)는 단순히 "CPU 사용량의 평균"이 아닙니다.
- **정의**: 특정 시간 동안 **CPU 실행 큐(Run Queue)에서 실행 중이거나 대기 중인 프로세스(R 상태)** + **인터럽트 불가능한 I/O 대기 프로세스(D 상태)**의 평균 개수입니다.
- **해석 기준 (CPU 코어가 4개인 시스템 기준)**:
  - **Load Average < 4.0**: 시스템이 모든 요청을 지연 없이 소화하고 있는 쾌적한 상태.
  - **Load Average = 4.0**: 4개의 CPU 코어가 쉬지 않고 100% 효율로 가동 중인 상태 (대기 큐 없음).
  - **Load Average > 4.0**: 처리 용량을 초과하여 대기 큐에 프로세스가 밀려 있는 **포화(Saturation)** 상태.

> [!IMPORTANT]
> **CPU 사용률은 5%인데 Load Average가 20인 기현상의 원인**:
> 많은 엔지니어가 이 현상에 혼란을 겪습니다. 리눅스는 과거 Unix와 달리 **D 상태(Uninterruptible Sleep, 주로 디스크나 NFS 등의 블록 I/O 완료 대기)** 프로세스도 로드 애버리지 집계에 포함합니다. 따라서 CPU 연산이 전혀 없어도 디스크 I/O가 병목되어 대기 중인 프로세스가 많으면 로드 애버리지가 치솟게 됩니다.

### 2. CPU 사용률의 5대 메트릭 분석
`top`이나 `mpstat`에서 표기되는 CPU 시간 분할의 의미:

| 메트릭 | 명칭 | 시스템 진단 관점의 원인 및 대책 |
| :---: | :--- | :--- |
| **%usr** | User Time | 사용자 공간(User Space) 애플리케이션 연산. 비즈니스 로직 연산, JSON 직렬화, 정규식 등. |
| **%sys** | System Time | 커널 공간(Kernel Space) 연산. 과도한 시스템 콜 호출, 잦은 파일 읽기/쓰기, 소켓 생성/삭제 등. |
| **%iowait** | I/O Wait Time | CPU가 유휴 상태이지만, 처리할 디스크/블록 I/O 응답을 기다리고 있는 비율. 높다면 스토리지 진단 필요. |
| **%steal** | Steal Time | 가상화 환경(클라우드 인스턴스 등)에서 하이퍼바이저가 다른 VM에 CPU 사이클을 할당하여 우리 VM이 CPU를 빼앗긴 시간. 높다면 인스턴스 스케일업 필요. |
| **%idle** | Idle Time | CPU가 아무 작업도 하지 않고 유휴 상태인 비율. |

### 3. 자발적(Voluntary) vs 비자발적(Involuntary) 컨텍스트 스위칭
- **자발적 컨텍스트 스위칭 (`cswch/s`)**: 프로세스가 I/O 응답, 락(Lock) 획득 대기를 위해 스스로 CPU 할당을 반납한 횟수.
- **비자발적 컨텍스트 스위칭 (`nvcswch/s`)**: 프로세스가 더 일하고 싶지만, OS 스케줄러에 의해 강제로 타임 슬라이스(Time Slice)를 빼앗긴 횟수. **이 수치가 급증하면 CPU 코어 수 대비 너무 많은 스레드가 경합 중임을 의미합니다.**

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 기준(Baseline) 시스템 상태 확인
아무런 부하가 없는 상태에서 시스템의 로드 애버리지와 코어 수를 측정합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 사용 가능한 논리 CPU 코어 수 확인
lscpu | grep "CPU(s):"

# 2. 현재 시스템 로드 애버리지 확인
uptime

# 3. 1초 간격으로 3회 전체 코어 CPU 사용률 계측
mpstat -P ALL 1 3
```

### Step 2. CPU 스파이크 부하 주입 (stress-ng)
`stress-ng` 유틸리티를 사용하여 2개의 코어에 100% 매트릭스 연산 부하를 30초 동안 발생시킵니다.

```bash
# 백그라운드에서 2개 CPU 워커 가동 (30초 후 자동 종료)
stress-ng --cpu 2 --cpu-method matrixprod --timeout 30s --metrics-brief &
```

### Step 3. 실시간 CPU 사용률 및 코어별 편중 진단
부하가 걸린 상태에서 즉시 다른 터미널 또는 동일 쉘에서 모니터링을 수행합니다.

```bash
# 1. vmstat으로 실행 큐 대기 수(r 열)와 유저 CPU 사용률(us 열) 확인
vmstat -w 1 5
```

*vmstat 출력 분석:*
```text
procs -------------------memory------------------ ---swap-- -----io---- -system-- ------cpu-----
 r  b       swpd       free       buff      cache   si   so    bi    bo   in    cs us sy id wa st
 2  0          0    1842012     104232    1240188    0    0     0     0 2100  4200 98  2  0  0  0
```
- `r` 열이 2로 증가(실행 큐에 2개의 프로세스가 CPU를 기다림)
- `us` 열이 98%로 증가(유저 공간 연산 포화)

```bash
# 2. mpstat으로 코어별 부하 분포 확인
mpstat -P ALL 1 3
```

```bash
# 3. pidstat으로 CPU를 과도하게 점유하는 프로세스의 PID 식별
pidstat -u 1 3
```

*pidstat 출력 분석:*
```text
Linux 6.6.x (linux-lab) 	10/22/2026 	_x86_64_	(4 CPU)

13:25:01      UID       PID    %usr %system  %guest   %wait    %CPU   CPU  Command
13:25:02        0       245   99.00    0.00    0.00    0.00   99.00     1  stress-ng-cpu
13:25:02        0       246   99.00    0.00    0.00    0.00   99.00     2  stress-ng-cpu
```

### Step 4. 웹 애플리케이션 CPU 과부하 시나리오 진단
실제 웹 서버(`chaos-target`)에 CPU 집약적 엔드포인트를 호출하고, 백엔드 서비스의 병목을 진단합니다.

```bash
# 1. 타깃 웹 서버에 10초간 CPU 연산 부하 주입 요청
curl -X POST "http://chaos-target:8000/chaos/cpu?duration_seconds=10" &

# 2. 실시간 top 또는 pidstat으로 타깃 컨테이너의 프로세스 점유율 확인
# (도커 호스트 환경 또는 컨테이너 메트릭 엔드포인트 확인)
curl -s http://chaos-target:8000/metrics/process | jq .
```

### Step 5. 컨텍스트 스위칭 경합 분석
`pidstat -w` 옵션을 사용하여 스레드가 과도하게 전환되고 있는지 확인합니다.

```bash
# 1초 간격으로 자발적(cswch/s) 및 비자발적(nvcswch/s) 스위칭 횟수 측정
pidstat -w 1 3
```

---

## 🎯 마무리 및 다음 단계

CPU 리소스 병목의 두 축인 **사용률(%usr/%sys)**과 **포화도(Load Average/Run Queue)**를 분리하여 진단하는 프레임워크를 확립했습니다.

다음 단계인 **[04-memory-and-oom.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/04-memory-and-oom.md)**에서는 **가상 메모리 시스템(Virtual Memory)**의 핵심인 VIRT/RES/SHR의 메커니즘, 리눅스 커널의 **Page Cache 회수 메커니즘**, 그리고 프로세스가 비정상 종료되는 **OOM(Out of Memory) Killer의 선정 기준과 방어 기법**을 심층 분석합니다.
