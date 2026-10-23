import os
import sys
import time
import math
import tempfile
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, Query, HTTPException
import psutil

app = FastAPI(
    title="Linux System Chaos & Diagnostic Lab API",
    description="Linux 시스템 리소스 병목(CPU, Memory, FD, Disk, Zombie)을 재현하고 진단하기 위한 실습용 API 서버",
    version="0.1.0"
)

# 전역 메모리 누수 시뮬레이션용 버퍼
MEMORY_LEAK_BUFFER: List[bytes] = []

# 열린 파일 디스크립터(FD) 누수 시뮬레이션용 파일 객체 목록
FD_LEAK_HANDLES: List[Any] = []

# 삭제되었으나 열려 있는 파일 핸들 목록 (lsof +L1 진단용)
UNLINKED_FILE_HANDLES: List[Any] = []


@app.get("/health")
def health_check() -> Dict[str, str]:
    """기본 헬스체크 엔드포인트"""
    return {"status": "ok", "service": "chaos-target"}


@app.get("/metrics/process")
def process_metrics() -> Dict[str, Any]:
    """현재 프로세스의 시스템 리소스 지표 확인"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    
    return {
        "pid": process.pid,
        "ppid": process.ppid(),
        "cpu_percent": process.cpu_percent(interval=0.1),
        "threads_count": process.num_threads(),
        "open_file_descriptors": process.num_fds() if hasattr(process, "num_fds") else len(process.open_files()),
        "memory_rss_bytes": mem_info.rss,
        "memory_rss_mb": round(mem_info.rss / 1024 / 1024, 2),
        "memory_vms_mb": round(mem_info.vms / 1024 / 1024, 2),
        "leaked_memory_chunks_count": len(MEMORY_LEAK_BUFFER),
        "leaked_fds_count": len(FD_LEAK_HANDLES),
        "unlinked_files_count": len(UNLINKED_FILE_HANDLES),
    }


@app.post("/chaos/cpu")
async def trigger_cpu_burn(duration_seconds: int = Query(5, ge=1, le=60)):
    """
    [CPU 병목 재현] 지정된 시간 동안 CPU 연산 루프를 수행하여 코어 사용률 100% 유발
    진단 도구: top, htop, mpstat, pidstat
    """
    loop = asyncio.get_running_loop()

    def _burn():
        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            # CPU 바운드 연산 수행
            _ = math.sqrt(123456789.0) * math.sin(987654.0)

    # 비동기 이벤트 루프 블로킹 방지를 위해 별도 스레드에서 실행
    await loop.run_in_executor(None, _burn)
    return {"status": "success", "message": f"CPU 연산 완료 ({duration_seconds}초)"}


@app.post("/chaos/memory-leak")
def trigger_memory_leak(size_mb: int = Query(64, ge=1, le=512)):
    """
    [메모리 누수 및 OOM 재현] 지정된 MB 단위만큼의 메모리를 할당하여 전역 버퍼에 영구 보관
    진단 도구: free -m, vmstat, smem, dmesg (OOM Killer 로그)
    """
    chunk = b"X" * (size_mb * 1024 * 1024)
    MEMORY_LEAK_BUFFER.append(chunk)
    
    process = psutil.Process(os.getpid())
    rss_mb = round(process.memory_info().rss / 1024 / 1024, 2)
    return {
        "status": "leaked",
        "allocated_chunk_mb": size_mb,
        "total_leaked_chunks": len(MEMORY_LEAK_BUFFER),
        "current_rss_mb": rss_mb
    }


@app.post("/chaos/fd-leak")
def trigger_fd_leak(count: int = Query(10, ge=1, le=1000)):
    """
    [파일 디스크립터 누수 재현] 임시 파일을 생성하여 열고 닫지(close) 않음
    진단 도구: lsof -p <PID>, ls -l /proc/<PID>/fd, ulimit -n
    """
    for _ in range(count):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.write(b"Leaked file descriptor test data\n")
        tmp.flush()
        FD_LEAK_HANDLES.append(tmp)

    process = psutil.Process(os.getpid())
    current_fds = process.num_fds() if hasattr(process, "num_fds") else "N/A"
    return {
        "status": "fds_leaked",
        "newly_opened_fds": count,
        "total_leaked_handles": len(FD_LEAK_HANDLES),
        "current_process_fds": current_fds
    }


@app.post("/chaos/disk-unlinked")
def trigger_unlinked_open_file(size_mb: int = Query(50, ge=1, le=200)):
    """
    [삭제되었으나 열려 있는 파일 재현] 대용량 파일을 생성 후 unlink(삭제)하지만 핸들은 유지
    현상: df에는 디스크 공간이 줄어든 것으로 나타나지만 du로는 원인 파일을 찾을 수 없음
    진단 도구: lsof +L1, /proc/<PID>/fd
    """
    tmp = tempfile.NamedTemporaryFile(delete=False)
    # 파일에 데이터 기록
    chunk = b"A" * (1024 * 1024)
    for _ in range(size_mb):
        tmp.write(chunk)
    tmp.flush()
    
    file_path = tmp.name
    # 파일시스템 상에서 삭제 (unlink)
    os.unlink(file_path)
    
    # 프로세스는 파일 핸들을 계속 쥐고 있음
    UNLINKED_FILE_HANDLES.append(tmp)

    return {
        "status": "unlinked_file_created",
        "original_path": file_path,
        "size_mb": size_mb,
        "message": "파일이 파일시스템에서 삭제되었으나 핸들이 유지되어 디스크 공간을 점유 중입니다. lsof +L1 으로 진단하세요."
    }


@app.post("/chaos/zombie")
def trigger_zombie_process(count: int = Query(3, ge=1, le=20)):
    """
    [좀비 프로세스 재현] 자식 프로세스를 fork한 뒤 즉시 종료시키고 부모는 waitpid()를 호출하지 않음
    진단 도구: ps aux | grep defunct, pstree -p
    """
    zombie_pids = []
    for _ in range(count):
        pid = os.fork()
        if pid == 0:
            # 자식 프로세스: 즉시 종료
            os._exit(0)
        else:
            # 부모 프로세스: wait/waitpid를 호출하지 않아 자식이 좀비(defunct) 상태로 남음
            zombie_pids.append(pid)

    return {
        "status": "zombies_spawned",
        "created_pids": zombie_pids,
        "message": "부모 프로세스가 waitpid를 호출하지 않아 자식 프로세스가 좀비(Z 상태)가 되었습니다."
    }


@app.get("/chaos/slow")
async def trigger_slow_response(delay_seconds: int = Query(5, ge=1, le=30)):
    """
    [응답 지연 재현] 의도적으로 응답을 지연시켜 소켓 큐 포화 및 타임아웃 유발
    진단 도구: curl -w, ss -tan, tcpdump
    """
    await asyncio.sleep(delay_seconds)
    return {"status": "delayed", "delay_seconds": delay_seconds}


@app.post("/chaos/reset")
def reset_chaos_state():
    """모든 누수 리소스(메모리 버퍼, FD, 언링크 파일) 해제 및 정리"""
    global MEMORY_LEAK_BUFFER, FD_LEAK_HANDLES, UNLINKED_FILE_HANDLES
    
    # 열려 있던 FD 닫기
    for handle in FD_LEAK_HANDLES:
        try:
            handle.close()
        except Exception:
            pass
    FD_LEAK_HANDLES.clear()

    # 언링크 파일 핸들 닫기 (이 시점에 OS가 디스크 블록을 실제 해제함)
    for handle in UNLINKED_FILE_HANDLES:
        try:
            handle.close()
        except Exception:
            pass
    UNLINKED_FILE_HANDLES.clear()

    # 메모리 버퍼 비우기
    MEMORY_LEAK_BUFFER.clear()

    return {"status": "reset_completed", "message": "모든 카오스 리소스가 정리되었습니다."}
