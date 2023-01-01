"""
A custom websocket client for udiscord, based on:
https://github.com/danni/uwebsockets/tree/esp8266/uwebsockets

MIT License

Copyright (c) 2019-2022 Danielle Madeley
Copyright (c) 2022-present Dorukyum

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# pyright: reportMissingImports=false
import random
import socket
from binascii import b2a_base64
from json import dumps, loads
from ssl import wrap_socket
from struct import pack, unpack

from micropython import const

# OP codes
OP_CONT = const(0x0)
OP_TEXT = const(0x1)
OP_BYTES = const(0x2)
OP_CLOSE = const(0x8)
OP_PING = const(0x9)
OP_PONG = const(0xA)

# close codes
CLOSE_OK = const(1000)
CLOSE_GOING_AWAY = const(1001)
CLOSE_PROTOCOL_ERROR = const(1002)
CLOSE_DATA_NOT_SUPPORTED = const(1003)
CLOSE_BAD_DATA = const(1007)
CLOSE_POLICY_VIOLATION = const(1008)
CLOSE_TOO_BIG = const(1009)
CLOSE_MISSING_EXTN = const(1010)
CLOSE_BAD_CONDITION = const(1011)


class NoDataException(Exception):
    pass


class ConnectionClosed(Exception):
    pass


class WebsocketClient:
    async def connect(self) -> None:
        sock = socket.socket()
        sock.connect(socket.getaddrinfo("gateway.discord.gg", 443)[0][4])
        # sock.setblocking(False)
        self._underlying = wrap_socket(sock)

        async def send_header(header, *args) -> None:
            self._underlying.write(header % args + "\r\n")

        # Sec-WebSocket-Key is 16 random bytes encoded in base64
        key = b2a_base64(bytes(random.getrandbits(8) for _ in range(16)))[:-1]

        await send_header(b"GET /?v=10&encoding=json HTTP/1.1")
        await send_header(b"Host: gateway.discord.gg:433")
        await send_header(b"Connection: Upgrade")
        await send_header(b"Upgrade: websocket")
        await send_header(b"Sec-WebSocket-Key: %s", key)
        await send_header(b"Sec-WebSocket-Version: 13")
        await send_header(b"Origin: http://gateway.discord.gg:443")
        await send_header(b"")

        header = self._underlying.readline()[:-2]  # type: ignore # readline isn't recognised
        assert header.startswith(b"HTTP/1.1 101 ")

        while header:
            header = self._underlying.readline()[:-2]  # type: ignore # readline isn't recognised

        self.open = True

    async def read_frame(self) -> tuple[bool, int, bytes]:
        # frame header
        two_bytes = self._underlying.read(2)

        if not two_bytes:
            raise NoDataException

        byte1, byte2 = unpack("!BB", two_bytes)

        # byte 1: FIN(1) _(1) _(1) _(1) OPCODE(4)
        fin = bool(byte1 & 0x80)
        op_code = byte1 & 0x0F

        # byte 2: MASK(1) LENGTH(7)
        mask = bool(byte2 & (1 << 7))
        length = byte2 & 0x7F

        if length == 126:  # magic number, length header is 2 bytes
            (length,) = unpack("!H", self._underlying.read(2))
        elif length == 127:  # magic number, length header is 8 bytes
            (length,) = unpack("!Q", self._underlying.read(8))

        mask_bits = self._underlying.read(4) if mask else b""

        try:
            data = self._underlying.read(length)
        except MemoryError:
            await self.close(CLOSE_TOO_BIG, reason="Received data is too big.")
            return True, OP_CLOSE, b""

        if mask:
            data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))
        return fin, op_code, data

    async def write_frame(self, op_code: int, data: bytes) -> None:
        length = len(data)

        # frame header
        # byte 1: FIN(1) _(1) _(1) _(1) OPCODE(4)
        byte1 = 0x80
        byte1 |= op_code

        # byte 2: MASK(1) LENGTH(7)
        byte2 = 0x80

        if length < 126:  # 126 is a magic value to use 2-byte length header
            byte2 |= length
            self._underlying.write(pack("!BB", byte1, byte2))
        elif length < (1 << 16):  # length fits in 2-bytes
            byte2 |= 126  # magic code
            self._underlying.write(pack("!BBH", byte1, byte2, length))
        elif length < (1 << 64):
            byte2 |= 127  # magic code
            self._underlying.write(pack("!BBQ", byte1, byte2, length))
        else:
            raise ValueError()

        mask_bits = pack("!I", random.getrandbits(32))
        self._underlying.write(mask_bits)
        data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))
        self._underlying.write(data)

    async def recv(self) -> dict[str, object] | None:
        while self.open:
            try:
                fin, op_code, data = await self.read_frame()
            except ValueError:
                return await self._close()

            if not fin:
                raise NotImplementedError()

            if op_code == OP_TEXT:
                return loads(data.decode("utf-8"))
            elif op_code == OP_BYTES:
                return loads(data)
            elif op_code == OP_CLOSE:
                return await self._close()
            elif op_code == OP_PING:
                await self.write_frame(OP_PONG, data)
            elif op_code == OP_CONT:
                raise NotImplementedError(op_code)
            else:
                raise ValueError(op_code)

    async def send(self, payload: dict[str, object]) -> None:
        assert self.open
        await self.write_frame(OP_BYTES, dumps(payload).encode("utf-8"))

    async def close(self, code: int = CLOSE_OK, *, reason: str = "") -> None:
        if self.open:
            buf = pack("!H", code) + reason.encode("utf-8")
            await self.write_frame(OP_CLOSE, buf)
            await self._close()

    async def _close(self) -> None:
        self.open = False
        self._underlying.close()
        raise ConnectionClosed()
