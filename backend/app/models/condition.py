from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Boolean, ForeignKey
from sqlalchemy.sql import func
from ..db.base import Base
import enum

class ConditionType(str, enum.Enum):
    STOP_LOSS = "STOP_LOSS" # 손절 (가격 이하 하락 시)
    TAKE_PROFIT = "TAKE_PROFIT" # 익절 (가격 이상 상승 시)
    TRAILING_STOP = "TRAILING_STOP" # 트레일링 스탑 (고점 대비 하락 시)

class ConditionStatus(str, enum.Enum):
    PENDING = "PENDING"     # 감시 중
    TRIGGERED = "TRIGGERED" # 조건 만족, 주문 실행 중
    COMPLETED = "COMPLETED" # 주문 체결 완료 (더 이상 감시 안 함)
    CANCELLED = "CANCELLED" # 사용자 취소 또는 원본 주문 청산으로 인한 취소
    FAILED = "FAILED"       # 주문 실패

class ConditionalOrder(Base):
    __tablename__ = "conditional_orders"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    
    # Condition Config
    condition_type = Column(String, nullable=False) # Enum: STOP_LOSS, TAKE_PROFIT
    trigger_price = Column(Float, nullable=False)   # 이 가격에 도달하면 발동
    
    # Order Config (Trigger 되면 나갈 주문)
    order_type = Column(String, default="sell")     # 보통 매도(sell)
    price_type = Column(String, default="market")   # 보통 시장가(market)로 탈출
    order_price = Column(Float, default=0)          # 지정가일 경우 가격
    quantity = Column(Integer, nullable=False)      # 수량
    
    # Status
    status = Column(String, default="PENDING")
    
    # Metadata
    ref_order_id = Column(String, nullable=True) # 원본 주문 번호 (선택적)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    # For Trailing Stop (Optional)
    highest_price = Column(Float, nullable=True) # 감시 시작 후 도달한 최고가
    trailing_percent = Column(Float, nullable=True) # 고점 대비 하락 퍼센트
