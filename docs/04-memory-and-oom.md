# 04. 가상 메모리 아키텍처 및 OOM Killer 분석

## 🎯 학습 목표 (Goal)
- Linux 가상 메모리 관리자(VMM)의 핵심 메커니즘인 `VIRT`, `RES`, `SHR` 및 `PSS`의 차이를 명확히 이해합니다.
- 버퍼(Buffers)와 페이지 캐시(Page Cache)의 회수 메커니즘을 파악하고, 시스템 메모리가 고갈되었을 때 작동하는 **OOM(Out of Memory) Killer의 선정 기준(Badness Heuristic)과 방어 설정(`oom_score_adj`)**을 실습합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. 프로세스 메모리 지표의 정확한 정의
`top`이나 `ps`에서 출력되는 메모리 지표는 가상 메모리 페이징(Paging) 메커니즘으로 인해 단순 합산할 수 없습니다.

| 지표 | 명칭 | 설명 및 시스템 분석 관점의 의미 |
| :---: | :--- | :--- |
| **VIRT** | Virtual Memory Size | 프로세스가 `malloc()`, `mmap()` 등으로 커널에 요청하여 할당받은 **가상 주소 공간의 총량**. 실제 물리 메모리가 할당되지 않은 영역도 포함하므로 단독으로 메모리 부족을 판단하는 근거가 될 수 없습니다. |
| **RES / RSS** | Resident Set Size | 프로세스가 현재 **물리 메모리(RAM)에 실제로 올리고 점유 중인 페이지 크기**. 공유 라이브러리(libc 등)의 크기가 중복 포함되어 있어, 시스템 전체 프로세스의 RSS를 단순 합산하면 실제 물리 RAM 크기를 초과하게 됩니다. |
| **SHR** | Shared Memory | 다른 프로세스와 공유하고 있는 물리 메모리 크기 (공유 라이브러리, IPC 공유 메모리 세그먼트 등). |
| **PSS** | Proportional Set Size | 공유 라이브러리 메모리를 이를 참조하는 프로세스 수로 나눈 뒤 고유 메모리(USS)와 합산한 값. **프로세스의 실제 물리 메모리 기여도를 가장 정확히 측정하는 지표**입니다. |

### 2. Buffers와 Cached의 차이 및 Free vs Available
`free -h` 명령어의 출력값 중:
- **Buffers**: 블록 디바이스(Raw 디스크 블록)의 메타데이터 및 파일시스템 쓰기 작업을 위해 커널이 임시 보관하는 메모리.
- **Cached (Page Cache)**: 디스크 I/O 성능 향상을 위해 최근 읽거나 쓴 파일 내용을 메모리에 올려둔 캐시.
- **available**: 커널이 새 프로세스나 기존 작업에 즉각 할당할 수 있는 **실질 가용 메모리**입니다 (`free` + 회수 가능한 `Page Cache/Buffers` - 커널 최소 보장 공간).

> [!NOTE]
> 리눅스 커널은 놀고 있는 RAM을 낭비로 간주하므로, 가능한 모든 유휴 메모리를 Page Cache로 채웁니다. 따라서 `free` 수치가 100MB 미만이어도 `available`이 충분하다면 메모리 부족 상태가 아닙니다.

### 3. OOM Killer와 oom_score 계산 원리
물리 메모리와 스왑이 모두 고갈되고 페이지 캐시도 더 이상 회수할 수 없는 긴급 상황에 도달하면, 커널은 시스템 전체 크래시(Kernel Panic)를 막기 위해 프로세스 하나를 강제 사살(`SIGKILL`)합니다. 이를 **OOM Killer**라고 합니다.

- **Badness 계산**: 프로세스가 사용 중인 물리 메모리 비율(`RSS`), 실행 시간(오래 실행된 프로세스는 감점), 루트 권한 여부 등을 종합하여 0~1000 사이의 `oom_score`를 산출합니다.
- 점수가 가장 높은 프로세스가 1순위 사살 대상이 됩니다.
- **`/proc/<PID>/oom_score_adj`**: -1000부터 +1000까지의 값을 지정하여 강제로 우선순위를 변경할 수 있습니다.
  - `-1000`: OOM Killer 대상에서 완전 배제 (절대 킬되지 않음)
  - `+1000`: 메모리가 부족할 때 가장 먼저 킬 대상이 됨

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 호스트 및 컨테이너 메모리 현황 진단
현재 메모리의 상세 분할 현황을 확인합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. free 명령어로 가용 메모리 확인
free -h

# 2. 커널 meminfo에서 세부 캐시 통계 확인
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Buffers|Cached|Dirty|Active|Inactive"
```

*출력 예시:*
```text
               total        used        free      shared  buff/cache   available
Mem:           7.7Gi       1.2Gi       4.5Gi        12Mi       2.0Gi       6.2Gi
Swap:          2.0Gi          0B       2.0Gi
```

### Step 2. smem 유틸리티를 활용한 PSS 기반 정밀 측정
프로세스별 고유 메모리(USS)와 비례 분할 메모리(PSS)를 확인합니다.

```bash
# PSS 기준 내림차순 정렬 (상위 10개 프로세스)
smem -t -k -s pss -r | head -n 12
```

### Step 3. 실전 장애 재현: 타깃 애플리케이션 메모리 누수 유발
`chaos-target` 컨테이너(메모리 512MB 제한 환경)에 메모리 누수를 단계적으로 주입합니다.

```bash
# 1. 타깃 프로세스의 현재 메모리 사용량 확인
curl -s http://chaos-target:8000/metrics/process | jq '{pid, memory_rss_mb, leaked_memory_chunks_count}'

# 2. 128MB 메모리 누수 1차 주입
curl -X POST "http://chaos-target:8000/chaos/memory-leak?size_mb=128" | jq .

# 3. 128MB 메모리 누수 2차 주입
curl -X POST "http://chaos-target:8000/chaos/memory-leak?size_mb=128" | jq .

# 4. 메모리 증가 확인
curl -s http://chaos-target:8000/metrics/process | jq '{pid, memory_rss_mb, leaked_memory_chunks_count}'
```

### Step 4. OOM Killer 강제 작동 및 커널 로그 확인
컨테이너 리소스 한계(512MB)를 초과하도록 추가 256MB를 주입하여 OOM Killer를 발생시킵니다.

```bash
# 한계치를 초과하는 메모리 할당 요청
curl -X POST "http://chaos-target:8000/chaos/memory-leak?size_mb=256"
```

타깃 프로세스가 비정상 종료되었는지 확인하고, 커널 로그에서 OOM Killer 작동 기록을 분석합니다.

```bash
# 1. 커널 링 버퍼에서 Out of memory 로그 탐색
dmesg -T | grep -i -E "oom|out of memory|killed process" | tail -n 20
```

*커널 OOM 로그 분석 예시:*
```text
[Thu Oct 22 13:35:10 2026] Memory cgroup out of memory: Killed process 1 (uvicorn) total-vm:612340kB, anon-rss:498212kB, file-rss:1240kB, shmem-rss:0kB, oom_score_adj:0
```
- cgroup의 메모리 한도에 도달하여 커널이 가장 점유율이 높은 PID 1(uvicorn) 프로세스를 `anon-rss:498212kB` 상태에서 사살했음을 증명합니다.

### Step 5. 프로세스 oom_score_adj 조정 실습
핵심 데몬 프로세스를 OOM Killer로부터 보호하는 설정을 테스트합니다.

```bash
# 1. 현재 쉘 프로세스의 OOM 스코어 확인
cat /proc/$$/oom_score

# 2. OOM 킬러 보호 설정 (-500 감점 부여)
echo -500 > /proc/$$/oom_score_adj

# 3. 변경된 OOM 스코어 재확인 (점수가 대폭 감소함)
cat /proc/$$/oom_score
```

---

## 🎯 마무리 및 다음 단계

가상 메모리의 페이징 원리, Page Cache와 Available 메모리의 판별 기준, 그리고 OOM Killer의 사살 알고리즘과 방어 체계를 확립했습니다.

다음 단계인 **[05-disk-io-and-filesystems.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/05-disk-io-and-filesystems.md)**에서는 **"디스크 용량이 100%인데 du로는 아무것도 나오지 않는 현상(Unlinked Open File)"**을 `lsof +L1`으로 추적하고, **Inode 고갈 장애** 및 `iostat`을 통한 블록 I/O 대기시간(%util, await) 분석 기법을 실습합니다.
