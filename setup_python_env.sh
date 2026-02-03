#!/bin/bash

echo "=========================================="
echo "Python 환경 설정 스크립트"
echo "=========================================="
echo ""

# 3단계: pip 및 venv 설치
echo "=== 3. pip 및 venv 설치 ==="
sudo apt update
sudo apt install -y python3-pip python3-venv

echo ""
echo "✅ pip 및 venv 설치 완료!"
echo ""

# 확인
echo "📦 설치 확인:"
python3 --version
pip3 --version

echo ""

# 4단계: 가상환경 생성
echo "=== 4. 가상환경 생성 ==="
cd ~/antigravity/backend
python3 -m venv venv

echo ""
echo "✅ 가상환경 생성 완료!"
echo ""

# 5단계: 패키지 설치
echo "=== 5. 프로젝트 의존성 설치 ==="
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ 패키지 설치 완료!"
echo ""

# 6단계: 확인
echo "=== 6. 설치 확인 ==="
echo "📦 설치된 패키지 (주요):"
pip list | grep -E "fastapi|uvicorn|pydantic|sqlalchemy|psycopg2"

echo ""
echo "💾 가상환경 크기:"
du -sh venv

echo ""
echo "=========================================="
echo "✅ Python 환경 설정 완료!"
echo "=========================================="
echo ""
echo "가상환경 활성화 방법:"
echo "  cd ~/antigravity/backend"
echo "  source venv/bin/activate"
echo ""
echo "백엔드 실행 방법:"
echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"
echo ""
