import React from 'react';

/**
 * 공통 SymbolChip 컴포넌트 - 중앙 집중화된 종목 칩
 *
 * 지원 모드:
 * 1. 선택 모드 (Rank 탭): 클릭으로 선택, 드래그 앤 드롭
 * 2. 체크박스 모드 (Symbol Compare): 체크박스로 선택/해제
 */
const SymbolChip = ({
    symbol,                  // { code, name }
    isSelected = false,      // 선택 상태
    onSelect,                // 클릭 시 선택 핸들러
    onDelete,                // 삭제 핸들러
    showCheckbox = false,    // 체크박스 모드
    onCheckChange,           // 체크박스 변경 핸들러
    isChecked = false,       // 체크 상태
    draggable = false,       // 드래그 가능 여부
    isDragging = false,      // 드래그 중
    isDragOver = false,      // 드래그 오버 상태
    onDragStart,
    onDragOver,
    onDragLeave,
    onDrop,
    onDragEnd,
    index,
}) => {
    const baseStyles = "group flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer border transition-all";

    const getStateStyles = () => {
        if (isDragOver) return "border-yellow-500 border-dashed";
        if (isDragging) return "opacity-50";

        if (showCheckbox) {
            // 체크박스 모드 (Symbol Compare)
            return isChecked
                ? "bg-emerald-600/30 border-emerald-500 text-white"
                : "bg-black/30 border-white/10 hover:border-white/30 text-gray-400";
        } else {
            // 선택 모드 (Rank 탭)
            return isSelected
                ? "bg-blue-900/30 border-blue-500 text-blue-300"
                : "bg-black/20 border-white/10 text-gray-400 hover:bg-white/5";
        }
    };

    const handleClick = (e) => {
        if (showCheckbox && onCheckChange) {
            onCheckChange(!isChecked);
        } else if (onSelect) {
            onSelect(symbol.code);
        }
    };

    const handleDelete = (e) => {
        e.stopPropagation();
        if (onDelete) {
            onDelete(symbol.code);
        }
    };

    return (
        <div
            className={`${baseStyles} ${getStateStyles()} ${draggable ? 'cursor-grab' : ''}`}
            onClick={handleClick}
            draggable={draggable}
            onDragStart={draggable ? (e) => onDragStart?.(e, index) : undefined}
            onDragOver={draggable ? (e) => { e.preventDefault(); onDragOver?.(e, index); } : undefined}
            onDragLeave={draggable ? onDragLeave : undefined}
            onDrop={draggable ? (e) => onDrop?.(e, index) : undefined}
            onDragEnd={draggable ? onDragEnd : undefined}
        >
            {/* 체크박스 (Symbol Compare 모드) */}
            {showCheckbox && (
                <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => {
                        e.stopPropagation();
                        onCheckChange?.(e.target.checked);
                    }}
                    className="w-4 h-4 rounded accent-emerald-500"
                />
            )}

            {/* 종목 코드 및 이름 */}
            <span className="text-sm font-mono">
                {symbol.code}
                {symbol.name && (
                    <span className="text-xs opacity-70 ml-1">({symbol.name})</span>
                )}
            </span>

            {/* 삭제 버튼 */}
            {onDelete && (
                <button
                    onClick={handleDelete}
                    className="w-4 h-4 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-red-500/20 hover:text-red-400 transition-all text-xs"
                    title="Remove symbol"
                >
                    ×
                </button>
            )}
        </div>
    );
};

export default SymbolChip;
