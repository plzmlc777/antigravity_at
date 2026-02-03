class EventBus {
    constructor() {
        this.listeners = new Set();
    }

    subscribe(listener) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    publish(event) {
        this.listeners.forEach((listener) => listener(event));
    }
}

const apiLogger = new EventBus();

// Ensure singleton instance across chunks/bundles by attaching to window
if (typeof window !== 'undefined') {
    if (!window.__apiLogger) {
        window.__apiLogger = apiLogger;
    }
}

export { apiLogger };
// Also export the window instance as default or fallback
export const getApiLogger = () => (typeof window !== 'undefined' ? window.__apiLogger : apiLogger);
