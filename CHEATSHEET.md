# ⚡ Linux 시스템 엔지니어링 빠른 참조 치트시트 (CHEATSHEET.md)

시스템 운영 중 성능 저하나 장애가 발생했을 때 커널 및 하위 서브시스템(CPU, 메모리, 스토리지, 네트워크) 상태를 진단하고 병목을 식별하기 위한 **명령어 요약 및 실행 결과 기반 상세 해석 가이드**입니다.

각 섹션은 긴급 복사용 **빠른 원라이너 요약표**와 **터미널 실행 결과 및 핵심 열(Column)별 상세 해석 표**로 구성되어 있습니다.

---

## 1. 초기 긴급 점검 (Initial Emergency Check)

### 📋 빠른 진단 원라이너 요약표
| 대상 자원 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **시스템 부하** | `uptime` | 가동 시간 및 1/5/15분 로드 애버리지(Run Queue 포화도) 확인 |
| **커널 이벤트** | `dmesg -T --level=emerg,alert,crit,err \| tail -n 20` | 하드웨어 결함, I/O 오류, OOM Killer 작동 로그 탐색 |
| **시스템 통합** | `vmstat -w 1 5` | CPU 실행대기(`r`), I/O대기(`b`), 스왑(`si/so`), 시스템 I/O 통합 계측 |
| **CPU 코어별** | `mpstat -P ALL 1 3` | 특정 코어 쏠림 현상 및 I/O 대기율(`%iowait`) 분리 계측 |
| **물리 메모리** | `free -h` | 총 메모리 대비 실질 가용 메모리(`available`) 및 스왑 사용 여부 확인 |
| **스토리지 I/O** | `iostat -xz 1 3` | 블록 디바이스별 포화도(`%util`) 및 요청 처리 지연시간(`r_await`, `w_await`) |
| **디스크 용량** | `df -hT -x tmpfs -x devtmpfs` | 파일시스템 마운트 지점별 디스크 공간 고갈 여부 점검 |
| **소켓 요약** | `ss -s` | 총 TCP 소켓 수 및 ESTABLISHED / TIME_WAIT 연결 분포 확인 |
| **네트워크 오류** | `ip -s link` | 인터페이스별 드롭(`dropped`), 에러(`errors`), 오버런 발생 여부 확인 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### 1) `uptime` & `vmstat -w 1 2`
```bash
uptime
vmstat -w 1 2
```

```text
 16:27:47 up 7 days,  1:04,  0 user,  load average: 0.03, 0.01, 0.00
--procs-- -----------------------memory---------------------- ---swap-- -----io---- -system-- ----------cpu----------
   r    b         swpd         free         buff        cache   si   so    bi    bo   in   cs  us  sy  id  wa  st  gu
   0    0            0     14683636          112      1150060    0    0   887   176 1345    1   1   0  99   0   0   0
   0    0            0     14687168          112      1150908    0    0     0     0  131  135   0   0 100   0   0   0
```

| 열(Column) | 기술적 의미 | 정상 기준 | 이상 징후 판단 및 조치 방향 |
| :--- | :--- | :---: | :--- |
| **`load average`** | CPU 실행 큐 대기 프로세스(R) + I/O 대기 프로세스(D)의 평균 수 | `< 코어 수` | `Load Average > 논리 코어 수`: 시스템 처리 용량 초과. `vmstat`의 `r`과 `b`로 원인 분리. |
| **`procs: r`** | CPU 실행 대기 큐(Run Queue)에 대기 중인 프로세스 수 | `0 ~ 2` | 코어 수보다 지속적으로 크다면 CPU 연산 병목 발생. `pidstat -u`로 원인 프로세스 추적. |
| **`procs: b`** | 디스크/네트워크 블록 I/O 완료를 기다리는 인터럽트 불가(D 상태) 프로세스 수 | `0` | `b > 0`이 지속되면 디스크 병목 또는 스토리지 응답 불가 상태. `iostat`, `iotop` 점검 필수. |
| **`swap: si/so`** | 초당 디스크에서 스왑 인(si) / 스왑 아웃(so)되는 메모리 블록 수 | `0` | `so > 0`: 물리 RAM 고갈로 디스크 스왑 발생. 심각한 I/O 스파이크 및 지연 유발. |
| **`cpu: us`** | 사용자 공간(User Space) 비즈니스 로직 연산 비율 | `< 70%` | 높다면 애플리케이션 알고리즘 최적화, 스케일아웃, 연산 루프 점검 필요. |
| **`cpu: sy`** | 커널 공간(System/Kernel Space) 시스템 콜 처리 비율 | `< 20%` | 높다면 과도한 컨텍스트 스위칭, 잦은 I/O 시스템 콜 호출, 락 경합 의심 (`strace` 분석). |
| **`cpu: wa`** | 디스크 I/O 응답을 기다리느라 CPU가 유휴(Idle) 상태로 대기한 비율 | `< 5%` | 높다면 느린 디스크 장치, 대량의 DB 디스크 쓰기 발생. |

---

#### 2) `free -h`
```bash
free -h
```

```text
               total        used        free      shared  buff/cache   available
Mem:            15Gi       816Mi        14Gi        22Mi       1.1Gi        14Gi
Swap:           16Gi          0B        16Gi
```

| 열(Column) | 기술적 의미 | 주의점 및 이상 징후 판단 기준 |
| :--- | :--- | :--- |
| **`total`** | 커널이 인식하는 전체 물리 RAM 용량 | BIOS/하드웨어 예약 영역을 제외한 가용 메모리. |
| **`used`** | 프로세스들이 현재 점유 중인 메모리 (RSS) | 커널 슬랩, 버퍼/캐시 영역은 포함되지 않음. |
| **`free`** | 커널과 애플리케이션 모두가 전혀 건드리지 않은 빈 메모리 | 리눅스는 유휴 메모리를 Page Cache로 적극 활용하므로 `free`가 낮아도 정상임. |
| **`buff/cache`** | 디스크 블록 메타데이터(Buffers)와 파일 캐시(Page Cache) | 새 프로세스가 메모리를 요구하면 커널이 즉시 회수하여 할당함. |
| **`available`** | **[가장 중요]** 스왑 없이 즉각 신규 할당 가능한 실질 가용 메모리 | **`available < 10%`**이면 심각한 메모리 압박 상태이며 곧 OOM Killer가 작동함. |
| **`Swap: used`** | 디스크 스왑 파티션에 기록된 메모리 양 | 물리 RAM이 부족하여 프로세스 메모리가 디스크로 쫓겨난 상태. |

---

#### 3) `iostat -xz 1 1`
```bash
iostat -xz 1 1
```

```text
Device   r/s   rkB/s  %rrqm  r_await rareq-sz   w/s   wkB/s  %wrqm  w_await wareq-sz  aqu-sz  %util
vda     5.48  355.62   0.44     0.00    64.94  0.00    0.00   0.00     0.00     0.00    0.00   0.35
vdb    12.64  531.89   1.60     0.00    42.08  3.70  176.91  24.00     0.36    47.79    0.00   0.18
```

| 열(Column) | 기술적 의미 | 정상 기준 | 이상 징후 판단 및 조치 방향 |
| :--- | :--- | :---: | :--- |
| **`r/s`, `w/s`** | 초당 디바이스에 요청된 읽기/쓰기 입출력 횟수 (IOPS) | 워크로드 종속 | 스토리지 하드웨어 사양의 최대 IOPS 한계와 비교. |
| **`r_await`** | 읽기 요청 1건이 큐 대기부터 처리 완료까지 걸린 평균 시간 (ms) | `< 5.0ms` | SSD 기준 `10ms` 이상 시 디스크 읽기 병목. DB 인덱스 누락 점검. |
| **`w_await`** | 쓰기 요청 1건이 큐 대기부터 처리 완료까지 걸린 평균 시간 (ms) | `< 5.0ms` | `20ms` 초과 시 대량 로그 쓰기, 디스크 flush 지연 의심. |
| **`aqu-sz`** | 디스크 드라이버 요청 큐에서 대기 중인 평균 I/O 요청 개수 | `0 ~ 2` | `aqu-sz > 10`: 스토리지가 요청을 제때 비워내지 못하고 적체됨. |
| **`%util`** | I/O 요청이 디바이스에 전달되어 활성 상태였던 시간 백분율 | `< 70%` | `100%`에 근접하면 디스크 장치 포화. (단, 병렬 처리가 가능한 고성능 NVMe는 `await`를 병행 확인) |

---

#### 4) `ss -s` & `ip -s link`
```bash
ss -s
ip -s link show eth0
```

```text
Total: 3
TCP:   38 (estab 0, closed 37, orphaned 0, timewait 0)

Transport Total     IP        IPv6
UDP	  1         1         0        
TCP	  1         1         0        

2: eth0@if130: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default 
    link/ether f2:ee:4b:cc:f5:17 brd ff:ff:ff:ff:ff:ff link-netnsid 0
    RX:  bytes packets errors dropped  missed   mcast           
          1256      14      0       0       0       0 
    TX:  bytes packets errors dropped carrier collsns           
           126       3      0       0       0       0 
```

| 열/필드 | 기술적 의미 | 이상 징후 판단 및 조치 방향 |
| :--- | :--- | :--- |
| **`TCP: estab`** | 현재 활성화되어 패킷을 주고받는 정식 TCP 연결 수 | 트래픽 규모 대비 급격한 증감 여부 모니터링. |
| **`TCP: timewait`** | 능동적 종료(Active Close) 후 2MSL(60초) 동안 대기 중인 소켓 수 | 수천~수만 개로 치솟을 경우 로컬 포트 고갈(`net.ipv4.tcp_tw_reuse` 적용 필요). |
| **`RX/TX: errors`** | 인터페이스 계층에서 감지된 물리/논리 패킷 전송 오류 수 | `> 0`: 케이블 불량, 드라이버 버그, MTU 불일치로 인한 패킷 손상. |
| **`RX/TX: dropped`** | 커널 수신 링 버퍼(Ring Buffer)가 꽉 차서 버려진 패킷 수 | 패킷 유입 속도가 CPU/커널 처리 속도를 초과함 (`ethtool -g`로 링버퍼 확장 필요). |

---

## 2. CPU & 프로세스 상태 분석 (CPU & Processes)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **CPU 아키텍처** | `lscpu \| grep -E "Model name\|CPU\(s\):"` | 논리 코어 수, 소켓 수 및 가상화 여부 확인 |
| **CPU 상위 프로세스** | `ps aux --sort=-%cpu \| head -n 11` | CPU 점유율 최상위 10개 프로세스(PID, 소유자, 명령행) 정렬 |
| **스레드별 계측** | `pidstat -p <PID> -t 1 3` | 멀티스레드 애플리케이션의 특정 워커 스레드 병목 식별 |
| **컨텍스트 스위칭** | `pidstat -w 1 3` | 자발적(`cswch/s`) vs 비자발적(`nvcswch/s`) 스위칭 과부하 진단 |
| **D 상태 프로세스** | `ps -eo pid,ppid,state,wchan:20,comm \| awk '$3=="D"'` | I/O 대기로 인해 시그널을 받지 못하는 프로세스 및 커널 대기 함수(`wchan`) 탐색 |
| **좀비 프로세스** | `ps -eo pid,ppid,state,comm \| awk '$3=="Z"'` | 종료 후 부모 프로세스가 회수하지 않은 `<defunct>` 좀비 탐색 |
| **정상 종료 시그널** | `kill -15 <PID>` | 리소스 정리 및 커넥션 풀 반환을 보장하는 Graceful Shutdown |
| **강제 종료 시그널** | `kill -9 <PID>` | 프로세스가 무응답일 때 최후의 수단으로 커널이 즉각 사살 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `ps aux --sort=-%cpu | head -n 6`
```bash
ps aux --sort=-%cpu | head -n 6
```

```text
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root           1  0.0  0.0   4044   288 pts/0    Ss+  15:17   0:00 bash -c trap 'exit 0' SIGTERM; sleep infinity & wait
root           6  0.0  0.0   2280   120 pts/0    S+   15:17   0:00 sleep infinity
root           7  0.0  0.0   4308  1744 pts/1    Ss+  15:22   0:00 bash
root          50  0.0  0.0   7640  3676 pts/2    R+   16:28   0:00 ps aux --sort=-%cpu
```

| 열(Column) | 기술적 의미 | 분석 가이드 |
| :--- | :--- | :--- |
| **`%CPU`** | 프로세스가 실행된 전체 시간 중 CPU를 사용한 비율 | 멀티코어 환경에서는 코어당 100%이므로 4코어 100% 사용 시 400%로 표기될 수 있음. |
| **`VSZ`** | 프로세스가 커널에 요청한 총 가상 메모리 크기 (KiB) | 물리 RAM 할당 여부와 무관하므로 메모리 누수 지표로 직접 사용 금지. |
| **`RSS`** | 프로세스가 물리 RAM에 점유 중인 크기 (KiB) | **메모리 사용량의 기준.** 공유 라이브러리가 포함됨. |
| **`STAT`** | 프로세스 상태 코드 (`R`, `S`, `D`, `Z`, `T`) | - `R`: 실행 중<br>- `S`: 인터럽트 가능 슬립 (대부분의 정상 데몬)<br>- `D`: 인터럽트 불가 블록 I/O 대기<br>- `Z`: 부모가 회수하지 않은 좀비 |

---

## 3. 메모리 & OOM 킬러 진단 (Memory & OOM)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **세부 메모리 통계** | `cat /proc/meminfo \| grep -E "MemTotal\|MemFree\|MemAvailable\|Buffers\|Cached\|Dirty"` | 더티 페이지(`Dirty`), 활성/비활성 메모리 분할 현황 조회 |
| **PSS 정밀 측정** | `smem -t -k -s pss -r \| head -n 10` | 공유 라이브러리 중복을 나눈 비례 분할 물리 메모리(PSS) 측정 |
| **OOM 로그 추적** | `journalctl -k --grep="Out of memory" --since "1 hour ago"` | 커널이 메모리 고갈로 사살한 프로세스 기록 조회 |
| **OOM 점수 확인** | `cat /proc/<PID>/oom_score` | 0~1000 사이의 OOM Killer 사살 우선순위 확인 |
| **OOM 보호 설정** | `echo -1000 > /proc/<PID>/oom_score_adj` | 핵심 데몬을 OOM Killer 사살 대상에서 영구 제외 (-1000) |
| **캐시 강제 비우기** | `sync && echo 3 > /proc/sys/vm/drop_caches` | 테스트 목적으로 페이지 캐시 및 dentry/inode 캐시 플러시 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `smem -t -k -s pss -r | head -n 6`
```bash
smem -t -k -s pss -r | head -n 6
```

```text
  PID User     Command                         Swap      USS      PSS      RSS 
   56 root     /usr/bin/python3 /usr/bin/s        0    11.9M    12.4M    13.3M 
   36 root     bash -c 
echo "=== UPTIME =        0     1.2M     1.9M     3.0M 
    7 root     bash                               0   844.0K     1.1M     1.7M 
   57 root     head -n 6                          0   132.0K   472.0K     1.2M 
```

| 지표 | 기술적 의미 | 차이점 및 실무 분석 가이드 |
| :--- | :--- | :--- |
| **`USS`** (Unique Set Size) | 해당 프로세스만이 독점적으로 점유하는 물리 메모리 | 프로세스가 종료될 때 **시스템으로 즉시 온전히 반환되는 메모리 크기**. |
| **`PSS`** (Proportional Set Size) | USS + (공유 메모리 / 공유 프로세스 수) | **[가장 신뢰할 수 있는 지표]** 다중 워커 프로세스 환경에서 물리 RAM 기여도를 왜곡 없이 합산 가능. |
| **`RSS`** (Resident Set Size) | 프로세스가 참조하는 모든 물리 페이지 크기 (공유 라이브러리 포함) | 여러 프로세스가 공유하는 `libc` 등이 중복 집계되므로 전체 합산 시 물리 RAM 크기보다 크게 나타남. |

---

## 4. 스토리지 I/O & 파일시스템 트러블슈팅 (Disk I/O & Storage)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **Inode 고갈 검사** | `df -hi -x tmpfs -x devtmpfs` | 용량이 남아 있어도 파일 생성이 불가능한 Inode 100% 여부 확인 |
| **폴더별 용량 순위** | `du -h --max-depth=1 /var/log 2>/dev/null \| sort -hr \| head -n 10` | 디스크 공간을 가장 많이 잠식한 상위 디렉터리 식별 |
| **I/O 발생 프로세스** | `iotop -o -b -n 3` | 디스크 읽기/쓰기를 지속적으로 일으키는 프로세스 필터링 |
| **삭제된 열린 파일** | `lsof +L1` | `rm` 되었으나 프로세스가 잡고 있어 디스크 용량을 물고 있는 파일 검색 |
| **무중단 용량 회수** | `: > /proc/<PID>/fd/<FD>` | 프로세스 재시작 없이 Unlinked 파일 크기를 0으로 즉시 Truncate |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `df -hi -x tmpfs -x devtmpfs` & `lsof +L1`
```bash
df -hi -x tmpfs -x devtmpfs
lsof +L1
```

```text
Filesystem     Inodes IUsed IFree IUse% Mounted on
overlay             0     0     0     - /
mac              720M  4.2M  716M    1% /workspace
/dev/vdb1           0     0     0     - /etc/hosts

COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NLINK   NODE NAME
python3    1  root    7u   REG   0,52 52428800     0 123456 /tmp/tmpki2_raa3 (deleted)
```

| 지표/필드 | 기술적 의미 | 이상 징후 판단 및 조치 방향 |
| :--- | :--- | :--- |
| **`IUse%`** | 파일시스템의 총 Inode 중 사용 중인 메타데이터 비율 | **`IUse% == 100%`**이면 디스크 공간(GB)이 남아 있어도 `No space left on device` 에러 발생. 소형 임시 파일 삭제 필요. |
| **`NLINK == 0`** | 디렉터리 트리에서 링크가 끊어진(삭제된) 파일 | `(deleted)` 표기가 붙으며, 프로세스가 파일 핸들을 닫지 않아 디스크 블록이 해제되지 못함. |
| **`FD: 7u`** | 프로세스가 열고 있는 파일 디스크립터 번호(7번, 읽기/쓰기 모드) | `: > /proc/1/fd/7` 리다이렉션으로 서비스 중단 없이 용량 즉각 0바이트로 회수. |

---

## 5. 네트워크 스택 & 소켓 진단 (Network & Sockets)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **LISTEN 포트/프로세스**| `ss -tulpn` | 수신 대기 중인 모든 TCP/UDP 포트 및 담당 프로세스(PID) 조회 |
| **TCP 상태별 집계** | `ss -tan \| awk '{print $1}' \| sort \| uniq -c` | ESTAB, TIME_WAIT, CLOSE_WAIT 소켓 누수 수치 집계 |
| **L7 레이턴시 분해** | `/workspace/examples/basic-app/scripts/network_latency_benchmark.sh <URL>` | DNS, TCP, TLS, TTFB 구간별 지연 마이크로초 단위 분해 |
| **SYN 패킷 캡처** | `tcpdump -i any "tcp[tcpflags] & (tcp-syn) != 0" -nn -c 10` | 3-Way Handshake 신규 연결 인입률 실시간 관측 |
| **DNS 재귀 경로** | `dig +trace <domain>` | 루트 네임서버부터 권한 네임서버까지 단계별 위임 지연 추적 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `ss -tulpn`
```bash
ss -tulpn
```

```text
Netid  State   Recv-Q  Send-Q   Local Address:Port    Peer Address:Port Process 
udp    UNCONN  0       0           127.0.0.11:59974        0.0.0.0:*            
tcp    LISTEN  0       4096        127.0.0.11:42445        0.0.0.0:*            
```

| 열(Column) | 기술적 의미 (LISTEN 소켓 기준) | 정상 기준 | 이상 징후 판단 및 조치 방향 |
| :--- | :--- | :---: | :--- |
| **`Send-Q`** | 커널이 허용한 백로그(Backlog) 큐 최대 크기 | `somaxconn` 값 | 시스템 `net.core.somaxconn` 및 애플리케이션 `listen(backlog)` 설정값. |
| **`Recv-Q`** | 3-Way Handshake 완료 후 커널 Accept 큐에서 대기 중인 연결 수 | `0` | **`Recv-Q > 0` 또는 `Recv-Q >= Send-Q`**: 백엔드 프로세스가 `accept()`를 제때 처리하지 못해 신규 연결이 드롭(Drop)되는 치명적 병목 상태. |

---

## 6. 시스템 콜(Syscall) 추적 & 프로세스 디버깅 (strace & Debugging)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **시스템 콜 통계 요약** | `strace -c <command>` | 시스템 콜별 호출 빈도, 에러 수, 시간 점유율 요약 표 출력 |
| **프로세스 실시간 부착** | `strace -p <PID> -f` | 실행 중인 프로세스의 모든 자식 스레드 시스템 콜 실시간 출력 |
| **카테고리별 필터링** | `strace -p <PID> -f -e trace=network,file -s 256` | 불필요한 시스템 콜을 배제하고 네트워크/파일 I/O만 추적 |
| **소요 시간 정밀 계측** | `strace -p <PID> -f -T -t` | 각 시스템 콜이 지연된 시간(`<소요초>`)을 마이크로초 단위로 계측 |
| **열린 소켓/파일 조회** | `lsof -p <PID>` | 특정 프로세스가 열고 있는 소켓, 파이프, 일반 파일 목록 전수 조사 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `strace -c curl -s http://chaos-target:8000/health > /dev/null`
```bash
strace -c curl -s http://chaos-target:8000/health > /dev/null
```

```text
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 24.90    0.000451          11        40         4 openat
 18.88    0.000342           7        43           read
 12.70    0.000230          32         7           ppoll
 11.37    0.000206           1       109           mmap
  7.34    0.000133           2        65           mprotect
  5.08    0.000092          30         3         3 connect
  4.14    0.000075           1        44           close
  0.11    0.000002           2         1           recvfrom
------ ----------- ----------- --------- --------- ----------------
100.00    0.001811           3       526        10 total
```

| 열(Column) | 기술적 의미 | 분석 및 실무 디버깅 가이드 |
| :--- | :--- | :--- |
| **`% time`** | 전체 시스템 콜 실행 시간 중 해당 시스템 콜이 차지한 비율 | 지연 시간 비중이 가장 높은 상위 시스템 콜 식별. |
| **`seconds`** | 해당 시스템 콜에 소요된 누적 시간 (초) | 커널 공간에 체류한 총 소요 시간. |
| **`usecs/call`** | 1회 호출당 평균 지연 시간 (마이크로초) | 특정 시스템 콜(예: `connect`, `futex`, `read`)이 블로킹되는지 판별. |
| **`errors`** | 시스템 콜 실패 횟수 (반환값 < 0) | `openat` 오류(경로 부재: `ENOENT`), `connect` 오류(거부: `ECONNREFUSED` / 타임아웃: `ETIMEDOUT`) 즉시 포착. |

---

## 7. 서비스 관리 & 로그 분석 (Systemd & Logs)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **실패 유닛 일괄 검색** | `systemctl --failed` | 부팅 또는 운영 중 비정상 중단(Failed)된 서비스 유닛 스캔 |
| **서비스 상세 상태** | `systemctl status <service>` | 프로세스 트리, cgroup 리소스 점유 및 최근 로그 확인 |
| **에러 로그 정밀 필터** | `journalctl -p err..emerg -b` | 현재 부팅 세션 중 에러 이상 등급(`err`, `crit`, `alert`, `emerg`) 로그만 출력 |
| **실시간 로그 팔로우** | `journalctl -u <service> -f` | 특정 서비스의 실시간 stdout/stderr 로그 스트리밍 |
| **저널 디스크 정리** | `journalctl --vacuum-size=1G` | 1GB를 초과하는 오래된 시스템 저널 아카이브 정리 |

---

## 8. 커널 파라미터 & 리소스 한도 (Kernel Tuning & ulimits)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **소켓 백로그 튜닝** | `sysctl -w net.core.somaxconn=65535` | 고트래픽 유입 시 accept 대기 큐 드롭 방지 (동적 반영) |
| **포트 재사용 활성화** | `sysctl -w net.ipv4.tcp_tw_reuse=1` | TIME_WAIT 소켓을 신규 송신 연결에 즉각 재할당 허용 |
| **시스템 전체 FD 한도** | `sysctl fs.file-max` | OS 커널이 관리할 수 있는 총 파일 디스크립터 상한선 확인 |
| **실행 중 프로세스 한도**| `prlimit --pid <PID> --nofile=65536:65536` | **프로세스 무중단**으로 파일 디스크립터 오픈 한도 즉각 확장 |
| **쉘 오픈 파일 한도** | `ulimit -n` | 현재 사용자 세션의 소프트 오픈 파일 디스크립터 한도 확인 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `sysctl` & `prlimit --pid 1 --nofile`
```bash
sysctl net.core.somaxconn net.ipv4.tcp_tw_reuse fs.file-max vm.swappiness
prlimit --pid 1 --nofile
```

```text
net.core.somaxconn = 4096
net.ipv4.tcp_tw_reuse = 2
fs.file-max = 9223372036854775807
vm.swappiness = 20

RESOURCE DESCRIPTION               SOFT    HARD UNITS
NOFILE   max number of open files 20480 1048576 files
```

| 파라미터 / 지표 | 권장값 (고성능 백엔드) | 운영 영향 및 주의점 |
| :--- | :---: | :--- |
| **`net.core.somaxconn`** | `65535` | 기본값(128 또는 4096)이 낮으면 트래픽 스파이크 발생 시 연결 요청이 유실됨. |
| **`net.ipv4.tcp_tw_reuse`** | `1` | Outbound 외부 API 호출이 잦은 환경에서 포트 고갈(`EADDRNOTAVAIL`) 방지. |
| **`vm.swappiness`** | `10` 또는 `1` | 스왑 파티션 사용 성향. 지연 시간에 민감한 DB나 캐시 서버는 낮게 설정. |
| **`NOFILE: SOFT`** | `65536` | 프로세스가 열 수 있는 파일/소켓 한도. `1024`로 방치 시 대규모 트래픽에서 `Too many open files` 에러 발생. |
| **`NOFILE: HARD`** | `1048576` | root 권한 없이 SOFT 한도를 스스로 올릴 수 있는 최대 상한선. |

---

## 9. 패키지 관리 & 저장소 트러블슈팅 (Package Management & Repositories)

### 📋 빠른 진단 원라이너 요약표
| 분석 항목 | 명령어 | 핵심 관측 목적 |
| :--- | :--- | :--- |
| **바이너리 출처 역추적** | `dpkg -S $(which <cmd>)` | 특정 실행 파일 또는 라이브러리를 설치한 원본 deb 패키지명 식별 |
| **설치 파일 목록 조회** | `dpkg -L <package>` | 특정 패키지가 시스템에 배치한 모든 실행 파일, 설정 파일, 문서 경로 확인 |
| **패키지 버전 고정** | `apt-mark hold <package>` | 프로덕션 배포 시 `apt upgrade`로 인한 의도치 않은 메이저 판올림 방지 |
| **버전 고정 목록 확인** | `apt-mark showhold` | 현재 버전이 고정되어 업데이트가 잠겨 있는 패키지 목록 조회 |
| **잠금 파일 점유자 확인** | `fuser /var/lib/dpkg/lock-frontend` | `Could not get lock` 에러 발생 시 dpkg 락을 잡고 있는 프로세스 PID 탐색 |
| **패키지 캐시 완전 정리** | `apt-get clean && apt-get autoremove --purge -y` | `/var/cache/apt/archives/` deb 캐시 및 불필요 라이브러리 삭제로 디스크 회수 |

---

### 🔍 실행 결과 및 지표 상세 해석

#### `dpkg -S $(which curl)`
```bash
dpkg -S $(which curl)
```

```text
curl: /usr/bin/curl
```

| 진단 상황 | 권장 명령어 | 실무 해결 가이드 |
| :--- | :--- | :--- |
| **알 수 없는 바이너리 정체 확인** | `dpkg -S /usr/lib/x86_64-linux-gnu/libssl.so*` | 시스템에 배포된 라이브러리 파일이 공식 패키지인지, 수동 빌드된 미확인 파일인지 즉시 검증. |
| **메이저 버전 업데이트 방지** | `apt-mark hold nginx redis-server` | OS 정기 보안 패치 적용 시 애플리케이션 서비스 컴포넌트가 임의 갱신되어 다운타임이 발생하는 사태 차단. |
| **패키지 락 충돌 해소** | `fuser /var/lib/dpkg/lock-frontend`<br>`kill -15 <PID>` | 백그라운드 프로세스가 종료되지 않고 남아 락을 쥐고 있을 때, 프로세스를 정상 종료 후 `dpkg --configure -a` 실행. |
