from collections.abc import Callable

EventHandler = Callable[[], None]


class EventBus:
    def __init__(self) -> None:
        self._events_dict: dict[str, list[EventHandler]] = {}

    def subscribe(self, event: str, handler: EventHandler) -> None:
        if event in self._events_dict:
            return

        self._events_dict[event] = [handler]

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        if event not in self._events_dict:
            return

        self._events_dict[event].remove(handler)

    def publish(self, event: str) -> None:
        if event not in self._events_dict:
            return

        for handler in self._events_dict[event]:
            handler()

    def clear(self) -> None:
        self._events_dict.clear()


event_bus = EventBus()
