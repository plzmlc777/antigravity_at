# Operation Protocols

> DB 마이그레이션, 롤백, 버전 릴리즈 등 운영 프로토콜. 해당 작업 시 참조.

## Database Migration

> CRITICAL: 절대 DB DROP/RESET 금지. 데이터 손실 용납 불가.

```python
# backend/migrate_add_<feature>.py 패턴
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'your_table'"
        ))
        existing = {row[0] for row in result}
        if 'new_column' not in existing:
            conn.execute(text("ALTER TABLE your_table ADD COLUMN new_column VARCHAR(255)"))
        conn.commit()

if __name__ == "__main__":
    migrate()
```

```bash
# 사전 백업
pg_dump -h localhost -U antigravity_user antigravity_db > backups/db_backup_$(date +%Y%m%d_%H%M%S).sql

# 사후 검증
psql -h localhost -U antigravity_user -d antigravity_db -c "\d your_table"
```

## Rollback

> Default: Git 롤백만. DB 롤백은 명시적 요청 시에만.

```bash
pm2 stop all
git stash && git checkout <version_tag_or_hash>
# (선택) PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost -d antigravity_db < backups/db_backup_XXXX.sql
pm2 restart all
```

## Version Release

> 트리거: "버전업", "배포", "Version Up"

버전 수정 위치: `backend/app/core/config.py` (PROJECT_VERSION) + `frontend/package.json` (version)

**반드시 bump_version.sh 사용:**
```bash
# 버전업 (올인원: 커밋+태그+푸시+PM2 재시작)
bash scripts/bump_version.sh X.Y.Z

# 재시작만
bash scripts/bump_version.sh --restart

# 현재 버전 확인
bash scripts/bump_version.sh
```

**체크리스트:**
1. `.claude/docs/release_protocol.md` 읽기
2. 미커밋 변경사항 커밋
3. Change Log Report 생성
4. `bump_version.sh <새버전>` 실행 (수동 편집 금지!)
5. 사용자에게 보고

**금지:** config.py/package.json 수동 수정, 스크립트 없이 git tag, 사용자 요청 없이 리모트 배포
