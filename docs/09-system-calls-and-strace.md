# 09. 시스템 콜(Syscall) 추적과 프로세스 디버깅

## 🎯 학습 목표 (Goal)
- 사용자 공간(User Space)과 커널 공간(Kernel Space)의 접점인 **시스템 콜(Syscall)**의 동작 원리를 이해합니다.
- 애플리케이션이 로그를 남기지 않고 멈춰 있거나(Hang), 설정 파일을 찾지 못하거나, 소켓 타임아웃이 발생할 때 **`strace`를 통해 프로세스의 모든 I/O 및 시스템 호출을 실시간 추적**하는 방법을 마스터합니다.
- 운영 환경에서 `strace` 사용 시 발생하는 오버헤드를 제어하기 위한 필터링 옵션(`-e trace=`, `-c`, `-T`)을 올바르게 활용합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. 시스템 콜(Syscall)이란 무엇인가?
일반 애플리케이션(User Space, Ring 3)은 하드웨어(CPU, RAM, 디스크, 네트워크 카드)에 직접 접근할 권한이 없습니다. 파일 읽기/쓰기, 네트워크 소켓 전송, 메모리 할당 등의 작업을 수행하려면 반드시 커널(Kernel Space, Ring 0)에 요청해야 합니다. 이때 사용하는 공식 인터페이스가 **시스템 콜(Syscall)**입니다.

주요 시스템 콜 분류:
- **파일 I/O**: `openat`, `read`, `write`, `close`, `stat`, `unlinkat`
- **네트워크 소켓**: `socket`, `bind`, `listen`, `accept4`, `connect`, `sendto`, `recvfrom`
- **프로세스 및 스레드**: `clone`, `execve`, `exit_group`, `wait4`
- **동기화 및 락(Lock)**: `futex` (Fast Userspace Mutex, 락 경합 시 블로킹 발생)
- **메모리 할당**: `brk`, `mmap`, `munmap`

### 2. 운영 환경에서 strace 사용 시 주의사항 (오버헤드 제어)
`strace`는 `ptrace()` 커널 시스템 콜을 기반으로 대상 프로세스의 매 시스템 콜 진입(Entry)과 탈출(Exit) 시점에 프로세스 실행을 일시 정지(Trap)시킵니다.
- **위험성**: 초당 수만 건의 I/O를 처리하는 고성능 DB나 웹 서버에 아무 옵션 없이 `strace -p <PID>`를 실행하면 서비스 처리량이 50%~90%까지 급감할 수 있습니다.
- **안전 수칙**:
  1. 전체 출력을 실시간으로 덤프하지 말고 **`-c` 옵션(통계 요약 모드)**을 먼저 사용하여 의심되는 시스템 콜을 좁힙니다.
  2. **`-e trace=network`** 또는 **`-e trace=file`** 처럼 관심 있는 카테고리만 한정하여 추적합니다.
  3. **`-T` 옵션**으로 각 시스템 콜이 지연된 시간(초)을 측정하여 블로킹 지점을 찾습니다.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 명령어 단위 시스템 콜 실행 통계 요약 (-c)
`curl` 명령어가 실행되면서 내부적으로 어떤 시스템 콜을 몇 번 호출하고 어디서 시간을 가장 많이 썼는지 요약합니다.

```bash
# linux-lab 컨테이너에서 실행
# -c: 시스템 콜별 호출 횟수, 오류 수, 소요 시간 백분율 통계 요약
strace -c curl -s http://chaos-target:8000/health > /dev/null
```

*출력 예시:*
```text
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 45.20    0.003450         115        30           mprotect
 20.10    0.001534          15       102           read
 15.30    0.001168          24        48        12 openat
 10.20    0.000778         194         4           poll
  5.10    0.000389          97         4           connect
  4.10    0.000312          52         6           socket
------ ----------- ----------- --------- --------- ----------------
100.00    0.007631                   260        12 total
```

### Step 2. 누락된 설정 파일 또는 경로 오류 추적 (-e trace=openat)
프로세스가 존재하지 않는 설정 파일을 찾느라 에러를 내거나 종료될 때, 실패한 `openat` 호출을 추적합니다.

```bash
# 파일 오픈 관련 시스템 콜만 필터링 (-e trace=openat)
strace -e trace=openat cat /etc/non_existent_config.conf
```

*출력 분석:*
```text
openat(AT_FDCWD, "/etc/non_existent_config.conf", O_RDONLY) = -1 ENOENT (No such file or directory)
cat: /etc/non_existent_config.conf: No such file or directory
+++ exited with 1 +++
```
- `-1 ENOENT`: 커널이 "해당 파일 또는 디렉터리가 없음" 오류를 반환했음을 직접 확인했습니다.

### Step 3. 실행 중인 프로세스에 부착하여 네트워크 I/O 실시간 추적
백그라운드에서 실행 중인 프로세스의 PID를 확인하고, 실시간 네트워크 I/O만 추적합니다.

```bash
# 1. 대상 컨테이너(chaos-target)의 Python 웹 애플리케이션 PID 확인 (PID 1)
# 2. curl로 지연 요청을 발생시키면서 소켓 read/write 시스템 콜 관측
# -f: 모든 스레드 추적, -t: 타임스탬프, -T: 시스템 콜 수행 소요 시간 표시
strace -f -t -T -e trace=network curl -s http://chaos-target:8000/health > /dev/null
```

*출력 분석:*
```text
13:45:01 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 3 <0.000045>
13:45:01 connect(3, {sa_family=AF_INET, sin_port=htons(8000), sin_addr=inet_addr("172.28.0.20")}, 16) = 0 <0.000720>
13:45:01 sendto(3, "GET /health HTTP/1.1\r\nHost: chaos"..., 76, 0, NULL, 0) = 76 <0.000035>
13:45:01 recvfrom(3, "HTTP/1.1 200 OK\r\nserver: uvicorn"..., 16384, 0, NULL, NULL) = 175 <0.005120>
13:45:01 close(3) = 0 <0.000025>
```
- `<0.005120>`: `recvfrom` 호출에서 서버의 HTTP 응답 데이터를 기다리느라 5.1ms 동안 블로킹되었음을 정확한 수치로 입증할 수 있습니다.

### Step 4. 무응답(Hang) 및 락(Lock) 경합 진단 기법
프로세스가 아무런 로그도 남기지 않고 멈춰 있을 때 `strace -p <PID>`를 실행하면:
- `futex(0x..., FUTEX_WAIT_BITSET, ...)` 호출에서 멈춰 있다면: 애플리케이션 레벨의 **멀티스레드 락(Deadlock 또는 Lock Contention)**에 걸려 있는 상태입니다.
- `recvfrom(3, ...)` 또는 `read(3, ...)`에서 멈춰 있다면: 외부 API나 DB 연결에서 **네트워크 타임아웃 미설정으로 소켓 응답을 무한정 대기 중**인 상태입니다.

---

## 🎯 마무리 및 다음 단계

시스템 콜의 동작 원리와 `strace`를 활용한 프로세스 블랙박스 디버깅 및 안전한 운영 환경 프로파일링 기법을 마스터했습니다.

다음 단계인 **[10-linux-security-and-permissions.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/10-linux-security-and-permissions.md)**에서는 루트 권한의 오남용을 방지하기 위한 **최소 권한 원칙(Least Privilege)**, POSIX 확장 접근 제어 목록(**ACLs**), 그리고 루트 권한 없이도 80/443 포트를 바인딩할 수 있게 해주는 **Linux Capabilities(`cap_net_bind_service`) 격리 기법**을 실습합니다.
