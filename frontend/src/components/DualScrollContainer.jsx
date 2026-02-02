import React, { useRef, useCallback, useState, useEffect } from 'react';

/**
 * DualScrollContainer - Provides synchronized top and bottom horizontal scrollbars
 *
 * @param {React.ReactNode} children - The content to be scrolled (typically a table)
 * @param {string} className - Additional classes for the container
 */
const DualScrollContainer = ({ children, className = '' }) => {
    const topScrollRef = useRef(null);
    const bottomScrollRef = useRef(null);
    const contentRef = useRef(null);
    const [contentWidth, setContentWidth] = useState(0);
    const isScrollingRef = useRef(null);

    // Update content width when children change
    useEffect(() => {
        if (contentRef.current) {
            const updateWidth = () => {
                setContentWidth(contentRef.current.scrollWidth);
            };
            updateWidth();

            // Use ResizeObserver for dynamic content
            const resizeObserver = new ResizeObserver(updateWidth);
            resizeObserver.observe(contentRef.current);

            return () => resizeObserver.disconnect();
        }
    }, [children]);

    // Sync scroll from top to bottom
    const handleTopScroll = useCallback(() => {
        if (isScrollingRef.current === 'bottom') return;
        isScrollingRef.current = 'top';
        if (bottomScrollRef.current && topScrollRef.current) {
            bottomScrollRef.current.scrollLeft = topScrollRef.current.scrollLeft;
        }
        requestAnimationFrame(() => {
            isScrollingRef.current = null;
        });
    }, []);

    // Sync scroll from bottom to top
    const handleBottomScroll = useCallback(() => {
        if (isScrollingRef.current === 'top') return;
        isScrollingRef.current = 'bottom';
        if (topScrollRef.current && bottomScrollRef.current) {
            topScrollRef.current.scrollLeft = bottomScrollRef.current.scrollLeft;
        }
        requestAnimationFrame(() => {
            isScrollingRef.current = null;
        });
    }, []);

    return (
        <div className={className}>
            {/* Top scrollbar */}
            <div
                ref={topScrollRef}
                onScroll={handleTopScroll}
                className="overflow-x-auto scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-transparent"
                style={{ height: '12px' }}
            >
                <div style={{ width: contentWidth, height: '1px' }} />
            </div>

            {/* Main content with bottom scrollbar */}
            <div
                ref={bottomScrollRef}
                onScroll={handleBottomScroll}
                className="overflow-x-auto"
            >
                <div ref={contentRef}>
                    {children}
                </div>
            </div>
        </div>
    );
};

export default DualScrollContainer;
