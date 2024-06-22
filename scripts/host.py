import asyncio
import json

import asyncssh
import logging
import socket
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client_key = open("client_key", "r").read()

broadcast_port = 37021


async def get_client_broadcast() -> tuple[str, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    server_address = ('', broadcast_port)
    sock.bind(server_address)

    try:
        logger.info("Waiting for client connection...")

        message, _ = await loop.run_in_executor(None, sock.recvfrom, 4096)
        body = json.loads(message)

        if body.get("can_accept") is True:
            data = body["ip"], body["port"]
            logger.info(f"Found ssh client on {data[0]}:{data[1]}")

            return data

    finally:
        sock.close()


async def run_client(address: str, port: int):
    async with asyncssh.connect(
            address,
            port=port,
            username='user',
            client_keys=[asyncssh.import_private_key(client_key)],
            known_hosts=None,
    ) as conn:
        result = await conn.run('echo "Hello, world!"')
        print(result.stdout, end='')
        print(result.stderr, file=sys.stderr)


async def main():
    client_addr = await get_client_broadcast()
    try:
        await run_client(*client_addr)
    except (OSError, asyncssh.Error) as exc:
        print('Error connecting to server: ' + str(exc))


if __name__ == '__main__':
    logger.info("Launching Autoinstaller")
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(main())

    finally:
        loop.close()

    logger.info("Programm gracefully finished")
    exit(0)
