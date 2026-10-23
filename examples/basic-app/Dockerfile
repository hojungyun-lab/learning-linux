FROM ubuntu:24.04

# 비대화형 패키지 설치 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

# 기본 및 핵심 시스템 진단 툴체인 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 기본 유틸리티 및 텍스트 편집기
    bash-completion \
    ca-certificates \
    curl \
    wget \
    gnupg \
    vim \
    nano \
    tree \
    jq \
    # 프로세스 및 CPU/메모리 진단 도구
    procps \
    sysstat \
    htop \
    iotop \
    smem \
    stress-ng \
    util-linux \
    # 스토리지 및 파일시스템 진단
    lsof \
    psmisc \
    e2fsprogs \
    # 네트워크 및 소켓 분석 도구
    iproute2 \
    net-tools \
    iputils-ping \
    traceroute \
    dnsutils \
    tcpdump \
    iptables \
    socat \
    netcat-openbsd \
    # 시스템 콜 추적 및 디버깅
    strace \
    ltrace \
    gdb \
    # 개발 및 스크립팅 런타임
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# sysstat 활성화 설정 (기본적으로 비활성화되어 있는 sar 수집 활성화)
RUN sed -i 's/ENABLED="false"/ENABLED="true"/g' /etc/default/sysstat || true

WORKDIR /workspace

# 컨테이너 유지 및 기본 쉘 실행
CMD ["bash", "-c", "trap 'exit 0' SIGTERM; sleep infinity & wait"]
