import React, { useState } from 'react';
import { INTERVAL_OPTIONS } from '../constants/intervals';

/**
 * DynamicParameterForm - Schema-driven parameter form generator
 *
 * Renders form inputs based on parameter_schema from the database.
 * Supports field types: select, number, time, text, checkbox, multiselect, combobox
 *
 * Props:
 * - schema: { fields: [...] } from strategy.parameter_schema
 * - values: { [key]: value } current form values
 * - onChange: (key, value) => void callback
 * - disabled: boolean to disable all inputs
 */
const DynamicParameterForm = ({ schema, values = {}, onChange, disabled = false }) => {
    if (!schema || !schema.fields || schema.fields.length === 0) {
        return (
            <div className="text-gray-500 text-sm italic">
                No parameter schema available for this strategy.
            </div>
        );
    }

    // Active multiselect dropdown key
    const [openMultiselect, setOpenMultiselect] = useState(null);

    // Check visible_when conditions: { "field_name": { "gt": N, "eq": "value" } }
    // All conditions must match (AND logic). Supports: gt, gte, lt, lte, eq, ne
    const isFieldVisible = (field) => {
        const conditions = field.visible_when;
        if (!conditions) return true;

        // Resolve current value for a field (check values first, then find default from schema)
        const getVal = (fieldName) => {
            if (values[fieldName] !== undefined) return values[fieldName];
            const schemaField = schema.fields.find(f => (f.key || f.name) === fieldName);
            return schemaField?.default;
        };

        return Object.entries(conditions).every(([fieldName, ops]) => {
            const val = getVal(fieldName);
            const numVal = typeof val === 'string' ? parseFloat(val) : val;
            return Object.entries(ops).every(([op, target]) => {
                switch (op) {
                    case 'gt':  return numVal > target;
                    case 'gte': return numVal >= target;
                    case 'lt':  return numVal < target;
                    case 'lte': return numVal <= target;
                    case 'eq':  return val == target;  // loose equality for string/number compat
                    case 'ne':  return val != target;
                    default:    return true;
                }
            });
        });
    };

    // Reset hidden fields to their schema defaults when visibility changes.
    // This ensures toggling e.g. "Martingale: off" resets all dependent params.
    React.useEffect(() => {
        if (!schema?.fields || !onChange) return;
        schema.fields.forEach((field) => {
            const key = field.key || field.name;
            if (field.default !== undefined && !isFieldVisible(field)
                && values[key] !== undefined && values[key] != field.default) {
                onChange(key, field.default);
            }
        });
    });

    const renderField = (field) => {
        const key = field.key || field.name;
        const value = values[key] ?? field.default ?? '';
        const fieldType = field.type || 'text';

        switch (fieldType) {
            case 'select':
                // Use centralized INTERVAL_OPTIONS for interval field
                const selectOptions = key === 'interval'
                    ? INTERVAL_OPTIONS
                    : (field.options || []).map(opt =>
                        typeof opt === 'string' ? { value: opt, label: opt } : opt
                    );
                return (
                    <select
                        id={key}
                        value={value}
                        onChange={(e) => onChange(key, e.target.value)}
                        disabled={disabled}
                        className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                    >
                        {selectOptions.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                );

            case 'number':
                return (
                    <input
                        type="number"
                        id={key}
                        value={value}
                        onChange={(e) => onChange(key, parseFloat(e.target.value) || 0)}
                        disabled={disabled}
                        min={field.min}
                        max={field.max}
                        step={field.step || 1}
                        className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                    />
                );

            case 'time':
                // Time fields rendered as select with time options
                const timeOptions = field.options || generateTimeOptions();
                return (
                    <select
                        id={key}
                        value={value}
                        onChange={(e) => onChange(key, e.target.value)}
                        disabled={disabled}
                        className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                    >
                        {timeOptions.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                    </select>
                );

            case 'combobox':
                // Select with free-text input (datalist)
                const comboId = `${key}-list`;
                const comboOptions = (field.options || []).map(opt =>
                    typeof opt === 'string' ? { value: opt, label: opt } : opt
                );
                return (
                    <div className="relative">
                        <input
                            type="text"
                            id={key}
                            list={comboId}
                            value={value}
                            onChange={(e) => onChange(key, e.target.value)}
                            disabled={disabled}
                            placeholder={field.placeholder || 'Select or type...'}
                            className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                        />
                        <datalist id={comboId}>
                            {comboOptions.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                        </datalist>
                    </div>
                );

            case 'checkbox':
                return (
                    <input
                        type="checkbox"
                        id={key}
                        checked={!!value}
                        onChange={(e) => onChange(key, e.target.checked)}
                        disabled={disabled}
                        className="w-4 h-4 rounded border-gray-600 text-cyan-600 focus:ring-cyan-500 bg-gray-700"
                    />
                );

            case 'multiselect':
                const msOptions = (field.options || []).map(opt =>
                    typeof opt === 'string' ? { value: opt, label: opt } : opt
                );
                const selected = typeof value === 'string' ? value.split(',').filter(Boolean) : (Array.isArray(value) ? value : []);
                const isOpen = openMultiselect === key;
                return (
                    <div className="relative">
                        <div
                            onClick={() => !disabled && setOpenMultiselect(isOpen ? null : key)}
                            className={`w-full bg-black/40 border rounded px-3 py-2 text-sm text-white cursor-pointer min-h-[38px] flex items-center justify-between ${
                                isOpen ? 'border-cyan-500 ring-1 ring-cyan-500' : 'border-white/20'
                            } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                            <span className="truncate">
                                {selected.length > 0
                                    ? selected.map(v => msOptions.find(o => o.value === v)?.label || v).join(', ')
                                    : <span className="text-gray-500">Select options...</span>
                                }
                            </span>
                            <span className="text-gray-400 text-xs ml-2">▼</span>
                        </div>
                        {isOpen && (
                            <div className="absolute z-50 mt-1 w-full bg-[#1a1c23] border border-white/20 rounded-lg shadow-xl max-h-60 overflow-y-auto">
                                {msOptions.map(opt => {
                                    const isSelected = selected.includes(opt.value);
                                    return (
                                        <div
                                            key={opt.value}
                                            onClick={() => {
                                                const newSelected = isSelected
                                                    ? selected.filter(v => v !== opt.value)
                                                    : [...selected, opt.value];
                                                onChange(key, newSelected.join(','));
                                            }}
                                            className={`px-3 py-2 text-sm cursor-pointer hover:bg-white/10 flex items-center justify-between ${
                                                isSelected ? 'bg-cyan-900/40 text-cyan-300' : 'text-gray-300'
                                            }`}
                                        >
                                            <span>{opt.label}</span>
                                            {isSelected && <span>✓</span>}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        {isOpen && (
                            <div
                                className="fixed inset-0 z-40"
                                onClick={(e) => { e.stopPropagation(); setOpenMultiselect(null); }}
                            />
                        )}
                    </div>
                );

            case 'text':
            default:
                return (
                    <input
                        type="text"
                        id={key}
                        value={value}
                        onChange={(e) => onChange(key, e.target.value)}
                        disabled={disabled}
                        placeholder={field.placeholder || ''}
                        className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                    />
                );
        }
    };

    // Group labels for section headers
    const GROUP_LABELS = {
        common: 'Common',
        martingale: 'Position Sizing',
    };

    return (
        <div className="space-y-1">
            {(() => {
                const sections = [];
                let currentFields = [];
                let currentGroup = null;

                const flushSection = () => {
                    if (currentFields.length > 0) {
                        if (currentGroup && GROUP_LABELS[currentGroup]) {
                            sections.push(
                                <div key={`hdr-${currentGroup}`} className="pt-2 pb-1 border-t border-white/5 first:border-t-0 first:pt-0">
                                    <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">
                                        {GROUP_LABELS[currentGroup]}
                                    </span>
                                </div>
                            );
                        }
                        sections.push(
                            <div key={`grp-${currentGroup || 'strategy'}`} className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                {currentFields}
                            </div>
                        );
                        currentFields = [];
                    }
                };

                schema.fields.forEach((field) => {
                    const key = field.key || field.name;
                    const group = field.group || null;

                    // Skip hidden fields based on visible_when conditions
                    if (!isFieldVisible(field)) return;

                    // Detect group transition
                    if (group !== currentGroup) {
                        flushSection();
                        currentGroup = group;
                    }

                    currentFields.push(
                        <div key={key} className="space-y-1">
                            <label
                                htmlFor={key}
                                className="text-xs font-medium text-gray-400 block"
                                title={field.description}
                            >
                                {field.label || key}
                            </label>
                            {renderField(field)}
                        </div>
                    );
                });

                flushSection();
                return sections;
            })()}
        </div>
    );
};

// Helper: Generate time options (00:00 to 23:30 in 30min intervals)
const generateTimeOptions = () => {
    const options = [];
    for (let h = 0; h < 24; h++) {
        options.push(`${h.toString().padStart(2, '0')}:00`);
        options.push(`${h.toString().padStart(2, '0')}:30`);
    }
    return options;
};

export default DynamicParameterForm;
