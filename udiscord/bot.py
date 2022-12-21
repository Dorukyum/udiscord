# pyright: reportMissingImports=false

import os
import time
from random import random

import network
import uasyncio
from async_websocket_client import AsyncWebsocketClient

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    const = lambda x: x


__all__ = ("Bot",)


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

    def __init__(self, *, intents: int = 0) -> None:
        self.intents = intents

        self.socket = AsyncWebsocketClient()

    def connect_wlan(self, ssid: str, key: str, attempts: int = 3) -> None:
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
                raise RuntimeError('Could not establish WLAN connection to "{ssid}".')

        print(f'WLAN connected to "{ssid}".')

    async def send(self, payload: dict) -> None:
        await self.socket.send(payload)

    async def send_heartbeat(self) -> None:
        await self.send(
            {
                "op": 1,
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
                ...  # todo: await self.close()

    async def identify(self) -> None:
        await self.send(
            {
                "op": 2,
                "d": {
                    "token": self.token,
                    "intents": self.intents,
                    "properties": {
                        "os": os.uname()[0],
                        "browser": "udiscord",
                        "device": "udiscord",
                    },
                    # "presence": {
                    #     "activities": [{"name": "with the API", "type": 0}],
                    #     "status": "idle",
                    # },
                },
            }
        )

    async def receive(self) -> None:
        while await self.socket.open():
            data = await self.socket.recv()
            if data is not None:
                print(f"[RECV] {data}")

    async def connect(self) -> None:
        """Connect to the Discord gateway."""
        await self.socket.handshake("wss://gateway.discord.gg/?v=10&encoding=json")
        if self.session_id:
            await self.resume()
        else:
            await self.identify()
        await uasyncio.create_task(self.receive())

    async def resume(self) -> None:
        await self.send(
            {
                "op": 6,
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
