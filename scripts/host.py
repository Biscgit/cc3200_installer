import asyncio
import json
import time

import asyncssh
from aiohttp import web
import aiofiles
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
        "I can deploy the script on the server on my own\n"
        "[bold]\[q][/bold]:\n"  # noqa
        "Exist installation script\n\n"
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
        console.log("Terminated and cleaned up webserver")


async def get_client_broadcast() -> tuple[str, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    server_address = ('', broadcast_port)
    sock.bind(server_address)

    try:
        with console.status("[bold green4]", spinner="bouncingBar") as status:
            await asyncio.sleep(1 - (time.time() % 1))
            console.log("Started client listener")
            status.update(status="[bold green4]    Waiting for client message...")

            message, _ = await loop.run_in_executor(None, sock.recvfrom, 4096)
            body = json.loads(message)

            if body.get("can_accept") is True:
                data = body["ip"], body["port"]
                console.log(f"Found ssh client on {data[0]}:{data[1]}")

                return data

    finally:
        sock.close()


async def run_client(address: str, port: int):
    console.log("Running commands for installation:")

    async with aiofiles.open("certs/client_key", "r") as file:
        client_key = await file.read()

    with console.status(
            "[bold green4]    Installing TonieCloud...",
            spinner="bouncingBar"
    ):
        async with asyncssh.connect(
                address,
                port=port,
                username='user',
                client_keys=[asyncssh.import_private_key(client_key)],
                known_hosts=None,
        ) as conn:
            await asyncio.sleep(1)
            for x in range(3):
                command = "echo 'Hello, world!'"
                console.log(f"Running `{command}`")
                result = await conn.run('echo "Hello, world!"')
                await asyncio.sleep(1)
                # print(result.stdout, end='')
                # print(result.stderr, file=sys.stderr)


async def generate_scripts():
    # generate certificates
    with console.status(
            "[bold green4]    Generating scripts...",
            spinner="bouncingBar"
    ):
        # certificates
        console.log("Creating folder")
        Path("./certs").mkdir(parents=True, exist_ok=True)
        for x in ["host_key", "host_key.pub", "client_key", "client_key.pub"]:
            if os.path.exists(f"certs/{x}"):
                os.remove(f"certs/{x}")

        console.log("Generating host certificates")
        proc = await asyncio.create_subprocess_shell(
            "ssh-keygen -f certs/host_key -N ''",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.5)
        _, stderr = await proc.communicate()
        assert stderr.decode() == ""

        console.log("Generating client certificates")
        proc = await asyncio.create_subprocess_shell(
            "ssh-keygen -f certs/client_key -N ''",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.5)
        _, stderr = await proc.communicate()
        assert stderr.decode() == ""

        # generate script
        # ToDo


async def main():
    print_welcome()

    # ask which mode user wants
    option = await setup()
    console.print("\nStarting installation", style="bold steel_blue1")

    if option == "1":
        # generate script and launch server
        await generate_scripts()
        await WebServer.start_server()

    elif option == "2":
        # only generate a script
        await generate_scripts()

    elif option == "q":
        console.log("Existing...")
        exit(0)

    else:
        console.print("[red]invalid option[/red]\nexiting...")
        exit(1)

    # wait for the client to connect
    client_addr = await get_client_broadcast()

    if WebServer.is_running is True:
        await WebServer.stop_server()

    try:
        await run_client(*client_addr)
    except (OSError, asyncssh.Error) as exc:
        print('Error connecting to server: ' + str(exc))


if __name__ == '__main__':
    console.log("Welcome!")
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(main())

    finally:
        loop.close()

    console.log("Programm finished")
    exit(0)
