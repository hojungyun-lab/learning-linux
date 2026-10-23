# 13. [종합 실전] 프로덕션 복합 장애 대응 플레이북

## 🎯 학습 목표 (Goal)
- 단일 지표 오류가 아닌 CPU 스파이크, 메모리 누수, 디스크 용량 잠식, 소켓 대기가 동시다발적으로 발생하는 **복합 시스템 장애(Multi-fault Incident)** 상황을 체계적으로 격리하고 진단합니다.
- 긴급 장애 상황에서 증거를 훼손하지 않고 비파괴적(Non-destructive)으로 시스템을 복구하는 **5단계 인시던트 트러블슈팅 프레임워크**를 완수합니다.
- 재발 방지를 위한 정량적 **사후 분석 보고서(Post-mortem)** 작성 템플릿과 방법론을 정립합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 5단계 시스템 장애 트러블슈팅 프레임워크

```text
[1단계: 상황 전파 및 영향 격리]
       │  - 사용자 트래픽 우회 (Health Check 실패 처리 또는 가중치 0 조정)
       ▼
[2단계: 시스템 60초 긴급 스캔 (USE 방법론)]
       │  - CPU: uptime, mpstat, pidstat
       │  - 메모리: free, vmstat, dmesg
       │  - 스토리지: df -h, df -i, lsof +L1, iostat
       │  - 네트워크: ss -s, ss -tulpn
       ▼
[3단계: 가설 수립 및 원인 프로세스 추적]
       │  - 특정 PID의 비정상 동작 식별
       │  - strace 및 /proc/<PID>/fd 분석
       ▼
[4단계: 무중단 응급 조치 (Mitigation)]
       │  - 리소스 한도 상향 (prlimit)
       │  - Unlinked 파일 Truncate (: > /proc/<PID>/fd/<FD>)
       │  - Graceful Shutdown (kill -15)
       ▼
[5단계: 근본 원인 분석 및 사후 보고서(Post-mortem) 작성]
```

---

## 🛠️ 실습 코드: 복합 장애 시뮬레이션 모의훈련 (Hands-on)

### Phase 1. 복합 장애 동시 주입
`chaos-target` 서버에 3가지 주요 장애(Unlinked 파일 점유, 좀비 프로세스 발생, 응답 지연)를 동시에 발생시킵니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 50MB 언링크 파일 생성 (디스크 공간 잠식)
curl -s -X POST "http://chaos-target:8000/chaos/disk-unlinked?size_mb=50" | jq .

# 2. 좀비 프로세스 5개 생성
curl -s -X POST "http://chaos-target:8000/chaos/zombie?count=5" | jq .

# 3. 파일 디스크립터 20개 누수 유발
curl -s -X POST "http://chaos-target:8000/chaos/fd-leak?count=20" | jq .
```

---

### Phase 2. 60초 긴급 점검 수행
이상 징후를 빠르게 식별하기 위해 표준 명령어를 순차 실행합니다.

```bash
# 1. CPU 로드 및 대기 큐 확인
uptime && vmstat 1 3

# 2. 메모리 점유 및 최근 OOM 이벤트 검색
free -h && dmesg -T | grep -i oom | tail -n 5

# 3. 디스크 용량 및 Inode 상태 확인
df -hT -x tmpfs -x devtmpfs
df -hi -x tmpfs -x devtmpfs

# 4. 좀비 프로세스 존재 여부 확인
ps -eo pid,ppid,state,comm | awk '$3=="Z"'
```

---

### Phase 3. 심층 원인 분석 및 식별

#### [진단 1] 삭제된 파일의 디스크 점유 확인
```bash
# 링크 카운트가 0이면서 열려 있는 파일 탐색
lsof +L1
```
- **발견 사항**: `chaos-target` 프로세스(PID 1)가 삭제된 임시 파일을 계속 열고 있어 디스크 용량을 반환하지 않고 있음을 확인.

#### [진단 2] 파일 디스크립터 사용량 급증 확인
```bash
# 타깃 프로세스가 열고 있는 파일 디스크립터 목록 확인
ls -l /proc/1/fd | wc -l
```
- **발견 사항**: 일반적인 수준을 초과하여 비정상적으로 많은 파일 디스크립터가 점유되어 있음.

---

### Phase 4. 단계별 비파괴 응급 조치 (Mitigation)

#### [조치 1] 서비스 재시작 없이 디스크 공간 즉시 확보
```bash
# lsof +L1 에서 식별된 FD 번호(예: 7번)를 프로세스 무중단으로 Truncate
: > /proc/1/fd/7

# 공간 회수 여부 재검증
lsof +L1
```

#### [조치 2] 부모 프로세스에 자식 수거 요청 및 정상화
```bash
# 애플리케이션의 리셋 엔드포인트를 호출하여 누수 핸들 일괄 정리
curl -s -X POST "http://chaos-target:8000/chaos/reset" | jq .

# 정상 상태 복귀 확인
curl -s "http://chaos-target:8000/metrics/process" | jq .
```

---

## 📋 사후 분석 보고서 (Post-mortem) 템플릿

장애 조치 후 조직의 학습과 재발 방지를 위해 작성하는 표준 보고서 양식:

```markdown
# [인시던트 보고서] 2026-10-22 API 서버 디스크 점유 및 FD 누수 장애

## 1. 개요 (Summary)
- 발생 일시: 2026-10-22 13:40 KST
- 해결 일시: 2026-10-22 13:55 KST (총 소요 시간: 15분)
- 영향 범위: chaos-target 서비스의 신규 파일 오픈 지연 및 디스크 경보 발생

## 2. 장애 타임라인 (Timeline)
- 13:40: 디스크 사용률 90% 초과 모니터링 경보 인입
- 13:43: 엔지니어 1차 점검 실시, `du`와 `df`의 용량 불일치 확인
- 13:46: `lsof +L1` 진단을 통해 프로세스가 잡고 있는 Unlinked 임시 파일(50MB) 식별
- 13:50: `/proc/1/fd/7` Truncate를 통해 서비스 무중단으로 디스크 공간 긴급 회수
- 13:55: 애플리케이션 리셋 및 FD 정상화 완료

## 3. 근본 원인 (Root Cause)
- 임시 파일 처리 로직에서 예외 발생 시 `file.close()`가 호출되지 않아 파일 디스크립터가 열린 채 방치됨.
- 프로세스가 종료되지 않는 한 OS가 디스크 블록을 회수할 수 없는 상태가 지속됨.

## 4. 재발 방지 대책 (Action Items)
1. [코드 수정] Python `with tempfile.NamedTemporaryFile(...) as f:` 컨텍스트 매니저를 강제 적용하여 예외 발생 시에도 자동 `close()` 보장.
2. [모니터링 강화] `node_exporter`의 파일 디스크립터 할당률(`process_open_fds / process_max_fds`) 70% 초과 시 사전 알림 등록.
3. [커널 한도 점검] 고트래픽 서비스 유닛 파일에 `LimitNOFILE=65536` 적용 확인.
```

---

## 🎯 전체 커리큘럼 완주를 축하합니다!

총 14단계(00 ~ 13)의 실전 엔지니어링 과정을 통해:
1. **패키지 관리 아키텍처 및 DPKG/APT 저장소 보안**
2. **프로세스 생명주기 및 시그널 제어**
3. **CPU 로드 애버리지와 컨텍스트 스위칭 진단**
4. **가상 메모리 VIRT/RES/PSS와 OOM Killer 방어**
5. **스토리지 Inode 및 Unlinked 파일 공간 회수**
6. **TCP 소켓 상태 머신 및 L4 패킷 분석**
7. **DNS 파이프라인 및 L7 레이턴시 분해 계측**
8. **systemd 서비스 아키텍처와 journalctl 정밀 검색**
9. **시스템 콜(Syscall) 추적과 strace 오버헤드 제어**
10. **Linux Capabilities를 활용한 권한 격리**
11. **Namespaces와 cgroups v2를 통한 컨테이너 내부 원리 구현**
12. **고성능 커널 파라미터(`sysctl`) 튜닝 및 `prlimit` 무중단 확장**
13. **복합 인시던트 대응 프레임워크와 사후 보고서 수립**

까지 운영체제와 커널 전 계층을 아우르는 탄탄한 실전 시스템 엔지니어링 역량을 확립했습니다.
