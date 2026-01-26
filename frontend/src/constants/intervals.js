/**
 * Interval Options - Single Source of Truth
 *
 * Used across the application for:
 * - Configuration Parameters dropdown
 * - Backtest Settings dropdown
 * - Optimization panel options
 */

export const INTERVAL_OPTIONS = [
    { value: "1m", label: "1 Min" },
    { value: "3m", label: "3 Min" },
    { value: "5m", label: "5 Min" },
    { value: "10m", label: "10 Min" },
    { value: "15m", label: "15 Min" },
    { value: "30m", label: "30 Min" },
    { value: "60m", label: "1 Hour" },
    { value: "1d", label: "1 Day" },
];

// Helper: Get label by value
export const getIntervalLabel = (value) => {
    const option = INTERVAL_OPTIONS.find(opt => opt.value === value);
    return option ? option.label : value;
};

// Helper: Get all values as array (for validation)
export const INTERVAL_VALUES = INTERVAL_OPTIONS.map(opt => opt.value);

// Helper: Default optimization intervals
export const DEFAULT_OPT_INTERVALS = ["1m", "5m", "15m", "60m"];
