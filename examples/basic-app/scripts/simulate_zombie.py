#!/usr/bin/env python3
"""
좀비 프로세스 생성 시뮬레이션 스크립트
자식 프로세스를 fork()한 후 즉시 exit하고, 부모 프로세스는 wait()를 호출하지 않고 sleep합니다.
"""
import os
import time
import sys

def create_zombies(count: int = 5):
    print(f"[*] 부모 프로세스 시작 (PID: {os.getpid()})")
    print(f"[*] 좀비 프로세스 {count}개 생성 중...")
    
    children = []
    for i in range(count):
        pid = os.fork()
        if pid == 0:
            # 자식 프로세스: 즉각 종료 (종료 상태 반환 준비)
            os._exit(0)
        else:
            children.append(pid)
            print(f"    - 생성된 자식 PID: {pid}")

    print(f"[*] 자식이 모두 종료되었으나 부모가 waitpid()를 호출하지 않았습니다.")
    print(f"[*] 확인 명령: ps -eo pid,ppid,state,comm | awk '$3==\"Z\"'")
    print(f"[*] 30초 동안 대기합니다. (Ctrl+C로 종료 시 고아 프로세스가 되어 init에 입양/정리됨)")
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        print("\n[*] 종료 요청 수신")
    print("[*] 부모 프로세스 종료")

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    create_zombies(count)
