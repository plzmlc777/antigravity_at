import asyncio
from typing import List, Dict
from datetime import datetime

class LogBroadcaster:
    _instance = None
    
    def __init__(self):
        self.queues: List[asyncio.Queue] = []
        self.history: List[Dict] = [] # Store recent logs
        self.max_history = 50
        
    @staticmethod
    def get_instance():
        if LogBroadcaster._instance is None:
            LogBroadcaster._instance = LogBroadcaster()
        return LogBroadcaster._instance
        
    async def add_log(self, source: str, message: str):
        """
        Add a log message to all listening queues and history.
        """
        log_entry = {
            "time": datetime.now().isoformat(),
            "source": source,
            "msg": message
        }
        
        # Add to history
        self.history.append(log_entry)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        # Broadcast
        for q in self.queues:
            await q.put(log_entry)
            
    async def subscribe(self) -> asyncio.Queue:
        """
        Return a new queue for a subscriber, pre-filled with history.
        """
        q = asyncio.Queue()
        
        # Replay history
        for entry in self.history:
            await q.put(entry)
            
        self.queues.append(q)
        return q
        
    def unsubscribe(self, q: asyncio.Queue):
        if q in self.queues:
            self.queues.remove(q)
