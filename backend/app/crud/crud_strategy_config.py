from typing import List, Union
from sqlalchemy.orm import Session
from ..models.strategy_config import StrategyConfig
from ..schemas.strategy_config import StrategyConfigCreate, ConfigScope


class CRUDStrategyConfig:
    def get_multi(
        self,
        db: Session,
        scope: Union[ConfigScope, None] = None,
        *,
        account_id: int = None,
        strategy_id: str = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[StrategyConfig]:
        """계좌 + 전략 기준으로 설정 조회"""
        # ConfigScope 객체 또는 개별 파라미터 지원
        if scope:
            account_id = scope.account_id
            strategy_id = scope.strategy_id

        return db.query(StrategyConfig).filter(
            StrategyConfig.account_id == account_id,
            StrategyConfig.strategy_id == strategy_id
        ).order_by(StrategyConfig.rank).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: StrategyConfigCreate) -> StrategyConfig:
        db_obj = StrategyConfig(
            tab_id=obj_in.tab_id,
            account_id=obj_in.account_id,
            strategy_id=obj_in.strategy_id,
            rank=obj_in.rank,
            is_active=obj_in.is_active,
            tab_name=obj_in.tab_name,
            config_json=obj_in.config_json
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def replace_all(
        self,
        db: Session,
        scope: Union[ConfigScope, None] = None,
        configs: List[StrategyConfigCreate] = None,
        *,
        account_id: int = None,
        strategy_id: str = None
    ) -> List[StrategyConfig]:
        """계좌 + 전략에 해당하는 모든 설정 교체"""
        # ConfigScope 객체 또는 개별 파라미터 지원
        if scope:
            account_id = scope.account_id
            strategy_id = scope.strategy_id

        # Delete only configs for THIS account + strategy
        db.query(StrategyConfig).filter(
            StrategyConfig.account_id == account_id,
            StrategyConfig.strategy_id == strategy_id
        ).delete()

        new_objs = []
        for conf in configs:
            db_obj = StrategyConfig(
                tab_id=conf.tab_id,
                account_id=account_id,
                strategy_id=strategy_id,
                rank=conf.rank,
                is_active=conf.is_active,
                tab_name=conf.tab_name,
                config_json=conf.config_json
            )
            db.add(db_obj)
            new_objs.append(db_obj)

        db.commit()
        for obj in new_objs:
            db.refresh(obj)

        return new_objs

    def sync_selective(
        self,
        db: Session,
        scope: Union[ConfigScope, None] = None,
        configs: List[StrategyConfigCreate] = None,
        preserve_inactive: bool = True,
        *,
        account_id: int = None,
        strategy_id: str = None
    ) -> List[StrategyConfig]:
        """
        Selective sync: 계좌 + 전략 기준으로 설정 동기화
        - 비활성 탭 보존
        - Upsert 방식
        """
        # ConfigScope 객체 또는 개별 파라미터 지원
        if scope:
            account_id = scope.account_id
            strategy_id = scope.strategy_id

        # 1. Get all existing tabs for this account + strategy
        existing_tabs = db.query(StrategyConfig).filter(
            StrategyConfig.account_id == account_id,
            StrategyConfig.strategy_id == strategy_id
        ).all()

        # 2. Extract inactive tabs (preservation targets)
        inactive_tabs = {tab.tab_id: tab for tab in existing_tabs if not tab.is_active} if preserve_inactive else {}

        # 3. Get tab_id set from configs
        config_ids = {conf.tab_id for conf in configs}

        # 4. Determine tabs to delete: in DB but not in configs and not inactive
        to_delete = [
            tab for tab in existing_tabs
            if tab.tab_id not in config_ids and tab.tab_id not in inactive_tabs
        ]

        for tab in to_delete:
            db.delete(tab)

        # 5. Upsert configs
        for conf in configs:
            # tab_id (UUID) is already unique — no account_id filter needed
            db_obj = db.query(StrategyConfig).filter(
                StrategyConfig.tab_id == conf.tab_id
            ).first()

            if db_obj:
                # Update existing tab
                db_obj.strategy_id = strategy_id
                db_obj.rank = conf.rank
                db_obj.is_active = conf.is_active
                db_obj.tab_name = conf.tab_name
                db_obj.config_json = conf.config_json
            else:
                # Insert new tab
                db_obj = StrategyConfig(
                    tab_id=conf.tab_id,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    rank=conf.rank,
                    is_active=conf.is_active,
                    tab_name=conf.tab_name,
                    config_json=conf.config_json
                )
                db.add(db_obj)

        # 6. Commit and return all tabs (including inactive)
        db.commit()
        return self.get_multi(db, account_id=account_id, strategy_id=strategy_id)


strategy_config = CRUDStrategyConfig()
