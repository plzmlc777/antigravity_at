#!/bin/bash
# SSH 키 자동 등록 스크립트

REMOTE_HOST="121.183.229.140"
REMOTE_USER="mint"
SSH_KEY="$HOME/.ssh/id_ed25519.pub"

echo "=========================================="
echo "SSH 키 자동 등록 스크립트"
echo "=========================================="
echo ""
echo "리모트 서버: $REMOTE_USER@$REMOTE_HOST"
echo "공개 키: $SSH_KEY"
echo ""
echo "리모트 서버 패스워드를 입력해주세요:"
echo ""

# ssh-copy-id 실행 (인터랙티브 패스워드 입력)
ssh-copy-id -i "$SSH_KEY" "$REMOTE_USER@$REMOTE_HOST"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSH 키가 성공적으로 등록되었습니다!"
    echo ""
    echo "이제 패스워드 없이 SSH 접속이 가능합니다:"
    echo "  ssh $REMOTE_USER@$REMOTE_HOST"
    echo ""
    echo "연결 테스트를 진행합니다..."
    ssh -o ConnectTimeout=5 "$REMOTE_USER@$REMOTE_HOST" "echo '=== SSH 연결 성공! ===' && hostname && pwd"
else
    echo ""
    echo "❌ SSH 키 등록에 실패했습니다."
    echo ""
    echo "수동 등록 방법:"
    echo "1. 공개 키 내용을 복사하세요:"
    echo "   cat $SSH_KEY"
    echo ""
    echo "2. 리모트 서버에 접속하세요:"
    echo "   ssh $REMOTE_USER@$REMOTE_HOST"
    echo ""
    echo "3. 다음 명령을 실행하세요:"
    echo "   mkdir -p ~/.ssh && chmod 700 ~/.ssh"
    echo "   echo '<공개 키 내용>' >> ~/.ssh/authorized_keys"
    echo "   chmod 600 ~/.ssh/authorized_keys"
fi
