# 08. 서비스 관리와 구조화된 시스템 로그 분석

## 🎯 학습 목표 (Goal)
- Linux init 시스템인 `systemd`의 핵심 아키텍처와 유닛(Unit) 생명주기를 이해합니다.
- 백엔드 데몬을 안정적으로 운영하기 위한 표준 `.service` 유닛 파일 작성 규칙(자동 재시작, 리소스 한도, 정상 종료 타임아웃)을 습득합니다.
- 바이너리 인덱싱 기반의 구조화된 로깅 시스템인 `journalctl`을 사용하여 **우선순위(Priority)별, 서비스별, 특정 시점별 장애 로그를 신속히 필터링**하는 기법을 마스터합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. systemd와 서비스 유닛(Unit) 파일 구조
현대 Linux 배포판에서 PID 1로 동작하는 `systemd`는 의존성 기반 병렬 부팅과 cgroup 기반 프로세스 그룹 관리를 수행합니다. 프로덕션 서비스 유닛은 다음 3대 섹션으로 구성됩니다:

```ini
[Unit]
Description=Production API Service
After=network.target remote-fs.target
Wants=network-online.target

[Service]
Type=simple
User=appuser
Group=appgroup
WorkingDirectory=/var/www/app
ExecStart=/usr/local/bin/python3 main.py
ExecReload=/bin/kill -HUP $MAINPID

# 프로세스 장애 시 자동 복구 정책
Restart=on-failure
RestartSec=5s

# 정상 종료(Graceful Shutdown) 보장 시간
TimeoutStopSec=30s
KillMode=mixed

# 프로세스 레벨 리소스 한도 (ulimit 대체)
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
```

- **`Restart=on-failure`**: 프로세스가 정상 종료(`exit 0` 또는 허용된 시그널)된 경우에는 재시작하지 않고, 비정상 에러 코드로 종료되거나 SIGSEGV/SIGKILL 등으로 크래시된 경우에만 5초 대기 후 자동 재시작합니다.
- **`TimeoutStopSec=30s`**: `systemctl stop` 명령 시 먼저 `SIGTERM`을 보내고, 30초 내에 트랜잭션을 끝내지 못하면 커널이 `SIGKILL`을 보내도록 보장합니다.

### 2. journald의 로그 우선순위 레벨 (RFC 5424 Syslog 기준)
`journalctl -p` 옵션에 사용할 수 있는 8가지 표준 로그 수준:

| 숫자 | 레벨명 | 설명 및 사용 시점 |
| :---: | :--- | :--- |
| **0** | `emerg` | 시스템 전체를 사용할 수 없는 치명적 상태 (Kernel Panic 등) |
| **1** | `alert` | 즉각적인 조치가 필요한 긴급 상황 (데이터베이스 손상 등) |
| **2** | `crit` | 심각한 하드웨어 또는 핵심 컴포넌트 오류 |
| **3** | `err` | 일반적인 오류 상태 (요청 처리 실패, 파일 열기 실패 등) |
| **4** | `warning` | 잠재적 오류를 유발할 수 있는 경고 상태 |
| **5** | `notice` | 정상이지만 주목할 가치가 있는 중요 이벤트 |
| **6** | `info` | 일반적인 안내 메시지 (기본값) |
| **7** | `debug` | 상세한 개발용 디버깅 메시지 |

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 서비스 상태 검사 및 실패 유닛 탐색
시스템에 등록된 서비스들의 상태를 조회합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 시스템 전반의 실패(Failed) 상태 유닛 일괄 조회
systemctl --failed

# 2. 특정 서비스 상태 및 최근 로그 요약 확인 (예: cron 또는 ssh)
systemctl status systemd-journald
```

### Step 2. journalctl 정밀 로그 필터링 실습
방대한 시스템 로그 속에서 원하는 정보만 정확히 추출하는 실전 쿼리들을 연습합니다.

```bash
# 1. 에러 수준 이상(err, crit, alert, emerg)의 로그만 출력
journalctl -p err..emerg -b

# 2. 특정 서비스 유닛의 실시간 로그 팔로우 (tail -f 와 동일)
journalctl -u systemd-journald -f

# 3. 지정한 시간 범위의 로그만 필터링 (ISO 타임스탬프)
journalctl --since "10 minutes ago"

# 4. 특정 PID가 남긴 로그만 추적
journalctl _PID=1
```

### Step 3. 커널 메시지 전용 분리 조회
애플리케이션 로그와 OS 커널 로그를 분리하여 하드웨어 및 드라이버 이상 여부를 점검합니다.

```bash
# 커널 링 버퍼 로그를 타임스탬프와 함께 출력 (-k 또는 --dmesg)
journalctl -k --since "1 hour ago"
```

### Step 4. 저널 로그 스토리지 점유율 관리
운영 중 저널 로그가 디스크 공간을 과도하게 차지하지 않도록 제어합니다.

```bash
# 1. 현재 저널 로그가 차지하는 총 디스크 용량 확인
journalctl --disk-usage

# 2. 지정한 용량(예: 500MB)을 초과하는 오래된 로그 즉시 정리
journalctl --vacuum-size=500M

# 3. 지정한 기간(예: 7일) 이전의 로그 즉시 정리
journalctl --vacuum-time=7d
```

---

## 🎯 마무리 및 다음 단계

systemd 유닛 작성 모범 사례와 journalctl을 활용한 구조화된 로그 분석 체계를 확립했습니다.

다음 단계인 **[09-system-calls-and-strace.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/09-system-calls-and-strace.md)**에서는 프로세스가 CPU를 쓰지도 않고 에러 로그도 남기지 않은 채 멈춰 있는 **무응답(Hang) 현상**의 원인을 규명하기 위해, 커널과 사용자 공간의 경계인 **시스템 콜(Syscall)을 `strace`로 실시간 추적하고 분석하는 기법**을 심층 분석합니다.
