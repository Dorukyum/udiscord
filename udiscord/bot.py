# pyright: reportMissingImports=false
import os
import time
from random import random

import network
import uasyncio
from micropython import const

from .presence import Activity
from .websocket import WebsocketClient


class Bot:
    sequence: int | None = None
    session_id: int | None = None

    DISPATCH = const(0)
    HEARTBEAT = const(1)
    IDENTIFY = const(2)
    PRESENCE_UPDATE = const(3)
    VOICE_STATE_UPDATE = const(4)
    RESUME = const(6)
    RECONNECT = const(7)
    REQUEST_GUILD_MEMBERS = const(8)
    INVALID_SESSION = const(9)
    HELLO = const(10)
    ACK = const(11)

    def __init__(
        self,
        *,
        activity: Activity | None = None,
        status: str | None = None,
        intents: int = 0,
    ) -> None:
        self.activity = activity
        self.status = status
        self.intents = intents
        self.socket = WebsocketClient()

    def connect_wlan(self, ssid: str, key: str, attempts: int = 5) -> None:
        """Establish a WLAN connection."""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        attempt = 1
        while not wlan.isconnected():
            print(f"Attempting WLAN connection... [{attempt}/{attempts}]")
            if wlan.status() != network.STAT_CONNECTING:
                wlan.connect(ssid, key)
            time.sleep(1)
            attempt += 1
            if attempt == attempts:
                raise RuntimeError(f'Could not establish WLAN connection to "{ssid}".')

        print(f'WLAN connected to "{ssid}".')

    async def send_heartbeat(self) -> None:
        await self.socket.send(
            {
                "op": self.HEARTBEAT,
                "d": self.sequence,
            }
        )

    async def heartbeat(self, interval: float) -> None:
        self._heartbeat_ack = True
        await uasyncio.sleep(interval * random())
        await self.send_heartbeat()
        while True:
            if self._heartbeat_ack:
                await uasyncio.sleep(interval)
                await self.send_heartbeat()
                self._heartbeat_ack = False
            else:
                await self.socket.close()

    async def identify(self) -> None:
        await self.socket.send(
            {
                "op": self.IDENTIFY,
                "d": {
                    "token": self.token,
                    "intents": self.intents,
                    "properties": {
                        "os": os.uname()[0],
                        "browser": "udiscord",
                        "device": "udiscord",
                    },
                    "presence": {
                        "activities": [self.activity.to_dict()]
                        if self.activity
                        else [],
                        "status": self.status or "online",
                    },
                },
            }
        )

    async def receive(self) -> None:
        while self.socket.open:
            data = await self.socket.recv()
            if data is not None:
                print(f"[RECV] {data}")

    async def connect(self) -> None:
        """Connect to the Discord gateway."""
        await self.socket.connect()
        if self.session_id:
            await self.resume()
        else:
            await self.identify()
        await uasyncio.create_task(self.receive())

    async def resume(self) -> None:
        await self.socket.send(
            {
                "op": self.RESUME,
                "d": {
                    "token": self.token,
                    "session_id": self.session_id,
                    "seq": self.sequence,
                },
            }
        )

    def run(self, token: str) -> None:
        """Run the bot by connecting to the Discord gateway."""
        self.token = token
        uasyncio.run(self.connect())
