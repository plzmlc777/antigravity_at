/**
 * Exchange Constants - Single Source of Truth
 *
 * 거래소별 설정값 관리. 새 거래소 추가 시 여기만 수정.
 */

// ── 기본 거래소 (폴백 기본값) ──
export const DEFAULT_EXCHANGE = 'Kiwoom';

// ── 거래소별 기본 설정 ──

// 최대 데이터 조회 기간 (일)
export const EXCHANGE_MAX_DAYS = {
    Kiwoom: 365,        // 키움: 1년 (API 제한)
    Binance: 730,       // 바이낸스 스팟: 2년
    BinanceFutures: 730 // 바이낸스 선물: 2년
};

// 기본 시작 자본금
export const EXCHANGE_INITIAL_CAPITAL = {
    Kiwoom: 10000000,    // 키움: 1,000만 원
    Binance: 10000,      // 바이낸스 스팟: 10,000 USDT
    BinanceFutures: 10000 // 바이낸스 선물: 10,000 USDT
};

// 기본 백테스트 기간 (일)
export const EXCHANGE_DEFAULT_DAYS = {
    Kiwoom: 365,         // 키움: 1년
    Binance: 730,        // 바이낸스 스팟: 2년
    BinanceFutures: 730  // 바이낸스 선물: 2년
};

// 거래소별 전략 파라미터 기본값 오버라이드
// 크립토 거래소는 주식과 다른 기본값 필요 (가격 스케일, 24/7 시장 등)
export const EXCHANGE_PARAMETER_DEFAULTS = {
    Binance: {
        qty_mode: "percent",           // 자본 비율 모드 (fixed 1주 → 자본의 N%)
        base_quantity: 5,              // 자본의 5% 투입
        trailing_start_percent: 2.0,   // 포지션 수익 2%에서 트레일링 시작
        trailing_stop_percent: 1.0,    // 고점 대비 1% 하락 시 매도
        max_loss_percent: 3.0,         // 포지션 손실 3% 손절
    },
    BinanceFutures: {
        qty_mode: "percent",
        base_quantity: 5,
        trailing_start_percent: 2.0,
        trailing_stop_percent: 1.0,
        max_loss_percent: 3.0,
    }
};

// 거래소별 최적화 파라미터 기본 범위 오버라이드
// 크립토는 percent 모드 기준, 주식보다 타이트한 손절/트레일링
export const EXCHANGE_OPT_RANGE_DEFAULTS = {
    Binance: {
        base_quantity: "3, 5, 10, 20",            // 자본의 N% (percent 모드)
        trailing_start_percent: "1.0, 2.0, 3.0, 5.0",
        trailing_stop_percent: "0.5, 1.0, 1.5, 2.0",
        max_loss_percent: "2.0, 3.0, 5.0, 10.0",
    },
    BinanceFutures: {
        base_quantity: "3, 5, 10, 20",
        trailing_start_percent: "1.0, 2.0, 3.0, 5.0",
        trailing_stop_percent: "0.5, 1.0, 1.5, 2.0",
        max_loss_percent: "2.0, 3.0, 5.0, 10.0",
    }
};

// 거래소별 수량 규칙 (백엔드 qty_rules.py와 동기화)
// Binance는 심볼별로 다를 수 있음 (API 동적 로드), 여기는 기본값
export const EXCHANGE_QTY_CONFIG = {
    Kiwoom: {
        qtyType: "int",         // 주식: 정수 단위
        minQty: 1,              // 최소 1주
        stepSize: 1,            // 1주 단위
        minNotional: 0,         // 최소 주문 금액 없음
    },
    Binance: {
        qtyType: "float",       // 크립토: 소수점 허용
        minQty: 0.00001,        // 심볼별 다름 (기본값)
        stepSize: 0.00001,      // 심볼별 다름 (기본값)
        minNotional: 5,         // 최소 주문 금액 5 USDT
    },
    BinanceFutures: {
        qtyType: "float",       // 크립토: 소수점 허용
        minQty: 0.001,          // 심볼별 다름 (기본값)
        stepSize: 0.001,        // 심볼별 다름 (기본값)
        minNotional: 5,         // 최소 주문 금액 5 USDT
    }
};

// ── Fallback 기본값 (Kiwoom/미등록 거래소) ──
const DEFAULT_MAX_DAYS = 365;
export const DEFAULT_INITIAL_CAPITAL = 10000000;
export const DEFAULT_DAYS = 365;

// ── Helper Functions ──

/** 거래소명으로 MAX_DAYS 조회 */
export const getMaxDays = (exchangeName) => {
    return EXCHANGE_MAX_DAYS[exchangeName] || DEFAULT_MAX_DAYS;
};

/** 거래소명으로 기본 자본금 조회 */
export const getDefaultCapital = (exchangeName) => {
    return EXCHANGE_INITIAL_CAPITAL[exchangeName] || DEFAULT_INITIAL_CAPITAL;
};

/** 거래소명으로 기본 백테스트 기간 조회 */
export const getDefaultDays = (exchangeName) => {
    return EXCHANGE_DEFAULT_DAYS[exchangeName] || DEFAULT_DAYS;
};

/** 거래소별 파라미터 오버라이드 조회 */
export const getParameterDefaults = (exchangeName) => {
    return EXCHANGE_PARAMETER_DEFAULTS[exchangeName] || null;
};

/** 거래소별 최적화 범위 오버라이드 조회 */
export const getOptRangeDefaults = (exchangeName) => {
    return EXCHANGE_OPT_RANGE_DEFAULTS[exchangeName] || null;
};

/** 거래소별 수량 규칙 조회 */
export const getQtyConfig = (exchangeName) => {
    return EXCHANGE_QTY_CONFIG[exchangeName] || EXCHANGE_QTY_CONFIG[DEFAULT_EXCHANGE];
};

/** MAX_DAYS를 사람이 읽을 수 있는 문자열로 변환 */
export const getMaxDaysLabel = (exchangeName) => {
    const days = getMaxDays(exchangeName);
    if (days >= 730) return `2 years (${days} days)`;
    if (days >= 365) return `1 year (${days} days)`;
    return `${days} days`;
};
