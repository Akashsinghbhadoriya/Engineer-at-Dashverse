class EventBus:
    def __init__(self):
        self._handlers = []

    def subscribe(self, handler):
        self._handlers.append(handler)

    async def emit(self, node, execution, event="END", meta=None):
        if meta is None:
            meta = {}
        for handler in self._handlers:
            await handler(node, execution, event, meta)
