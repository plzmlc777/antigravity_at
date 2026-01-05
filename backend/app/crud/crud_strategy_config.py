from typing import List
from sqlalchemy.orm import Session
from ..models.strategy_config import StrategyConfig
from ..schemas.strategy_config import StrategyConfigCreate

class CRUDStrategyConfig:
    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[StrategyConfig]:
        return db.query(StrategyConfig).order_by(StrategyConfig.rank).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: StrategyConfigCreate) -> StrategyConfig:
        db_obj = StrategyConfig(
            tab_id=obj_in.tab_id,
            rank=obj_in.rank,
            is_active=obj_in.is_active,
            tab_name=obj_in.tab_name,
            config_json=obj_in.config_json
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def replace_all(self, db: Session, configs: List[StrategyConfigCreate]) -> List[StrategyConfig]:
        # Simple sync: Delete all and re-create
        # Transactional safety is important here
        db.query(StrategyConfig).delete()
        
        new_objs = []
        for conf in configs:
            db_obj = StrategyConfig(
                tab_id=conf.tab_id,
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

strategy_config = CRUDStrategyConfig()
