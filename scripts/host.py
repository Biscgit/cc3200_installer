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

        path = "out/client.sh"
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
    console.log("Running commands for installation")

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
            async def run_command(command: str, log: str = None, fail_all: bool = True) -> asyncssh.SSHCompletedProcess:
                if log:
                    console.log(log)

                result = await conn.run(command)

                if result.stderr and fail_all:
                    console.log(f"ERROR: {result.stderr}")
                    console.log("Exiting programm...")
                    exit(1)

                return result

            await run_command("ping -c 1 duckduckgo.com", log="Checking internet connection")
            res = await run_command("sudo docker -v", log="Checking docker")

            if "command not found" in res.stdout:
                console.log("Docker not found. Installing...")
                commands = [
                    # remove false packages
                    "for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; "
                    "do sudo apt-get remove $pkg; done",
                    # add repo
                    "sudo apt-get update",
                    "sudo apt-get install -y ca-certificates curl",
                    "sudo install -m 0755 -d /etc/apt/keyrings",
                    "sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc",
                    "sudo chmod a+r /etc/apt/keyrings/docker.asc",
                    # setup repo
                    r"""echo \
                    "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
                    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
                    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null""",
                    "sudo apt-get update",
                    # install docker
                    "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin "
                    "docker-compose-plugin",
                ]

                for c in commands:
                    await run_command(c, log=f"Running `{c}`")

                res = await run_command("sudo docker -v", log="Checking docker")
                if "command not found" in res.stdout:
                    console.log("Failed to install docker. Please check manually")
                    console.log("Exiting...")
                    exit(1)

                console.log("Successfully installed docker")


async def generate_certs():
    for x in ["host_key", "host_key.pub", "client_key", "client_key.pub"]:
        if os.path.exists(f"certs/{x}"):
            os.remove(f"certs/{x}")

    console.log("Generating host certificates")
    task = asyncio.create_task(asyncio.sleep(0.5))

    proc = await asyncio.create_subprocess_shell(
        "ssh-keygen -f certs/host_key -N ''",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    assert stderr.decode() == ""
    await task

    console.log("Generating client certificates")
    task = asyncio.create_task(asyncio.sleep(0.5))

    proc = await asyncio.create_subprocess_shell(
        "ssh-keygen -f certs/client_key -N ''",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    assert stderr.decode() == ""
    await task


async def generate_client():
    for x in ["client.sh"]:
        if os.path.exists(f"out/{x}"):
            os.remove(f"out/{x}")

    console.log("Generating installer script")
    task = asyncio.create_task(asyncio.sleep(0.5))

    async with aiofiles.open("certs/host_key", "r") as f:
        host_key = await f.read()
        host_key = host_key.rstrip("\n")

    async with aiofiles.open("certs/client_key.pub", "r") as f:
        client_pub = await f.read()
        client_pub = client_pub.rstrip("\n")

    async with aiofiles.open("templates/client.py", "r") as file:
        template = await file.read()

        # insert keys
        template = template.replace(
            "host_key = [[]]",
            f"host_key = '''{host_key}'''",
            1,
        )
        template = template.replace(
            "client_pub = [[]]",
            f"client_pub = '''{client_pub}'''",
            1,
        )

    async with aiofiles.open("templates/install.sh", "r") as f:
        script = await f.read()

    async with aiofiles.open("out/client.sh", "w") as file:
        script = script.replace(
            "[[script]]",
            template,
            1,
        )

        await file.write(script)

    proc = await asyncio.create_subprocess_shell(
        "chmod +x out/client.sh",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    assert stderr.decode() == ""

    await task


async def generate_scripts():
    # generate certificates
    with console.status(
            "[bold green4]    Generating scripts...",
            spinner="bouncingBar"
    ):
        console.log("Creating folders")
        Path("./certs").mkdir(parents=True, exist_ok=True)
        Path("./out").mkdir(parents=True, exist_ok=True)

        await generate_certs()
        await generate_client()


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
