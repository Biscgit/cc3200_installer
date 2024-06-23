import asyncio
import json
import time

import asyncssh
from aiohttp import web
import logging
from pathlib import Path
import rich
from rich.console import Console
from rich.panel import Panel
import socket
import socketserver
import sys
import os

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client_key = open("client_key", "r").read()
console = Console()

broadcast_port = 37021

logo = r"""
   _         _         _____           _   
  /_\  _   _| |_ ___   \_   \_ __  ___| |_ 
 //_\\| | | | __/ _ \   / /\/ '_ \/ __| __|
/  _  \ |_| | || (_) /\/ /_ | | | \__ \ |_ 
\_/ \_/\__,_|\__\___/\____/ |_| |_|___/\__|   
-==--==--==--==--==--==--==- by Biscgit -==-                                       
"""


def print_welcome() -> None:
    print(logo)
    console.print("Launching autoinstaller...", style="bold steel_blue1")


async def setup() -> str:
    console.print(
        "Welcome to the TonieCloud installer!\n"
        "This script will make your life as easy as possible.\n"
        "Ensure your server is running a debian based distro (like RaspbianOS).\n\n"
        "[bold steel_blue1]Choose an Option to continue:[/bold steel_blue1]\n"
        "[bold][1] (recommended)[/bold]:\n"
        "Easy script deploy\n"
        "[bold][2][/bold]:\n"
        "I can deploy the script on the server on my own\n\n"
        "[bold]Enter here[/bold] (default 1):",
        end=" "
    )
    user_input = await loop.run_in_executor(None, input) or "1"
    return user_input


class WebServer:
    runner: web.AppRunner | None = None
    server: web.TCPSite | None = None
    is_running: bool = False

    @staticmethod
    async def download_script(request: web.Request):
        console.log(f"Request for download from host: {request.headers.get('Host')}")

        path = "client.py"
        headers = {'Content-Disposition': 'attachment; filename="run.sh"'}

        return web.FileResponse(path, headers=headers)

    @staticmethod
    async def start_server():
        console.log("Starting file server")

        app = web.Application()
        app.router.add_get("/install.sh", WebServer.download_script)

        runner = web.AppRunner(app)
        WebServer.runner = runner

        await runner.setup()

        # get available random port
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        with socketserver.TCPServer(("localhost", 0), None) as s:  # noqa
            _, port = s.server_address

        server = web.TCPSite(runner, ip_address, port)
        WebServer.server = server
        await server.start()

        WebServer.is_running = True

        console.log(Panel(
            "[bold]Copy following command and execute it on your server.[/bold]\n\n"
            f"\t[bold bright_white]curl -s http://{ip_address}:{port}/install.sh | bash[/bold bright_white]\n\n"
            "You might get promoted to enter your admin password to install missing packages or libraries.",
            expand=False,
        ))

    @staticmethod
    async def stop_server():
        if server := WebServer.server:
            await server.stop()
            WebServer.server = None

        if runner := WebServer.runner:
            await runner.shutdown()
            await runner.cleanup()
            WebServer.runner = None

        WebServer.is_running = False
        logger.info("Terminated and cleaned up webserver")


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
