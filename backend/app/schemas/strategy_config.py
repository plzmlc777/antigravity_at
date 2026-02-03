from typing import Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime


class ConfigScope(BaseModel):
    """
    계좌 + 전략 컨텍스트 (항상 함께 사용되는 복합 키)

    이 두 값은 논리적으로 항상 함께 다녀야 함:
    - account_id: 어떤 계좌의 설정인지
    - strategy_id: 어떤 전략의 설정인지
    """
    account_id: int
    strategy_id: str

    class Config:
        frozen = True  # 불변 객체로 사용


class StrategyConfigBase(BaseModel):
    tab_id: str
    account_id: int  # 계좌 중심: 필수
    strategy_id: Optional[str] = "time_momentum"  # Default for migration
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
