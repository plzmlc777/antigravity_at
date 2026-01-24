import React from 'react';

/**
 * DynamicParameterForm - Schema-driven parameter form generator
 * 
 * Renders form inputs based on parameter_schema from the database.
 * Supports field types: select, number, time, text, checkbox
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

    const renderField = (field) => {
        const key = field.key || field.name;
        const value = values[key] ?? field.default ?? '';
        const fieldType = field.type || 'text';

        switch (fieldType) {
            case 'select':
                return (
                    <select
                        id={key}
                        value={value}
                        onChange={(e) => onChange(key, e.target.value)}
                        disabled={disabled}
                        className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
                    >
                        {(field.options || []).map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
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

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {schema.fields.map((field) => {
                const key = field.key || field.name;
                return (
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
            })}
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
