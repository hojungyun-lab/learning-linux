# 11. 컨테이너 내부 원리 - 네임스페이스와 cgroups v2

## 🎯 학습 목표 (Goal)
- Docker나 컨테이너 런타임의 마법 뒤에 있는 리눅스 커널의 2대 핵심 기둥인 **네임스페이스(Namespaces, 시야 격리)**와 **cgroups v2(Control Groups, 리소스 할당 제어)**의 내부 아키텍처를 파악합니다.
- `unshare` 명령어를 사용해 별도의 가상화 도구 없이 **순수 리눅스 커널 기능만으로 독립된 PID/네트워크 샌드박스를 직접 생성**해 봅니다.
- `/sys/fs/cgroup/` 파일시스템 계층 구조에서 직접 cgroups v2 컨트롤러를 조작하여 프로세스의 메모리 상한선 및 CPU 쿼터를 강제 제한하는 실습을 진행합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. 컨테이너(Container)의 실체
컨테이너는 가상 머신(VM)처럼 별도의 하이퍼바이저나 게스트 OS 커널을 띄우는 것이 아닙니다.
**"호스트 OS의 커널을 그대로 공유하면서, 네임스페이스로 시야를 격리하고 cgroups로 리소스를 제한한 일반 리눅스 프로세스"**에 불과합니다.

### 2. Linux 6대 핵심 네임스페이스 (시야 격리)
프로세스가 볼 수 있는 시스템 자원의 범위를 격리합니다:

| 네임스페이스 | 격리 대상 | 설명 |
| :---: | :--- | :--- |
| **PID** | 프로세스 ID | 컨테이너 내부에서는 해당 프로세스가 `PID 1`로 보이지만, 호스트에서는 일반 높은 PID로 매핑됩니다. |
| **NET** | 네트워크 장치 | 독립된 루프백(`lo`), 가상 이더넷(`veth`), 라우팅 테이블, 방화벽(iptables)을 보유합니다. |
| **MNT** | 파일시스템 마운트 | 호스트의 루트 파일시스템과 분리된 독립된 마운트 지점 트리를 가집니다 (`pivot_root`). |
| **UTS** | 호스트명 및 도메인 | 독립된 `hostname`을 가집니다. |
| **IPC** | 프로세스 간 통신 | 독립된 공유 메모리(POSIX/SysV IPC), 세마포어, 메시지 큐를 가집니다. |
| **USER** | 사용자 및 그룹 ID | 컨테이너 내부의 `UID 0(root)`을 호스트의 비특권 일반 유저(UID 10001)로 안전하게 매핑합니다. |

### 3. cgroups v2 (Control Groups: 리소스 제어 및 과금)
과거 cgroups v1의 파편화된 다중 계층(cpu, memory, blkio가 따로 놀던 구조)을 통합하여, 리눅스 커널 5.x 이상에서는 **cgroups v2(단일 통합 계층 파일시스템)**가 표준으로 자리잡았습니다.

`/sys/fs/cgroup/` 디렉터리 내에 폴더를 생성하는 것만으로 새 cgroup이 만들어지며, 파일에 숫자를 쓰는 것으로 리소스가 강제 제한됩니다:
- **`memory.max`**: 프로세스 그룹이 사용할 수 있는 최대 물리 메모리 바이트 수 (초과 시 OOM 발생).
- **`cpu.max`**: `[quota] [period]` 형식으로 지정 (예: `50000 100000`은 100ms 중 50ms만 CPU를 사용할 수 있도록 하여 0.5 코어로 제한).
- **`pids.max`**: 프로세스 그룹 내에서 포크(fork)할 수 있는 최대 프로세스/스레드 개수 (포크 폭탄 방지).

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 현재 프로세스의 네임스페이스 링크 검사
모든 프로세스는 `/proc/<PID>/ns/` 디렉터리 아래에 자신이 속한 네임스페이스의 고유 Inode 번호를 심볼릭 링크로 가지고 있습니다.

```bash
# linux-lab 컨테이너에서 실행
# 현재 쉘($$)의 네임스페이스 식별자 확인
ls -l /proc/$$/ns/
```

*출력 예시:*
```text
lrwxrwxrwx 1 root root 0 Oct 22 13:46 cgroup -> 'cgroup:[4026531835]'
lrwxrwxrwx 1 root root 0 Oct 22 13:46 ipc -> 'ipc:[4026532840]'
lrwxrwxrwx 1 root root 0 Oct 22 13:46 mnt -> 'mnt:[4026532838]'
lrwxrwxrwx 1 root root 0 Oct 22 13:46 net -> 'net:[4026532842]'
lrwxrwxrwx 1 root root 0 Oct 22 13:46 pid -> 'pid:[4026532841]'
lrwxrwxrwx 1 root root 0 Oct 22 13:46 uts -> 'uts:[4026532839]'
```

### Step 2. unshare를 이용한 즉석 격리 컨테이너 쉘 생성
도커 엔진을 거치지 않고, `unshare` 명령어로 완전히 새로운 PID 및 Mount 네임스페이스를 생성합니다.

```bash
# 새로운 PID, Mount 네임스페이스를 생성하고 proc 파일시스템을 새로 마운트하여 쉘 실행
unshare --pid --mount-proc --fork bash
```

새로 진입한 쉘에서 프로세스 목록을 확인합니다:
```bash
# 격리된 샌드박스 내부에서 프로세스 목록 확인
ps aux
```

*출력 분석:*
```text
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.0   4640  3968 ?        S    13:47   0:00 bash
root         2  0.0  0.0   7060  1536 ?        R+   13:47   0:00 ps aux
```
- 호스트나 외부의 수많은 프로세스는 전혀 보이지 않고, 방금 실행한 `bash`가 **`PID 1`**로 동작하고 있음을 직접 확인할 수 있습니다!
- 확인 후 `exit` 명령어로 원래 쉘로 복귀합니다.

```bash
exit
```

### Step 3. cgroups v2를 이용한 메모리 상한선 강제 제어
커널의 cgroup 파일시스템에 직접 그룹을 만들고 메모리 한도를 50MB로 제한해 봅니다.

```bash
# 1. cgroup v2 마운트 지점에 실습용 그룹 생성 (디렉터리 생성 시 커널이 컨트롤러 파일 자동 생성)
mkdir -p /sys/fs/cgroup/sandbox-limit || true

# 2. 메모리 상한선을 50MB(52428800 바이트)로 설정
echo "52428800" > /sys/fs/cgroup/sandbox-limit/memory.max || true

# 3. 설정 확인
cat /sys/fs/cgroup/sandbox-limit/memory.max
```

이제 현재 쉘 또는 특정 프로세스를 이 cgroup에 편입시킵니다:
```bash
# 현재 프로세스($$)를 sandbox-limit cgroup에 등록
echo $$ > /sys/fs/cgroup/sandbox-limit/cgroup.procs

# 50MB를 초과하는 메모리를 강제로 할당하여 cgroup OOM Killer 작동 확인
python3 -c "b = b'X' * (80 * 1024 * 1024)"
```

*결과 확인:*
```text
Killed
```
- 커널의 cgroups v2 컨트롤러가 50MB 한도를 감지하고 프로세스를 즉각 강제 종료(Killed)시켰습니다.

---

## 🎯 마무리 및 다음 단계

컨테이너 기술의 근간인 Linux Namespaces의 시야 격리 원리와 cgroups v2를 통한 하드웨어 자원 강제 할당 원리를 심도 있게 증명했습니다.

다음 단계인 **[12-kernel-parameters-and-tuning.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/12-kernel-parameters-and-tuning.md)**에서는 대규모 트래픽을 처리하는 고성능 서버를 구축하기 위해 필수적인 **커널 파라미터(`sysctl`) 튜닝(`somaxconn`, `tcp_max_syn_backlog`, `tcp_tw_reuse`)**과 **파일 디스크립터 한도(`ulimit`, `prlimit`)** 설정법을 학습합니다.
