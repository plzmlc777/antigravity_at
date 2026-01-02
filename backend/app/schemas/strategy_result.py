from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

class StrategyResultBase(BaseModel):
    data: Dict[str, Any]

class StrategyResultCreate(StrategyResultBase):
    pass

class StrategyResultResponse(StrategyResultBase):
    tab_id: str
    result_type: str
    updated_at: datetime

    class Config:
        from_attributes = True
