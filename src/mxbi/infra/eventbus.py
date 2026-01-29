from typing import Callable


class EventBus:
    def __init__(self) -> None:
        self._events_dict: dict[str, list[Callable]] = {}

    def subscribe(self, event: str, handler: Callable) -> None:
        if event not in self._events_dict:
            self._events_dict[event] = [handler]

        self._events_dict[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
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
