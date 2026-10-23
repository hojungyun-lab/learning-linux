#!/usr/bin/env python3
"""
파일 디스크립터(FD) 누수 시뮬레이션 스크립트
지정된 개수만큼 임시 파일을 열어두고 닫지(close) 않은 채 대기합니다.
"""
import os
import sys
import time
import tempfile

def leak_file_descriptors(count: int = 50):
    print(f"[*] 프로세스 시작 (PID: {os.getpid()})")
    print(f"[*] 파일 디스크립터 {count}개 누수 시뮬레이션 중...")
    
    handles = []
    for i in range(count):
        try:
            f = tempfile.NamedTemporaryFile(prefix=f"fd_leak_{i}_", delete=False)
            f.write(b"File descriptor leak test\n")
            f.flush()
            handles.append(f)
        except OSError as e:
            print(f"[!] FD 할당 실패 (도달 한도: {i}): {e}")
            break

    print(f"[*] 총 {len(handles)}개의 파일 디스크립터가 열려 있습니다.")
    print(f"[*] 진단 명령어:")
    print(f"    - ls -l /proc/{os.getpid()}/fd")
    print(f"    - lsof -p {os.getpid()}")
    print(f"[*] 30초 동안 대기합니다. (Ctrl+C로 종료)")
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        print("\n[*] 종료 요청 수신")
    finally:
        for f in handles:
            f.close()
            try:
                os.unlink(f.name)
            except OSError:
                pass
        print("[*] 모든 FD 정상 반환 완료")

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    leak_file_descriptors(count)
