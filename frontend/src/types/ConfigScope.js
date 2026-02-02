/**
 * ConfigScope - 계좌 + 전략 컨텍스트 (항상 함께 사용되는 복합 키)
 *
 * 이 두 값은 논리적으로 항상 함께 다녀야 함:
 * - accountId: 어떤 계좌의 설정인지
 * - strategyId: 어떤 전략의 설정인지
 *
 * @typedef {Object} ConfigScope
 * @property {number|null} accountId - 계좌 ID
 * @property {string|null} strategyId - 전략 ID
 */

/**
 * ConfigScope 객체 생성
 * @param {number|null} accountId - 계좌 ID
 * @param {string|null} strategyId - 전략 ID
 * @returns {ConfigScope}
 */
export const createConfigScope = (accountId, strategyId) => ({
    accountId,
    strategyId
});

/**
 * ConfigScope 유효성 검사
 * @param {ConfigScope} scope - ConfigScope 객체
 * @returns {boolean} - 유효하면 true
 */
export const isValidScope = (scope) => {
    return scope &&
           scope.accountId !== null &&
           scope.accountId !== undefined &&
           scope.strategyId !== null &&
           scope.strategyId !== undefined &&
           scope.strategyId !== '';
};

/**
 * ConfigScope를 API 요청용 객체로 변환
 * @param {ConfigScope} scope - ConfigScope 객체
 * @returns {Object} - API 요청용 객체 (account_id, strategy_id)
 */
export const scopeToApiParams = (scope) => ({
    account_id: scope.accountId,
    strategy_id: scope.strategyId
});

export default { createConfigScope, isValidScope, scopeToApiParams };
