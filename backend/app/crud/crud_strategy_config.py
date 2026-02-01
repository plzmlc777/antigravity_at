from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.strategy_config import StrategyConfig
from ..schemas.strategy_config import StrategyConfigCreate

class CRUDStrategyConfig:
    def get_multi(self, db: Session, strategy_id: str, account_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[StrategyConfig]:
        query = db.query(StrategyConfig).filter(StrategyConfig.strategy_id == strategy_id)
        if account_id is not None:
            query = query.filter(StrategyConfig.account_id == account_id)
        return query.order_by(StrategyConfig.rank).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: StrategyConfigCreate, account_id: Optional[int] = None) -> StrategyConfig:
        db_obj = StrategyConfig(
            tab_id=obj_in.tab_id,
            strategy_id=obj_in.strategy_id,
            account_id=account_id or obj_in.account_id,
            rank=obj_in.rank,
            is_active=obj_in.is_active,
            tab_name=obj_in.tab_name,
            config_json=obj_in.config_json
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def replace_all(self, db: Session, strategy_id: str, configs: List[StrategyConfigCreate], account_id: Optional[int] = None) -> List[StrategyConfig]:
        # Delete only configs for THIS strategy AND account
        query = db.query(StrategyConfig).filter(StrategyConfig.strategy_id == strategy_id)
        if account_id is not None:
            query = query.filter(StrategyConfig.account_id == account_id)
        query.delete()

        new_objs = []
        for conf in configs:
            db_obj = StrategyConfig(
                tab_id=conf.tab_id,
                strategy_id=strategy_id, # Enforce ID from URL context
                account_id=account_id or conf.account_id,
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

    def sync_selective(self, db: Session, strategy_id: str, configs: List[StrategyConfigCreate],
                      preserve_inactive: bool = True, account_id: Optional[int] = None) -> List[StrategyConfig]:
        """
        Selective sync: Preserve inactive tabs while synchronizing active tabs

        Logic:
        1. Query all existing tabs for this strategy from DB
        2. If preserve_inactive=True, keep is_active=False tabs
        3. Upsert configs (update if exists, insert if not)
        4. Delete tabs that are not in configs and not inactive
        """
        # 1. Get all existing tabs for this strategy and account
        query = db.query(StrategyConfig).filter(StrategyConfig.strategy_id == strategy_id)
        if account_id is not None:
            query = query.filter(StrategyConfig.account_id == account_id)
        existing_tabs = query.all()

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
            conf.strategy_id = strategy_id  # Enforce strategy_id from URL

            # Check if tab already exists
            db_obj = db.query(StrategyConfig).filter(
                StrategyConfig.tab_id == conf.tab_id
            ).first()

            if db_obj:
                # Update existing tab
                db_obj.strategy_id = strategy_id
                db_obj.account_id = account_id or conf.account_id
                db_obj.rank = conf.rank
                db_obj.is_active = conf.is_active
                db_obj.tab_name = conf.tab_name
                db_obj.config_json = conf.config_json
            else:
                # Insert new tab
                db_obj = StrategyConfig(
                    tab_id=conf.tab_id,
                    strategy_id=strategy_id,
                    account_id=account_id or conf.account_id,
                    rank=conf.rank,
                    is_active=conf.is_active,
                    tab_name=conf.tab_name,
                    config_json=conf.config_json
                )
                db.add(db_obj)

        # 6. Commit and return all tabs (including inactive)
        db.commit()
        return self.get_multi(db, strategy_id, account_id=account_id)

strategy_config = CRUDStrategyConfig()
