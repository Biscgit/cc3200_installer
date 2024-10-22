import asyncio
import json
import logging
import os
import pathlib
import socket
import socketserver
import typing

import asyncssh

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

host_key = [[]]
client_pub = [[]]

broadcast_port = 37021


class BroadCaster:
    def __init__(self):
        self._has_connected = False

    async def cast_script_up(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        local_ip = socket.gethostbyname(socket.gethostname())
        ssh_port = SSHServer.ssh_port

        broadcast_address = ('<broadcast>', broadcast_port)
        broadcast_message = json.dumps({
            "can_accept": True,
            "ip": local_ip,
            "port": ssh_port
        })

        try:
            running_time = 0
            while not self._has_connected:
                if running_time % 20 == 0:
                    logger.info(f"Broadcasting SSH address: {local_ip}:{ssh_port} on port {broadcast_port}")
                    sock.sendto(broadcast_message.encode(), broadcast_address)

                await asyncio.sleep(0.1)
                running_time += 1

        finally:
            logger.info("Closing broadcast socket")
            sock.close()

            SSHServer.task = None

    def set_connected(self):
        self._has_connected = True


class SSHServer(asyncssh.SSHServer):
    broadcast = BroadCaster()
    task: typing.Optional[asyncio.Task] = None
    ssh_port: typing.Optional[int] = None
    current_folder = pathlib.Path.cwd()

    def auth_completed(self) -> None:
        # only activate on successful authentication -> for example, avoid close on nmap scanning
        SSHServer.broadcast.set_connected()

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        logging.info(f"Connection from {conn.get_extra_info('peername')[0]}")

    def connection_lost(self, exc: typing.Optional[Exception]) -> None:
        # on disconnect the script should have finished, stopping server
        loop.stop()
        if exc:
            logger.error(f"Closing connection with exception: {exc}")

    @staticmethod
    def change_location(command: str) -> None:
        split = command.strip("DIRECTORY").strip(" ").lower().split(" ")

        if split[0] == "up":
            SSHServer.current_folder = SSHServer.current_folder.parent

        elif split[0] == "into":
            new_folder = split[1]
            SSHServer.current_folder /= new_folder

            if not os.path.exists(SSHServer.current_folder):
                os.makedirs(SSHServer.current_folder, exist_ok=True)

        else:
            raise Exception("Invalid option passed")

        os.chdir(SSHServer.current_folder)

    @staticmethod
    async def handle_commands(process: asyncssh.SSHServerProcess) -> None:
        # synchronize first connection with socket
        if SSHServer.task:
            await SSHServer.task
            SSHServer.task = None

        try:
            if process.command.startswith("DIRECTORY"):
                try:
                    SSHServer.change_location(process.command)
                    process.stdout.write(f"Current location: {SSHServer.current_folder}")
                    process.exit(0)

                except Exception as e:
                    process.stderr.write(f"Failed to change directories: {e}")
                    process.exit(1)

                finally:
                    return

            proc = await asyncio.create_subprocess_shell(
                process.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                try:
                    out = stdout.decode().rstrip('\n')
                    logger.info(f"Command: `{process.command}` with stdout: {out}")
                except UnicodeDecodeError:
                    out = stdout.hex()

                process.stdout.write(out)

            if stderr:
                err = stderr.decode().rstrip('\n')
                logger.warning(f"`{process.command}` stderr: {err}")
                process.stdout.write(err)

        except Exception as e:
            logger.error(f"Failed to execute command: {type(e)} {e}")
            process.stderr.write(f'Error in execution: {e}\n')

        finally:
            process.exit(0)

    @classmethod
    async def start_ssh_server(cls):
        with socketserver.TCPServer(("localhost", 0), None) as s:  # noqa
            port = s.server_address[1]
            SSHServer.ssh_port = port

        await asyncssh.create_server(
            cls,
            '',
            port,
            server_host_keys=[asyncssh.import_private_key(str(host_key))],
            authorized_client_keys=asyncssh.import_authorized_keys(str(client_pub)),
            process_factory=SSHServer.handle_commands
        )
        SSHServer.task = asyncio.create_task(SSHServer.broadcast.cast_script_up())


async def main():
    try:
        # launch ssh server awaiting key_inputs
        await SSHServer.start_ssh_server()

    except (OSError, asyncssh.Error) as e:
        logger.error(f"Error in starting  ssh server: {e}")
        exit(1)


if __name__ == '__main__':
    logger.info("Launching Autoinstaller")
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(main())
        loop.run_forever()

    except KeyboardInterrupt:
        # cleanup broadcast task
        if SSHServer.task and not SSHServer.task.cancelled():
            logger.info("Terminating broadcast task...")
            SSHServer.broadcast.set_connected()
            loop.run_until_complete(SSHServer.task)

    finally:
        logger.info("Terminating server...")
        loop.stop()

    logger.info("Programm gracefully finished")
    exit(0)
