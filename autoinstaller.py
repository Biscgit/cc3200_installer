#!/usr/bin/python3

import asyncio
import importlib
import json
import os
import typing
from pathlib import Path
import socket
import socketserver
import time

import aiofiles
import aiohttp
from aiohttp import web
import asyncssh
from rich.console import Console
from rich.panel import Panel

try:
    cc = importlib.import_module("cc3200tool.cc3200tool.cc")
except ModuleNotFoundError:
    cc = None


class ConsoleLogger(Console):
    DEBUG = False

    def debug(self, text: str, *form):
        if ConsoleLogger.debug:
            if form:
                text %= form
            self.log(f"[grey66]{text}[/grey66]")

    def info(self, text: str, *form):
        if form:
            text %= form
        self.log(f"[grey82]{text}[/grey82]")

    def warning(self, text: str, *form):
        if form:
            text %= form
        self.log(f"[yellow1][bold]Warning:[/bold] {text}[/yellow1]")

    def warn(self, text: str, *form):
        self.warning(text, *form)

    def error(self, text: str, *form):
        if form:
            text %= form
        self.log(f"[red1][bold]Error:[/bold] {text}[/red1]")


console = ConsoleLogger()
broadcast_port = 37021

logo = r"""[bold][white]
   _         _         _____           _   
  /_\  _   _| |_ ___   \_   \_ __  ___| |_ 
 //_\\| | | | __/ _ \   / /\/ '_ \/ __| __|
/  _  \ |_| | || (_) /\/ /_ | | | \__ \ |_ 
\_/ \_/\__,_|\__\___/\____/ |_| |_|___/\__| [/white]  
─══───══───══───══───══───══ [orange_red1]by Biscgit[/orange_red1] ══─[/bold]                                      
"""

circuit = r"""
  [bold]How to connect the cable's pins to your uart usb adapter[/bold] (TC2050) 
    
    
[medium_purple4]                       ╭───────────────────────  [bold]GND[/medium_purple4][/bold]
[yellow1]                 ╭─────[/yellow1][medium_purple4]│[/medium_purple4][yellow1]──┬────────────────────  [bold]3V3[/yellow1][/bold]     
[yellow1]                 │[/yellow1]     [medium_purple4]│[/medium_purple4]  [yellow1]│[/yellow1]  [deep_sky_blue1]╭─────────────────  [bold]RXD[/deep_sky_blue1][/bold]                  
[yellow1]                 │[/yellow1]     [medium_purple4]│[/medium_purple4]  [yellow1]│[/yellow1]  [deep_sky_blue1]│[/deep_sky_blue1]
              ╔══════🭷🭷🭷🭷🭷══════╗
              ║ [bold] [yellow1]🯱[/yellow1]  [grey58]🯳[/grey58]  [medium_purple4]🯵[/medium_purple4]  [yellow1]🯷[/yellow1]  [deep_sky_blue1]🯹[/deep_sky_blue1] [/bold] ║              [bold]TC2050-[/bold]
              ║                 ╟──────────── [bold]Connector[/bold]
              ║ [bold] [grey58]🯲  🯴  🯶[/grey58]  [spring_green3]🯸[/spring_green3] [deep_pink2]🯱︎🯰[/deep_pink2] [/bold] ║               [bold]Head[/bold]
              ╚═════════════════╝
                          [spring_green3]│[/spring_green3]  [deep_pink2]│[/deep_pink2]
                          [spring_green3]│[/spring_green3]  [deep_pink2]╰─────────────────  [bold]TXD[/deep_pink2][/bold]
[spring_green3]                          ╰────────────────────  [bold]DTR[/spring_green3][/bold]
"""


def print_welcome() -> None:
    console.print("Launching autoinstaller...", style="bold steel_blue1")
    console.print(logo)


async def print_description():
    console.print(
        "[bold]Welcome to the TeddyCloud installer![/bold]\n"
        "This script will make your life as easy as possible.\n"
        "It works on Linux and only with the CC3200 Box!\n"
        "Ensure your server is running a debian based distro (like RaspbianOS).\n"
        "The author recommends a fresh RaspbianOS installation\n"
    )


async def setup() -> str:
    can_dump = "grey42" if cc is None else "grey82"
    console.print(
        "[bold steel_blue1]Choose an Option to continue:[/bold steel_blue1]\n"
        f"[{can_dump}][bold](1)[/bold] "
        f"Dump certificates from TonieBox[/{can_dump}]\n"
        "[grey82][bold](2)[/bold] "
        "Launch connector helper (TC2050)\n"
        "[bold](3)[/bold] "
        "Easy cloud deploy\n"
        "[bold](4)[/bold] "
        "Manual cloud deploy\n"
        "[bold](q)[/bold] "
        "Exit installation script[/grey82]\n\n"
        "[bold]Enter here[/bold] (default q):",
        end=" "
    )
    try:
        user_input = await loop.run_in_executor(None, input) or "q"
        return user_input

    except KeyboardInterrupt:
        return "q"


last_usb: typing.Optional[str] = None


async def get_usb_port() -> typing.Optional[str]:
    global last_usb
    if last_usb:
        console.print(
            f"\nPreviously selected device on `{last_usb}`. "
            "[bold]Use that? [[green4]Y[/green4]/[red3]n[/red3]] [/bold]",
            end=""
        )
        choice = await loop.run_in_executor(None, input)
        if choice.lower() == "y" or choice == "":
            return last_usb

        if choice.lower() != "n":
            console.error(f"Invalid option: {choice}\n")
            return None

    console.print(
        "\nConnect the firmware cable to your computer and press enter to continue...",
        style="bold steel_blue1",
        end=" ",
    )
    await loop.run_in_executor(None, input)

    console.info("Searching for usb devices")
    proc = await asyncio.create_subprocess_shell(
        "lsusb",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    console.print(
        "\nSelect the device in the list below",
        style="bold steel_blue1",
    )

    devices = []
    default = None

    for line in stdout.decode().splitlines():
        *parts, name = line.split(" ", maxsplit=6)

        if "Linux Foundation" in name:
            continue

        path = f"/dev/bus/usb/{parts[1]}/{parts[3][:-1]}"
        devices.append(path)

        index = len(devices)
        is_default = False

        if default is None and "uart" in name.lower():
            default = index
            is_default = True

        console.print(
            f"[bold][{index}][/bold] {name}",
            style="bold green" if is_default else "",
        )

    if not devices:
        console.print("No devices found", style="bold red")
        return None

    console.print(f"[bold]Enter here[/bold] (default {default}):", end=" ")
    try:
        user_input = await loop.run_in_executor(None, input) or default.__str__()
        dev_path = devices[int(user_input) - 1]

    except (IndexError, TypeError, ValueError):
        console.print("Invalid option\n", style="bold red")
        return

    except KeyboardInterrupt:
        return

    # from dev path to /dev/tty
    console.print()
    console.info("Looking for corresponding serial port")
    proc = await asyncio.create_subprocess_shell(
        f"udevadm info --name={dev_path} | grep DEVPATH",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    base_device = stdout.decode().split("=")[1].strip()

    ttys = [x for x in os.listdir("/dev/") if x.startswith("ttyUSB")]
    for tty in ttys:
        device_path = f"/dev/{tty}"
        proc = await asyncio.create_subprocess_shell(
            f"udevadm info --name={device_path} | grep DEVPATH",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        device_name = stdout.decode().split("=")[1].strip()

        if device_name.startswith(base_device):
            console.info(f"Found serial port {device_path} for {dev_path}")
            last_usb = dev_path
            return device_path

    console.error("No serial ports found for that device!\n")
    return None


async def run_cc_command(command: str, error_msg: str, last_command: bool = True) -> bool:
    try:
        await loop.run_in_executor(
            None,
            cc.main,
            command.split(" "),
            console,
            'cc3200tool.cc3200tool.cc'
        )

    except cc.ExitException as e:
        code = e.__str__()
        console.error(f"{error_msg} Errorcode {code}")
        return False

    else:
        return True

    finally:
        if last_command:
            console.print(
                "You can now disconnect your device.\n",
                style="bold steel_blue1",
            )


async def dump_certificates(path: str) -> bool:
    console.print(
        "\nConnect the Toniebox and press enter to continue...",
        style="bold steel_blue1",
        end=" ",
    )
    await loop.run_in_executor(None, input)
    with console.status(
            "[bold green4]    Dumping files using modified cc3200tool",
            spinner="bouncingBar"
    ):
        console.info("Creating dump folder")
        folder = "./certs/box/"
        os.makedirs(folder, exist_ok=True)

        console.info("Dumping certificates")
        command = (
            f"-p {path} "
            f"--reset dtr "
            f"read_file /cert/ca.der {folder}ca.der "
            f"read_file /cert/client.der {folder}client.der "
            f"read_file /cert/private.der {folder}private.der"
        )

        return await run_cc_command(command, "Failed to read certificates from device.")


class WebServer:
    runner: web.AppRunner | None = None
    server: web.TCPSite | None = None
    is_running: bool = False

    @staticmethod
    async def download_script(request: web.Request):
        console.info(f"Request for download from host: {request.headers.get('Host')}")

        path = "out/client.sh"
        headers = {'Content-Disposition': 'attachment; filename="run.sh"'}

        return web.FileResponse(path, headers=headers)

    @staticmethod
    async def start_server():
        console.info("Starting file server")

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

        # port = 56123

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
        console.info("Terminated and cleaned up webserver")


async def get_client_broadcast() -> tuple[str, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    server_address = ('', broadcast_port)
    sock.bind(server_address)

    try:
        with console.status("[bold green4]", spinner="bouncingBar") as status:
            await asyncio.sleep(1 - (time.time() % 1))
            console.info("Started client listener")
            status.update(status="[bold green4]    Waiting for client message...")

            message, _ = await loop.run_in_executor(None, sock.recvfrom, 4096)
            body = json.loads(message)

            if body.get("can_accept") is True:
                data = body["ip"], body["port"]
                console.info(f"Found ssh client on {data[0]}:{data[1]}")

                return data

    finally:
        sock.close()


async def run_client(address: str, port: int):
    console.info("Running commands for installation")

    async with aiofiles.open("certs/ssh/client_key", "r") as file:
        client_key = await file.read()

    with console.status(
            "[bold green4]    Installing TonieCloud...",
            spinner="bouncingBar"
    ) as status:
        async with asyncssh.connect(
                address,
                port=port,
                username='user',
                client_keys=[asyncssh.import_private_key(client_key)],
                known_hosts=None,
        ) as conn:
            async def run_command(command: str, log: str = None, fail_all: bool = True) -> asyncssh.SSHCompletedProcess:
                if log:
                    console.info(log)

                command_result = await conn.run(command)

                if command_result.stderr and fail_all:
                    console.error(command_result.stderr)
                    console.error("Exiting program...")
                    exit(1)

                return command_result

            await run_command("ping -c 1 duckduckgo.com", log="Checking internet connection")
            res = await run_command("sudo docker -v", log="Checking docker")

            if "command not found" in res.stdout:
                console.info("Docker not found. Installing...")
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
                    console.error("Failed to install docker. Please check manually")
                    console.info("Exiting program...")
                    exit(1)

                console.info("Successfully installed docker")

            console.info("Installing TeddyCloud & Web Interface")
            await run_command("DIRECTORY INTO teddy_cloud")
            await run_command("curl -o docker-compose.yaml -s https://raw.githubusercontent.com/"
                              "toniebox-reverse-engineering/teddycloud/master/docker/docker-compose.yaml")

            await run_command('sed -i "7s/# //" "docker-compose.yaml"')
            await run_command('sed -i "8s/#//" "docker-compose.yaml"')
            await run_command('sed -i "9s/#//" "docker-compose.yaml"')
            await run_command('sed -i "1d" docker-compose.yaml')

            console.info("Starting TeddyCloud")
            await run_command("sudo docker compose up -d --quiet-pull")

            async with aiohttp.ClientSession() as s:
                max_tries = 60

                while max_tries > 0:
                    try:
                        async with s.get(f"http://{address}") as r:
                            text = await r.text()
                            if "TeddyCloud administration interface" in text:
                                console.info(
                                    f"Cloud is running [bold]on http://{address}/web[/bold]\n"
                                    "You can stop it with `sudo docker compose -f teddy_cloud/docker-compose.yaml down`"
                                )
                                break

                    except (aiohttp.InvalidURL, aiohttp.ClientConnectionError):
                        await asyncio.sleep(3)
                        max_tries -= 1

                else:
                    console.error("Failed to start cloud within 120 seconds. Please check manually")
                    console.error("Exiting program...")
                    exit(1)

            console.info("Exchanging certificates")
            await run_command("sudo docker cp teddycloud:/teddycloud/certs/server/ca.der ca.der")
            result = await run_command("cat ca.der")

            folder = "./certs/cloud/"
            os.makedirs(folder, exist_ok=True)
            async with aiofiles.open(f"{folder}ca.der", "wb") as file:
                server_cert = bytes.fromhex(result.stdout)
                await file.write(server_cert)

            await run_command(f"rm ca.der")

            console.info(f"Fetched certificate `{folder}ca.der`")

            folder = "./certs/box/"
            while True:
                missing: list[str] = []
                certs: dict[str, str] = {}

                for x in ["ca.der", "client.der", "private.der"]:
                    path = f"{folder}{x}"

                    if os.path.exists(path):
                        async with aiofiles.open(path, "rb") as f:
                            content = await f.read()
                            certs[x] = content.hex()

                    else:
                        missing.append(x)

                if not missing:
                    break

                status.stop()
                console.print(
                    "\n[bold yellow1]Following client certificates are missing:[/bold yellow1]\n" +
                    "\n∘︎ ".join(missing) + "\n",
                    "Copy missing certificates to `./certs/box/` and press enter.\n"
                    "Type [bold]N[/bold] to finish setup without client certificates",
                    end="",
                )
                choice = await loop.run_in_executor(None, input)

                if choice.lower() == "n":
                    console.info("Skipping client certificates")
                    console.print("Finished installation\n", style="bold steel_blue1")
                    return

                status.start()

            console.info("Loaded all required TonieBox certificates from disk")

            for k, v in certs.items():
                await run_command(f"echo {v} | xxd -r -p > {k}")
                await run_command(f"sudo docker cp {k} teddycloud:/teddycloud/certs/client/{k}")
                await run_command(f"rm {k}")

                console.info(f"Transferred certificate `{folder}{k}`")

            console.print("Finished installation\n", style="bold steel_blue1")


async def keygen(base_folder: str, name: str):
    task = asyncio.create_task(asyncio.sleep(0.5))
    proc = await asyncio.create_subprocess_shell(
        f"ssh-keygen -f {base_folder}{name} -N ''",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    assert stderr.decode() == ""
    await task


async def generate_certs():
    base_folder = "./certs/ssh/"
    for x in ["host_key", "host_key.pub", "client_key", "client_key.pub"]:
        if os.path.exists(f"{base_folder}{x}"):
            os.remove(f"certs/ssh/{x}")

    console.info("Generating SSH certificates")
    await keygen(base_folder, "host_key")
    await keygen(base_folder, "client_key")


async def generate_client():
    ssh_certs = "./certs/ssh/"
    for x in ["client.sh"]:
        if os.path.exists(f"out/{x}"):
            os.remove(f"out/{x}")

    console.info("Generating installer script")
    task = asyncio.create_task(asyncio.sleep(0.5))

    async with aiofiles.open(f"{ssh_certs}host_key", "r") as f:
        host_key = await f.read()
        host_key = host_key.rstrip("\n")

    async with aiofiles.open(f"{ssh_certs}client_key.pub", "r") as f:
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
        console.info("Creating folders")
        Path("certs/ssh").mkdir(parents=True, exist_ok=True)
        Path("./out").mkdir(parents=True, exist_ok=True)

        await generate_certs()
        await generate_client()


async def run_cloud_install():
    # wait for the client to connect
    client_addr = await get_client_broadcast()

    if WebServer.is_running is True:
        await WebServer.stop_server()

    try:
        await run_client(*client_addr)

    except (OSError, asyncssh.Error) as exc:
        console.error('Error connecting to server: ' + str(exc))


async def main():
    print_welcome()

    # ask which mode user wants
    await print_description()
    while True:
        option = (await setup()).lower()

        if option == "1":
            if cc is None:
                console.print(
                    "\n[bold yellow1]This cannot be executed because the required custom cc3200tool "
                    "is not installed![/bold yellow1]\n"
                    "[bold]Do you want to download it? [[green4]y[/green4]/[red3]N[/red3]] [/bold]",
                    end=""
                )
                choice = await loop.run_in_executor(None, input)
                if choice.lower() == "y":
                    with console.status(
                            "[bold green4]    Installing cc3200tool...",
                            spinner="bouncingBar"
                    ):
                        console.info("Downloading Biscgit/cc3200tool")
                        proc = await asyncio.create_subprocess_shell(
                            "git clone --quiet https://github.com/Biscgit/cc3200tool.git",
                        )
                        await proc.wait()

                        console.info("Installed cc3200tool module")

                    console.print("[bold]Please restart the application manually.[/bold]\n")
                    exit(0)

                else:
                    console.info("Installation cancelled\n")
                    continue

            usb_port = await get_usb_port()
            if usb_port is None:
                continue

            await dump_certificates(usb_port)

        elif option == "2":
            console.print(f"\n{circuit}\n")

        elif option == "3":
            console.print("\nStarting installation", style="bold steel_blue1")
            # generate script and launch server
            await generate_scripts()
            await WebServer.start_server()
            await run_cloud_install()

        elif option == "4":
            console.print("\nStarting installation", style="bold steel_blue1")
            # only generate a script
            await generate_scripts()
            await run_cloud_install()

        elif option in ["q", "exit", "quit", "stop"]:
            console.info("Exiting...")
            exit(0)

        else:
            console.error("Invalid option\nExiting program...")
            exit(1)


if __name__ == '__main__':
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        loop.stop()

    finally:
        loop.close()

    console.log("Program finished")
    exit(0)
