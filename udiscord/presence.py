# pyright: reportMissingImports=false
from micropython import const


class Status:
    ONLINE = "online"
    DND = "dnd"
    DO_NOT_DISTURB = DND
    IDLE = "idle"
    INVISIBLE = "invisible"
    OFFLINE = "offline"


class ActivityType:
    GAME = const(0)
    STREAMING = const(1)
    LISTENING = const(2)
    WATCHING = const(3)
    CUSTOM = const(4)
    COMPETING = const(5)


class Activity:
    def __init__(self, name: str, type: int, url: str | None = None) -> None:
        self.name = name
        self.type = type
        self.url = url

    def to_dict(self) -> dict[str, str | int]:
        data = {"name": self.name, "type": self.type}
        if self.url is not None:
            data["url"] = self.url
        return data
