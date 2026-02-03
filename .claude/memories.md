# Claude Project Memories

이 파일은 Claude가 반복적으로 기억해야 할 중요한 지침을 저장합니다.

---

## 버전업 (Version Bump) - 필수 절차

**트리거 키워드**: "버전업", "배포", "Version Up", "Deployment"

**절차**:
1. `.claude/docs/release_protocol.md` 파일 읽기
2. 커밋되지 않은 변경사항 확인 및 커밋
3. Change Log Report 생성:
   - User Ordered Changes (사용자 요청 변경)
   - Self-Initiated Changes (자체 개선)
   - Modified Files (수정된 파일 목록)
4. `./scripts/bump_version.sh <새버전>` 실행
5. 결과 보고

**금지 사항**:
- ❌ `backend/app/core/config.py` 수동 수정
- ❌ `frontend/package.json` 수동 수정
- ❌ 스크립트 없이 git tag 생성

---

## 재시작 (Restart)

**트리거 키워드**: "재시작", "Restart"

**명령어**: `./scripts/bump_version.sh --restart`

---
