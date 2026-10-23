# 07. DNS 조회 및 L7 애플리케이션 지연 진단

## 🎯 학습 목표 (Goal)
- Linux 시스템의 이름 해결(Name Resolution) 순서(`/etc/nsswitch.conf`, `/etc/hosts`, `/etc/resolv.conf`)와 동작 원리를 파악합니다.
- `dig`를 활용해 DNS 재귀 조회(Recursive Query) 경로 및 권한 네임서버를 추적하고, 쿠버네티스 및 분산 환경에서 빈번한 `ndots:5` 검색 도메인 병목의 구조적 원인을 이해합니다.
- `curl`의 세부 포맷팅 옵션을 통해 네트워크 구간별 소요 시간(DNS 조회, TCP 연결, TLS 핸드셰이크, TTFB)을 마이크로초 단위로 분해 계측하여 **지연이 네트워크에서 발생하는지, 백엔드 서버 로직에서 발생하는지** 격리 진단합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. Linux 이름 해결(Name Resolution) 파이프라인
프로세스가 `example.com` 도메인으로 소켓 연결을 시도할 때 커널과 C 라이브러리(glibc)는 다음 순서로 IP를 조회합니다:

1. **`/etc/nsswitch.conf`**: 호스트 검색 정책을 정의합니다 (`hosts: files dns`).
2. **`files` (/etc/hosts)**: 로컬 정적 호스트 매핑 파일을 먼저 확인합니다.
3. **`dns` (/etc/resolv.conf)**: 설정된 네임서버(`nameserver`)로 DNS 쿼리를 전송합니다.
   - `search`: 도메인 접미사 자동 완성 목록 (예: `search default.svc.cluster.local svc.cluster.local cluster.local`)
   - `options ndots:5`: 도메인 이름에 포함된 점(`.`)의 개수가 5개 미만이면, 먼저 `search` 접미사를 차례로 붙여가며 쿼리를 시도합니다. (내부 도메인이 아닌 외부 FQDN 조회 시 불필요한 DNS 쿼리가 다수 발생할 수 있는 원인)

### 2. cURL을 이용한 L7 지연 시간 분해 (Latency Breakdown)
HTTP 요청이 느릴 때 네트워크가 느린 것인지 백엔드 애플리케이션 처리가 느린 것인지를 판별하기 위해 전체 시간을 다음 5개 구간으로 분해합니다:

```text
|-- DNS Lookup (time_namelookup)
|------ TCP Connect (time_connect)
|---------- TLS Handshake (time_appconnect)
|-------------- Pre-transfer (time_pretransfer)
|------------------ Time To First Byte (time_starttransfer / TTFB)
|---------------------------------- Total Transaction Time (time_total)
```

- **네트워크 병목인 경우**: `time_namelookup`(DNS 서버 지연) 또는 `time_connect - time_namelookup`(네트워크 RTT 지연) 구간이 비정상적으로 길어집니다.
- **백엔드 서버 병목인 경우**: TCP 연결은 1~2ms 내에 끝나지만, 서버가 비즈니스 로직 및 DB 쿼리를 처리하느라 응답의 첫 바이트를 보내는 `time_starttransfer - time_pretransfer`(TTFB) 구간이 수 초 이상 길어집니다.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 리눅스 리졸버 설정 검사
현재 컨테이너의 DNS 리졸버 구성 파일을 확인합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 이름 해결 순서 확인
cat /etc/nsswitch.conf | grep hosts

# 2. DNS 네임서버 및 search 설정 확인
cat /etc/resolv.conf
```

### Step 2. dig를 이용한 DNS 재귀 조회 경로 추적
루트 네임서버부터 시작하여 도메인의 최종 권한 네임서버까지 단계별 위임 과정을 추적합니다.

```bash
# 1. 재귀 조회 전체 경로 추적
dig +trace google.com

# 2. 응답 IP만 간결히 출력
dig google.com +short

# 3. IP 주소로부터 도메인 역방향 조회 (PTR 레코드)
dig -x 8.8.8.8 +short
```

### Step 3. cURL 기반 L7 레이턴시 정밀 프로파일링
제공된 벤치마크 스크립트를 사용하여 정상 엔드포인트의 구간별 지연을 측정합니다.

```bash
# 프로젝트 벤치마크 스크립트 실행
/workspace/examples/basic-app/scripts/network_latency_benchmark.sh http://chaos-target:8000/health
```

*출력 분석:*
```text
  DNS Lookup Time       : 0.000738s  <- 로컬 DNS 해석 0.7ms 소요
  TCP Connect Time      : 0.000822s  <- 3-Way Handshake 0.8ms 소요
  TLS Handshake Time    : 0.000000s  <- HTTP 평문 연결이므로 0s
  Pre-transfer Time     : 0.000837s  <- HTTP 요청 헤더 전송 직전
  Start Transfer (TTFB) : 0.006576s  <- 첫 응답 바이트 수신(서버 로직 처리 시간 포함)
  --------------------------------------------------
  Total Time            : 0.006612s  <- 전체 요청 완료 약 6.6ms
```

### Step 4. 실전 진단: 백엔드 지연 주입 시 지표 변화 관측
`chaos-target` 서버의 의도적 지연 엔드포인트(`/chaos/slow?delay_seconds=3`)를 호출하고 지표가 어떻게 달라지는지 분석합니다.

```bash
/workspace/examples/basic-app/scripts/network_latency_benchmark.sh "http://chaos-target:8000/chaos/slow?delay_seconds=3"
```

*결과 비교:*
- `DNS Lookup` 및 `TCP Connect`는 여전히 **1ms 미만**을 유지합니다.
- 반면 `Start Transfer (TTFB)`가 **3.007초**로 급증합니다.
- **결론**: 네트워크 회선이나 라우팅 문제가 아니라, 백엔드 애플리케이션의 내부 로직 처리(DB 쿼리 지연, 락 경합 등)에서 병목이 발생했음을 단번에 입증할 수 있습니다.

---

## 🎯 마무리 및 다음 단계

DNS 해석 파이프라인의 구조와 cURL을 활용한 L7 레이턴시 분해 진단법을 완성했습니다.

다음 단계인 **[08-systemd-and-journalctl.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/08-systemd-and-journalctl.md)**에서는 Linux 서비스 관리의 표준인 **systemd 유닛(Unit) 파일 설계**, 프로세스 자동 재시작 정책(`Restart=on-failure`), 그리고 바이너리 기반 고성능 로깅 시스템인 **`journalctl`의 우선순위별, 서비스별, 시간대별 정밀 로그 필터링**을 학습합니다.
