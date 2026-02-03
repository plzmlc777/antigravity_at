#!/bin/bash
# SSH 키 등록 (원라이너)

echo "=========================================="
echo "SSH 키를 리모트 서버에 등록합니다"
echo "=========================================="
echo ""
echo "리모트 서버: mint@121.183.229.140"
echo "공개 키: ~/.ssh/id_ed25519.pub"
echo ""
echo "패스워드를 입력하시면 자동으로 등록됩니다."
echo ""

ssh-copy-id -i ~/.ssh/id_ed25519.pub mint@121.183.229.140

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSH 키 등록 완료!"
    echo ""
    echo "연결 테스트 중..."
    echo ""
    ssh -o ConnectTimeout=5 mint@121.183.229.140 "echo '=== SSH 연결 성공! ===' && echo 'Hostname:' \$(hostname) && echo 'Path: '\$(pwd) && echo 'PM2 Status:' && pm2 status"
else
    echo ""
    echo "❌ 등록 실패"
fi
