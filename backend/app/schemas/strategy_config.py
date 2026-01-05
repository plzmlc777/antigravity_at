from typing import Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime

class StrategyConfigBase(BaseModel):
    tab_id: str
    rank: int
    is_active: bool = True
    tab_name: str
    config_json: Dict[str, Any]

class StrategyConfigCreate(StrategyConfigBase):
    pass

class StrategyConfigUpdate(StrategyConfigBase):
    pass

class StrategyConfig(StrategyConfigBase):
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
