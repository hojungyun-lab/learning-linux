# 06. 네트워크 스택, 소켓 상태 및 패킷 분석

## 🎯 학습 목표 (Goal)
- TCP 3-Way Handshake 및 4-Way Teardown 과정에서 커널 소켓 상태 머신(LISTEN, ESTABLISHED, TIME_WAIT, CLOSE_WAIT)의 전이 원리를 이해합니다.
- `ss` 명령어로 소켓 버퍼(Recv-Q, Send-Q)를 분석하여 애플리케이션의 소켓 지연을 진단하고, **TIME_WAIT과 CLOSE_WAIT 소켓 누수의 근본적인 원인 차이**를 식별합니다.
- `tcpdump`를 활용하여 운영 환경에 부하를 주지 않고 특정 플래그(SYN, RST, FIN) 패킷만을 정밀 필터링하여 캡처하는 기술을 습득합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. TCP 연결 수립 및 해제 상태 머신
TCP 통신은 신뢰성을 보장하기 위해 엄격한 상태 전이를 거칩니다:

```text
[Client]                                            [Server]
   |                                                   |
   | --- SYN (seq=x) --------------------------------> |  LISTEN -> SYN_RECV
   | <-- SYN-ACK (seq=y, ack=x+1) -------------------- |
   | --- ACK (ack=y+1) ------------------------------> |  SYN_RECV -> ESTABLISHED
   |                                                   |
   [데이터 송수신 (ESTABLISHED)]
   |                                                   |
   | --- FIN (능동적 종료 시작: Active Close) ----------> |  ESTABLISHED -> CLOSE_WAIT
   | <-- ACK ----------------------------------------- |  (커널이 즉각 ACK 응답)
   |                                                   |
   | [FIN_WAIT_2 대기 상태]                             |  (애플리케이션이 소켓 close() 호출)
   | <-- FIN ----------------------------------------- |  CLOSE_WAIT -> LAST_ACK
   | --- ACK ----------------------------------------> |  LAST_ACK -> CLOSED
   |                                                   |
   [TIME_WAIT (2MSL: 60초 대기 후 소멸)]
```

### 2. TIME_WAIT vs CLOSE_WAIT 누수 분석 (중요)
시스템에서 소켓 고갈로 인한 네트워크 장애가 발생했을 때 두 상태는 발생 원인과 해결책이 완전히 다릅니다:

| 소켓 상태 | 주체 | 발생 메커니즘 | 원인 및 해결 방안 |
| :---: | :---: | :--- | :--- |
| **TIME_WAIT** | 먼저 `close()`를 호출한 쪽 (Active Close) | 연결 해제 후 네트워크 상에 지연되어 떠돌던 패킷(Ghost Packet)이 새 연결에 유입되는 것을 방지하기 위해 2MSL(약 60초) 동안 소켓을 유지함. | 정상적인 TCP 동작. 단, 단시간에 수만 개의 연결이 열리고 닫히면 로컬 포트 고갈(EADDRNOTAVAIL) 유발. <br>👉 **해결**: HTTP Keep-Alive 적용, 커널 `net.ipv4.tcp_tw_reuse=1` 활성화 |
| **CLOSE_WAIT** | 상대방으로부터 FIN을 받은 쪽 (Passive Close) | 원격 호스트는 연결을 끊겠다고 통보했고 커널도 이를 수락했으나, **로컬 애플리케이션 코드가 소켓 객체에 대해 `close()`를 호출하지 않고 방치함.** | **100% 애플리케이션 버그(소켓 누수).** 타임아웃 처리가 없거나 예외 블록에서 connection.close()가 누락된 경우. <br>👉 **해결**: 애플리케이션 버그 수정 또는 해당 프로세스 재시작 |

### 3. LISTEN 소켓 vs ESTABLISHED 소켓의 Recv-Q / Send-Q
`ss -ltn`과 `ss -tn`에서 `Recv-Q`와 `Send-Q` 열은 소켓 상태에 따라 완전히 다른 의미를 가집니다:

1. **LISTEN 상태인 소켓**:
   - **`Send-Q`**: 커널이 허용한 백로그 큐(Backlog Queue)의 최대 크기 (`somaxconn` 또는 `listen(fd, backlog)` 값).
   - **`Recv-Q`**: 3-Way Handshake를 마치고 커널의 Accept 큐에 쌓였으나, **애플리케이션이 아직 `accept()` 함수로 꺼내가지 않은 대기 연결 수**.
   - ⚠️ **`Recv-Q > Send-Q`인 경우**: 백엔드 프로세스가 요청을 제때 처리하지 못해 새 접속 요청이 드롭(Drop)되고 있는 상태입니다.
2. **ESTABLISHED 상태인 소켓**:
   - **`Recv-Q`**: TCP 수신 버퍼에 도착했으나 애플리케이션이 아직 `read()`하지 않은 데이터 바이트(Bytes).
   - **`Send-Q`**: 애플리케이션이 `write()`했으나 상대방으로부터 아직 ACK를 받지 못한 송신 버퍼의 데이터 바이트.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 전체 소켓 요약 및 LISTEN 포트 검사
시스템의 소켓 계층 전반을 빠르게 스캔합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 소켓 요약 통계 확인 (TCP, UDP, RAW 소켓 개수)
ss -s

# 2. 현재 수신 대기(LISTEN) 중인 모든 TCP 포트 및 프로세스 식별
ss -tulpn
```

### Step 2. 소켓 상태별 개수 집계
현재 열려 있는 모든 TCP 소켓의 상태 분포를 한 줄로 집계합니다.

```bash
ss -tan | awk '{print $1}' | sort | uniq -c | sort -nr
```

*출력 예시:*
```text
      8 ESTAB
      2 LISTEN
      1 TIME-WAIT
```

### Step 3. 실시간 패킷 캡처 (tcpdump)
`chaos-target` 서버(172.28.0.20:8000)로 통신하는 패킷을 백그라운드에서 캡처합니다.

```bash
# 타깃 컨테이너의 8000 포트 트래픽 캡처 (최대 10개 패킷, DNS 역방향 조회 끄기: -nn)
tcpdump -i any -nn -s 0 -c 10 port 8000 &

# HTTP 헬스체크 호출로 패킷 발생
curl -s http://chaos-target:8000/health > /dev/null
```

*패킷 캡처 출력 분석:*
```text
13:42:01.123 IP 172.28.0.10.45678 > 172.28.0.20.8000: Flags [S], seq 1001, win 64240, length 0
13:42:01.124 IP 172.28.0.20.8000 > 172.28.0.10.45678: Flags [S.], seq 2001, ack 1002, win 65160, length 0
13:42:01.124 IP 172.28.0.10.45678 > 172.28.0.20.8000: Flags [.], ack 2002, win 64240, length 0
```
- `[S]`: SYN 패킷 (클라이언트 -> 서버)
- `[S.]`: SYN-ACK 패킷 (서버 -> 클라이언트)
- `[.]`: ACK 패킷 (클라이언트 -> 서버, 3-Way Handshake 완료)

### Step 4. SYN 패킷 전용 필터링 (TCP 연결 시도 탐색)
특정 비트 연산을 통해 새 연결 시도(SYN)만 캡처하여 초당 연결 인입률을 관측합니다.

```bash
# TCP 플래그 중 SYN 비트가 1인 패킷만 필터링
tcpdump -i any "tcp[tcpflags] & (tcp-syn) != 0" -nn -c 5
```

---

## 🎯 마무리 및 다음 단계

TCP 소켓 상태 머신의 전이 과정, TIME_WAIT과 CLOSE_WAIT의 장애 원인 분리, 그리고 `ss`와 `tcpdump`를 통한 L4 레벨 관측 기법을 정립했습니다.

다음 단계인 **[07-dns-and-http-diagnostics.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/07-dns-and-http-diagnostics.md)**에서는 애플리케이션 통신 장애의 주범인 **DNS 리졸빙 내부 메커니즘(`/etc/resolv.conf`, `nsswitch.conf`)**, DNS 타임아웃 분석, 그리고 `curl`을 이용해 **DNS -> TCP Handshake -> TLS Handshake -> TTFB(첫 바이트 수신 시간)까지 L7 레이턴시 구간을 마이크로초 단위로 분해 계측**하는 실전 기술을 다룹니다.
