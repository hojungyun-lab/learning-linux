#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo " 🐧 Linux 시스템 엔지니어링 분석 툴체인 진단"
echo "=============================================="

TOOLS=(
  "uptime:시스템 가동 시간 및 로드 애버리지"
  "free:가상 메모리 및 버퍼/캐시 현황"
  "vmstat:CPU, 메모리, I/O 통합 통계"
  "mpstat:코어별 CPU 사용률 상세 계측"
  "iostat:스토리지 블록 디바이스 %util 및 대기시간"
  "pidstat:프로세스/스레드 단위 CPU 및 I/O 분석"
  "ss:소켓 버퍼 및 TCP 상태 통계"
  "ip:네트워크 인터페이스 및 라우팅 테이블"
  "tcpdump:네트워크 L3/L4 패킷 캡처"
  "strace:시스템 콜(Syscall) 실시간 추적"
  "lsof:열린 파일 디스크립터 및 언링크 파일 추적"
  "stress-ng:합성 워크로드 리소스 부하 주입"
  "smem:PSS 기반 물리 메모리 정밀 측정"
  "dig:DNS 재귀 조회 및 리졸버 진단"
  "curl:L7 네트워크 지연 시간 세부 계측"
)

SUCCESS_COUNT=0
TOTAL_COUNT=${#TOOLS[@]}

for item in "${TOOLS[@]}"; do
  cmd="${item%%:*}"
  desc="${item##*:}"
  
  if command -v "$cmd" >/dev/null 2>&1; then
    path=$(which "$cmd")
    printf " [\033[32mOK\033[0m] %-12s : %-35s (%s)\n" "$cmd" "$desc" "$path"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  else
    printf " [\033[31mFAIL\033[0m] %-12s : %s (설치 필요)\n" "$cmd" "$desc"
  fi
done

echo "=============================================="
echo " 결과: ${SUCCESS_COUNT}/${TOTAL_COUNT} 도구 검증 완료"
if [ "$SUCCESS_COUNT" -eq "$TOTAL_COUNT" ]; then
  echo " 모든 필수 시스템 진단 툴체인이 준비되었습니다."
else
  echo " 일부 도구가 누락되었습니다. 패키지 설치 상태를 확인하세요."
  exit 1
fi
echo "=============================================="
