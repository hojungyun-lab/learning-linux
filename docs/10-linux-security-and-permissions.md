# 10. 권한 격리, Capabilities 및 파일 보안

## 🎯 학습 목표 (Goal)
- Linux 표준 파일 권한(DAC, rwx)과 특수 권한(SUID, SGID, Sticky Bit), 그리고 `umask`의 계산 원리를 이해합니다.
- 복잡한 협업 환경에서 표준 그룹 권한의 한계를 극복하는 **POSIX 확장 접근 제어 목록(ACLs)**을 다룹니다.
- All-or-Nothing(전부 아니면 전무) 방식의 루트(root, UID 0) 권한의 위험성을 제거하고, **Linux Capabilities(`setcap`, `cap_net_bind_service`)를 활용해 비루트 사용자가 80/443 포트를 안전하게 바인딩**하도록 권한을 격리하는 기술을 습득합니다.

---

## 💡 핵심 개념 (Core Concepts)

### 1. 특수 권한 비트(Special Permission Bits)
표준 3자리 8진수 권한(`chmod 755`) 앞에 위치하는 4번째 최상위 비트의 의미:

| 권한 비트 | 명칭 | 8진수 | 동작 메커니즘 및 시스템 보안 영향 |
| :---: | :--- | :---: | :--- |
| **SUID** | Set User ID | `4000` | 바이너리 실행 시, 실행자가 아니라 **파일 소유자(Owner)의 권한으로 프로세스가 동작**합니다. (예: 일반 사용자가 비밀번호를 변경할 수 있도록 root 소유의 `/usr/bin/passwd`에 설정됨) |
| **SGID** | Set Group ID | `2000` | 디렉터리에 설정 시, 그 아래 생성되는 모든 하위 파일이 상위 디렉터리의 그룹 소유권을 자동 상속받습니다. (공용 프로젝트 폴더에 유용) |
| **Sticky Bit** | Sticky Bit | `1000` | 디렉터리에 누구나 쓰기 권한이 있더라도, **파일의 소유자 본인 또는 루트만이 해당 파일을 삭제/이름 변경**할 수 있습니다. (예: `/tmp` 디렉터리 `1777` 권한) |

### 2. POSIX ACLs (Access Control Lists)
기존 Unix 권한 체계는 `소유자`, `단일 그룹`, `기타(Others)`라는 3분법 구조로 제한되어 있어, 여러 특정 사용자나 추가 그룹에 개별적인 읽기/쓰기 권한을 부여할 수 없습니다.
- **`setfacl`**: 특정 유저(`u:bob:rw-`) 또는 특정 그룹(`g:devs:r-x`) 단위로 정밀한 접근 제어 규칙을 추가합니다.
- **`getfacl`**: 파일이나 디렉터리에 부여된 세부 ACL 목록을 확인합니다 (`ls -l` 시 권한 뒤에 `+` 기호가 붙음).

### 3. Linux Capabilities란 무엇인가?
전통적인 Unix 커널은 권한을 오직 두 가지로만 구분했습니다:
1. `UID == 0` (Superuser / Root): 모든 커널 보안 검사를 무조건 통과.
2. `UID != 0` (Unprivileged User): 엄격한 권한 제약을 받음. 1024 이하 포트 바인딩 불가, 네트워크 인터페이스 설정 불가, 타 프로세스 ptrace 불가.

이로 인해 웹 서버가 80 포트를 열기 위해 프로세스를 root로 실행해야 했고, 웹 서버에 원격 코드 실행 취약점(RCE)이 발생하면 서버 전체의 root 권한이 탈취되는 심각한 보안 사고가 발생했습니다.

리눅스 커널은 이를 해결하기 위해 루트의 전능한 권한을 약 40여 개의 독립적인 **Capabilities(기능 단위)**로 잘게 쪼갰습니다:
- **`CAP_NET_BIND_SERVICE`**: 비루트 프로세스가 1024 미만의 Privileged Port(80, 443 등)에 바인딩할 수 있는 권한.
- **`CAP_NET_ADMIN`**: 네트워크 인터페이스, 라우팅 테이블, 방화벽(iptables)을 설정할 수 있는 권한.
- **`CAP_SYS_PTRACE`**: `strace`나 `gdb`로 다른 프로세스를 디버깅할 수 있는 권한.
- **`CAP_SYS_TIME`**: 시스템 시계를 변경할 수 있는 권한.

---

## 🛠️ 실습 코드 (Hands-on)

### Step 1. umask 동작 원리 및 권한 계산 실습
새 파일과 디렉터리가 생성될 때 적용되는 기본 마스크를 검증합니다.

```bash
# linux-lab 컨테이너에서 실행
# 1. 현재 umask 확인 (기본값 보통 0022)
umask

# 2. 임시 디렉터리에 파일 및 디렉터리 생성 후 권한 확인
# (파일 기본 최대: 666 - 022 = 644 / 디렉터리 기본 최대: 777 - 022 = 755)
touch /tmp/test_file.txt && mkdir /tmp/test_dir
ls -ld /tmp/test_file.txt /tmp/test_dir
```

### Step 2. POSIX ACL을 통한 다중 사용자 권한 부여
단일 그룹 권한의 한계를 넘어 특정 사용자에게만 읽기/쓰기 권한을 부여합니다.

```bash
# 1. 테스트 파일 생성
touch /tmp/shared_document.txt
chmod 600 /tmp/shared_document.txt

# 2. 일반 nobody 사용자에게 읽기/쓰기(rw-) ACL 부여
setfacl -m u:nobody:rw /tmp/shared_document.txt

# 3. 파일의 ACL 설정 상태 확인
getfacl /tmp/shared_document.txt

# 4. ls -l 확인 시 권한 문자열 끝에 '+' 표기가 추가되었는지 확인
ls -l /tmp/shared_document.txt
```

### Step 3. Linux Capabilities를 이용한 비루트 80포트 바인딩
바이너리에 `CAP_NET_BIND_SERVICE` 기능을 부여하여 일반 사용자 권한으로 80 포트를 수신 대기(LISTEN)하는 실습을 진행합니다.

```bash
# 1. 테스트용 비루트 사용자(labuser) 생성
useradd -m labuser || true

# 2. Python 바이너리의 복사본을 생성
cp /usr/bin/python3 /tmp/python3_custom

# 3. 일반 사용자로 80포트 바인딩 시도 (권한 거부 에러 발생 확인)
su - labuser -c "/tmp/python3_custom -m http.server 80"
```

*에러 확인:*
```text
PermissionError: [Errno 13] Permission denied
```

이제 Capabilities를 부여합니다:
```bash
# 4. root 권한으로 바이너리에 CAP_NET_BIND_SERVICE 부여
# +ep: Effective(즉각 유효), Permitted(허용됨)
setcap 'cap_net_bind_service=+ep' /tmp/python3_custom

# 5. 부여된 기능 확인
getcap /tmp/python3_custom

# 6. 일반 사용자로 다시 80포트 바인딩 실행 (정상 수신 대기 성공!)
su - labuser -c "/tmp/python3_custom -m http.server 80" &
```

*성공 확인:*
```bash
# 80 포트가 비루트 사용자(labuser) 소유로 정상 바인딩되었는지 확인
ss -tulpn | grep :80
```

---

## 🎯 마무리 및 다음 단계

리눅스의 전통적 권한 모델(DAC, SUID, umask)의 한계를 이해하고, POSIX ACL과 Linux Capabilities를 통해 최소 권한 원칙을 실현하는 엔지니어링 기법을 습득했습니다.

다음 단계인 **[11-linux-namespaces-and-cgroups.md](file:///Users/hojungyun/Desktop/__PROJECTS/_AI/learning-linux/docs/11-linux-namespaces-and-cgroups.md)**에서는 Docker와 Kubernetes의 심장인 **컨테이너 가상화의 2대 축: Linux Namespaces(PID, NET, MNT 격리)와 cgroups v2(CPU, 메모리 리소스 한도 강제)**의 커널 내부 원리를 직접 수동으로 구현해 봅니다.
