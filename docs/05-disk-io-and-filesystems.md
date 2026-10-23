# 05. 스토리지 I/O 및 파일시스템 트러블슈팅

## 🎯 학습 목표 (Goal)
- Inode와 Data Block의 구조적 차이를 이해하고, 디스크 용량이 남아 있어도 파일 생성이 불가능한 **Inode 고갈 현상**을 진단합니다.
- 현업에서 자주 발생하는 **"파일을 삭제(`rm`)했음에도 디스크 용량이 반환되지 않아 `df`는 100%인데 `du`로는 범인 파일을 찾을 수 없는 현상(Unlinked Open File)"**을 `lsof +L1`으로 찾아내고, 프로세스 무중단으로 디스크 공간을 회수하는 방법을 실습합니다.
- `iostat`의 핵심 지표(`%util`, `await`, `aqu-sz`)를 기반으로 스토리지 I/O 병목 여부를 판별합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. Inode와 Data Block의 분리 구조
Linux 파일시스템(ext4, xfs 등)은 파일의 메타데이터와 실제 내용을 서로 다른 영역에 보관합니다:
- **Inode (Index Node)**: 파일의 소유자(UID/GID), 접근 권한, 수정 시각, 파일 크기, 그리고 실제 데이터가 저장된 디스크 블록의 주소 포인터를 담는 메타데이터 구조체.
- **Data Block**: 파일의 실제 바이트 데이터가 저장되는 블록 (일반적으로 4KB 단위).
- **디렉터리 엔트리 (dentry)**: 사람을 위한 "파일명"과 해당 파일의 "Inode 번호"를 매핑해 주는 테이블.

> [!WARNING]
> **Inode 고갈 장애 (`No space left on device`)**:
> 수백만 개의 0바이트 임시 파일이나 세션 파일이 생성된 경우, 디스크의 기가바이트(GB) 용량은 90% 이상 남아 있어도 Inode가 100% 소진되어 더 이상 새 파일을 생성하거나 로그를 남길 수 없게 됩니다 (`df -i`로 진단).

### 2. df와 du가 서로 다른 용량을 보고하는 이유 (Unlinked Open File)
- **`df` (Disk Free)**: 파일시스템의 수퍼블록(Superblock)에서 직접 할당/비할당 블록의 개수를 읽어옵니다.
- **`du` (Disk Usage)**: 지정한 디렉터리 트리 아래의 디렉터리 엔트리(파일명)를 하나씩 순회하며 크기를 합산합니다.

**왜 수치가 어긋나는가?**
어떤 프로세스가 파일(예: `app.log`)을 열어 파일 디스크립터(FD)를 쥐고 있는 상태에서, 운영자가 용량을 확보하려고 `rm app.log`를 실행하면:
1. 디렉터리 엔트리(파일명)만 파일시스템 트리에서 제거됩니다 (Unlink).
2. `du`는 파일명을 순회하므로 이 파일의 크기를 집계할 수 없습니다.
3. 그러나 커널은 프로세스가 파일 핸들을 닫지 않았으므로 Inode와 Data Block을 디스크에 그대로 유지합니다.
4. 따라서 `df`는 여전히 디스크가 100% 차 있는 것으로 보고합니다.

### 3. `iostat -xz 1` 핵심 지표 해석
스토리지 하드웨어 병목을 측정할 때 반드시 확인해야 할 3대 지표:
- **`%util`**: 디스크 장치에 I/O 요청이 전달되어 활성화되어 있던 시간의 비율. 100%에 근접하면 디스크 장치가 포화 상태임을 의미합니다 (단, NVMe/SSD 배열의 경우 동시 큐 처리가 가능하므로 await를 함께 봐야 함).
- **`r_await` / `w_await`**: 읽기/쓰기 요청 하나가 처리되기까지 소요된 총 시간 (I/O 대기 큐 체류 시간 + 실제 디바이스 서비스 시간)을 밀리초(ms) 단위로 나타낸 값. 수십 ms 이상으로 치솟는다면 심각한 I/O 지연이 발생하고 있는 것입니다.
- **`aqu-sz` (Average Queue Size)**: 디스크 드라이버 요청 큐에서 대기 중인 평균 I/O 요청 개수.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. 파일시스템 용량 및 Inode 사용률 진단
디스크 공간과 Inode 사용 현황을 각각 확인합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 파일시스템 마운트 지점별 디스크 공간 사용률 확인
df -hT -x tmpfs -x devtmpfs

# 2. Inode 사용률 확인 (IUse% 열 점검)
df -hi -x tmpfs -x devtmpfs
```

### Step 2. 실전 장애 재현: 삭제되었으나 열려 있는 파일(Unlinked Open File) 주입
`chaos-target` 서버의 장애 주입 엔드포인트를 호출하여 50MB 크기의 대용량 파일을 생성한 뒤, `unlink`를 수행하지만 프로세스 핸들은 계속 유지하도록 만듭니다.

```bash
# 1. 삭제되었으나 핸들이 유지된 50MB 파일 생성 요청
curl -X POST "http://chaos-target:8000/chaos/disk-unlinked?size_mb=50" | jq .
```

*응답 예시:*
```json
{
  "status": "unlinked_file_created",
  "original_path": "/tmp/tmpa1b2c3d4",
  "size_mb": 50,
  "message": "파일이 파일시스템에서 삭제되었으나 핸들이 유지되어 디스크 공간을 점유 중입니다. lsof +L1 으로 진단하세요."
}
```

### Step 3. lsof +L1 명령어로 보이지 않는 점유 파일 추적
일반적인 `du`나 `ls`로는 사라진 파일이 보이지 않습니다. `lsof`의 링크 카운트 필터 옵션을 사용합니다.

```bash
# 링크 카운트가 0(삭제됨)이면서 열려 있는 파일 핸들 탐색
# +L1: 링크 수가 1 미만(즉 0)인 열린 파일만 필터링
lsof +L1
```

*출력 예시:*
```text
COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NLINK   NODE NAME
python3    1  root    7u   REG   0,52 52428800     0 123456 /tmp/tmpa1b2c3d4 (deleted)
```
- `PID 1`의 `python3` 프로세스가 파일 디스크립터 `7번(7u)`으로 50MB(`52428800` bytes) 크기의 `(deleted)` 파일을 계속 붙잡고 있음이 드러납니다.

### Step 4. 프로세스 중단 없이 디스크 공간을 즉시 회수하는 기법
운영 환경에서 해당 프로세스를 재시작할 수 없는 긴급 상황일 경우, `/proc/<PID>/fd/<FD>` 경로를 통해 파일 크기를 즉시 0으로 비웁니다 (Truncate).

```bash
# 프로세스의 해당 파일 디스크립터 경로를 리다이렉션으로 Truncate (용량 비우기)
# 예: PID가 1이고 FD가 7인 경우
: > /proc/1/fd/7

# 또는 truncate 명령어를 사용할 수도 있습니다
# truncate -s 0 /proc/1/fd/7
```

다시 `lsof +L1`을 확인하면 파일 크기(`SIZE/OFF`)가 `0`으로 감소하여 디스크 공간이 즉시 파일시스템으로 반환된 것을 확인할 수 있습니다.

### Step 5. 스토리지 I/O 부하 모니터링 실습 (iostat & iotop)
디스크 장치의 I/O 성능 및 병목 프로세스를 계측합니다.

```bash
# 1. 1초 간격으로 블록 디바이스 통계 출력 (확장 통계 -x, 0값 제외 -z)
iostat -xz 1 3

# 2. 실제 디스크 I/O를 발생시키는 프로세스만 실시간 필터링 (-o: only I/O)
iotop -o -b -n 3
```

---

## 🎯 마무리 및 다음 단계

파일시스템의 핵심인 Inode 구조와 `df`와 `du`의 괴리 원인을 파악하고, 무중단 Truncate를 통해 긴급 디스크 풀 장애를 해결하는 기술을 습득했습니다.

다음 단계인 **[06-network-troubleshooting.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/06-network-troubleshooting.md)**에서는 **TCP 3-Way Handshake와 4-Way Teardown 상태 머신**, `ss`를 통한 소켓 버퍼(Recv-Q, Send-Q) 분석, 그리고 소켓 고갈의 주원인인 **`TIME_WAIT` 및 `CLOSE_WAIT` 소켓 누수 진단 기법**을 심층 분석합니다.
