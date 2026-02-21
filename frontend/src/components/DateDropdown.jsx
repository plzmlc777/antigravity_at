import React, { useMemo } from 'react';

/**
 * DateDropdown - Custom date picker with Year/Month/Day dropdowns
 *
 * Props:
 * - value: "YYYY-MM-DD" format string or empty
 * - onChange: (dateString) => void
 * - minDate: Date object for minimum selectable date (default: 1 year ago)
 * - maxDate: Date object for maximum selectable date (default: today)
 * - disabled: boolean
 * - className: additional CSS classes for the container
 */
const DateDropdown = ({
    value = "",
    onChange,
    minDate,
    maxDate,
    disabled = false,
    className = ""
}) => {
    // Default min/max dates (1 year back to today)
    const today = new Date();
    const defaultMinDate = useMemo(() => {
        const d = new Date();
        d.setDate(d.getDate() - 365); // 1 year ago (API limit)
        return d;
    }, []);

    const effectiveMinDate = minDate || defaultMinDate;
    const effectiveMaxDate = maxDate || today;

    // Parse current value
    const parsed = useMemo(() => {
        if (!value) return { year: "", month: "", day: "" };
        const parts = value.split("-");
        if (parts.length !== 3) return { year: "", month: "", day: "" };
        return {
            year: parts[0],
            month: parts[1],
            day: parts[2]
        };
    }, [value]);

    // Generate year options (from minDate year to maxDate year)
    // 현재 선택된 연도가 범위 밖이어도 항상 포함 (새로고침 시 레이스 컨디션 방어)
    const yearOptions = useMemo(() => {
        const years = [];
        let minYear = effectiveMinDate.getFullYear();
        const maxYear = effectiveMaxDate.getFullYear();
        // 현재 값의 연도가 minYear보다 이전이면 범위 확장
        if (parsed.year && parseInt(parsed.year) < minYear) {
            minYear = parseInt(parsed.year);
        }
        for (let y = maxYear; y >= minYear; y--) {
            years.push(y.toString());
        }
        return years;
    }, [effectiveMinDate, effectiveMaxDate, parsed.year]);

    // Generate month options (1-12)
    const monthOptions = useMemo(() => {
        const months = [];
        for (let m = 1; m <= 12; m++) {
            months.push(m.toString().padStart(2, '0'));
        }
        return months;
    }, []);

    // Generate day options based on selected year/month
    const dayOptions = useMemo(() => {
        const days = [];
        if (!parsed.year || !parsed.month) {
            // Default to 31 days if no year/month selected
            for (let d = 1; d <= 31; d++) {
                days.push(d.toString().padStart(2, '0'));
            }
            return days;
        }

        const year = parseInt(parsed.year);
        const month = parseInt(parsed.month);
        const daysInMonth = new Date(year, month, 0).getDate();

        for (let d = 1; d <= daysInMonth; d++) {
            days.push(d.toString().padStart(2, '0'));
        }
        return days;
    }, [parsed.year, parsed.month]);

    // Handle individual dropdown changes
    const handleChange = (field, newValue) => {
        let { year, month, day } = parsed;

        if (field === 'year') year = newValue;
        if (field === 'month') month = newValue;
        if (field === 'day') day = newValue;

        // Validate day against new month if needed
        if (year && month && day) {
            const daysInMonth = new Date(parseInt(year), parseInt(month), 0).getDate();
            if (parseInt(day) > daysInMonth) {
                day = daysInMonth.toString().padStart(2, '0');
            }

            // Construct and validate the full date
            const newDateStr = `${year}-${month}-${day}`;
            const newDate = new Date(newDateStr);

            // Check bounds
            if (newDate < effectiveMinDate) {
                // Clamp to min date
                onChange(effectiveMinDate.toISOString().split('T')[0]);
                return;
            }
            if (newDate > effectiveMaxDate) {
                // Clamp to max date
                onChange(effectiveMaxDate.toISOString().split('T')[0]);
                return;
            }

            onChange(newDateStr);
        } else if (year && month) {
            // Partial date - don't trigger onChange yet, but update internal
            // Only trigger when all three are selected
            // For now, we'll just wait
        }
    };

    const selectClass = `bg-black/40 border border-white/20 rounded px-2 py-2 text-white text-sm
        focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500
        disabled:opacity-50 disabled:cursor-not-allowed
        appearance-none cursor-pointer`;

    return (
        <div className={`flex items-center gap-1 ${className}`}>
            {/* Year */}
            <select
                value={parsed.year}
                onChange={(e) => handleChange('year', e.target.value)}
                disabled={disabled}
                className={`${selectClass} w-20`}
            >
                <option value="">Year</option>
                {yearOptions.map(y => (
                    <option key={y} value={y}>{y}</option>
                ))}
            </select>

            <span className="text-gray-500">-</span>

            {/* Month */}
            <select
                value={parsed.month}
                onChange={(e) => handleChange('month', e.target.value)}
                disabled={disabled}
                className={`${selectClass} w-16`}
            >
                <option value="">Mon</option>
                {monthOptions.map(m => (
                    <option key={m} value={m}>{m}</option>
                ))}
            </select>

            <span className="text-gray-500">-</span>

            {/* Day */}
            <select
                value={parsed.day}
                onChange={(e) => handleChange('day', e.target.value)}
                disabled={disabled}
                className={`${selectClass} w-16`}
            >
                <option value="">Day</option>
                {dayOptions.map(d => (
                    <option key={d} value={d}>{d}</option>
                ))}
            </select>
        </div>
    );
};

export default DateDropdown;
