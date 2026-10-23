# 00. Docker 기반 시스템 진단 랩 환경 구축 및 도구 체계화

## 🎯 학습 목표 (Goal)
- 호스트 OS에 영향을 주지 않고 안전하게 시스템 콜 추적, 커널 파라미터 조작, 네트워크 패킷 캡처를 수행할 수 있는 격리된 Docker 기반 진단 랩을 구축합니다.
- 시스템 이상 징후를 진단할 때 기본이 되는 `procps`, `sysstat`, `iproute2` 패키지의 설치 여부와 동작을 검증합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 왜 컨테이너 샌드박스에서 실습을 진행하는가?
일반적인 애플리케이션 개발과 달리, 시스템 레벨의 진단 및 장애 대응 실습은 다음과 같은 운영체제 레벨의 위험 요소를 포함합니다:
1. **커널 파라미터 튜닝**: `sysctl`을 통한 파일 디스크립터 한도나 TCP 버퍼 설정 조작
2. **패킷 캡처 및 인터페이스 조작**: `tcpdump`, `iptables`, `tc`(Traffic Control)를 통한 네트워크 지연 주입
3. **시스템 리소스 고갈**: 의도적인 OOM(Out of Memory) 유발, CPU 100% 포화, Inode 고갈

개인 PC(macOS 또는 로컬 Linux)의 호스트 환경에서 이를 직접 실행하면 작업 중이던 애플리케이션이 강제 종료되거나 네트워크가 단절될 수 있습니다. 본 실습에서는 Docker Compose를 통해 **진단 서버(`linux-lab`)**와 **장애 주입 대상 웹 서버(`chaos-target`)**를 완전 격리된 가상 네트워크(172.28.0.0/16)에 배치하여 안전한 실습 환경을 제공합니다.

### 리눅스 핵심 4대 진단 툴킷
| 패키지명 | 주요 포함 명령어 | 진단 대상 계층 |
| :--- | :--- | :--- |
| **procps** | `ps`, `top`, `free`, `vmstat`, `pkill`, `sysctl` | 프로세스 스케줄링, 가상 메모리, 커널 상태 |
| **sysstat** | `iostat`, `mpstat`, `pidstat`, `sar` | CPU 코어별 점유율, 스토리지 I/O 대기시간(%util, await) |
| **iproute2** | `ip`, `ss` | 네트워크 인터페이스 상태, TCP/UDP 소켓 버퍼 및 연결 수 |
| **util-linux / lsof** | `lsof`, `fuser`, `lscpu`, `dmesg`, `prlimit` | 파일 디스크립터 누수, 커널 하드웨어 링버퍼, 리소스 한도 |

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 실습 환경 기동 및 컨테이너 상태 확인
프로젝트 루트 디렉터리에서 `docker-compose.yml`을 기반으로 실습 클러스터를 빌드하고 실행합니다.

```bash
# 1. 백그라운드에서 컨테이너 빌드 및 구동
docker compose up -d --build

# 2. 실행 중인 컨테이너 확인 (linux-lab 및 chaos-target이 'Up' 상태여야 함)
docker compose ps
```

*출력 예시:*
```text
NAME           IMAGE                      COMMAND                  SERVICE        CREATED         STATUS         PORTS
chaos-target   learning-linux-chaos-target "uvicorn app.main:ap…"   chaos-target   5 seconds ago   Up 4 seconds   0.0.0.0:8000->8000/tcp
linux-lab      learning-linux-linux-lab   "bash -c 'trap 'exit…"   linux-lab      5 seconds ago   Up 4 seconds   
```

### Step 2. 메인 분석 컨테이너(linux-lab) 쉘 진입

```bash
# linux-lab 컨테이너의 bash 쉘로 접속
docker compose exec linux-lab bash
```

접속 후 프롬프트가 `root@linux-lab:/workspace#` 형태로 변경되는지 확인합니다.

### Step 3. 필수 분석 명령어 바이너리 유효성 검증
컨테이너 내부에서 표준 시스템 진단 도구들이 올바르게 배치되어 있는지 확인합니다.

```bash
# 각 진단 도구의 바이너리 경로 및 버전 확인
which uptime free vmstat mpstat iostat pidstat ss ip tcpdump strace
```

*검증 쉘 스크립트 실행:*
```bash
# 도구 체크 일괄 실행 스크립트
for tool in uptime free vmstat mpstat iostat pidstat ss ip tcpdump strace lsof; do
    if command -v $tool >/dev/null 2>&1; then
        echo "[OK] $tool 사용 가능"
    else
        echo "[FAIL] $tool 누락됨"
    fi
done
```

### Step 4. 타깃 애플리케이션과의 가상 네트워크 통신 확인
`linux-lab` 컨테이너(172.28.0.10)에서 `chaos-target` 컨테이너(172.28.0.20:8000)로 HTTP 요청을 보내 통신 상태를 확인합니다.

```bash
# 1. DNS 이름 리졸빙 및 HTTP 통신 확인
curl -s http://chaos-target:8000/health | jq .

# 2. 타깃 컨테이너의 현재 시스템 리소스 지표 수신
curl -s http://chaos-target:8000/metrics/process | jq .
```

*출력 예시:*
```json
{
  "pid": 1,
  "ppid": 0,
  "cpu_percent": 0.0,
  "threads_count": 1,
  "open_file_descriptors": 5,
  "memory_rss_bytes": 35241984,
  "memory_rss_mb": 33.61,
  "memory_vms_mb": 112.45,
  "leaked_memory_chunks_count": 0,
  "leaked_fds_count": 0,
  "unlinked_files_count": 0
}
```

---

## 🎯 마무리 및 다음 단계

이제 안전하게 시스템을 모니터링하고 부하를 유발할 수 있는 격리 샌드박스가 완성되었습니다.

다음 단계인 **[01-package-management.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/01-package-management.md)**에서는 **DPKG와 APT의 계층 아키텍처**, 최신 GPG 키링 기반 저장소 격리, 프로덕션 버전 고정(`apt-mark hold`), 그리고 패키지 잠금 파일(`lock-frontend`) 충돌 해소 기법을 실습합니다.
