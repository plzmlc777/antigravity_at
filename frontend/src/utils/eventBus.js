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

export const apiLogger = new EventBus();
