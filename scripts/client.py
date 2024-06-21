import asyncio
import asyncssh
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

host_key = open("host_key", "r").read()
client_pub = open("client_key.pub", "r").read()


async def handle_commands(process: asyncssh.SSHServerProcess) -> None:
    try:
        proc = await asyncio.create_subprocess_shell(
            process.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            logger.info(f"`{process.command}` stdout: {stdout.decode().rstrip('\n')}")
            process.stdout.write(stdout.decode())
        if stderr:
            logger.warning(f"`{process.command}` stderr: {stderr.decode().rstrip('\n')}")
            process.stdout.write(stderr.decode())

    except Exception as e:
        logger.error(f"Failed to execute command: {type(e)} {e}")
        process.stderr.write(f'Error in execution: {e}\n')

    finally:
        process.exit(0)


async def run_ssh_server():
    await asyncssh.listen(
        '',
        8030,
        server_host_keys=[asyncssh.import_private_key(host_key)],
        authorized_client_keys=asyncssh.import_authorized_keys(client_pub),
        process_factory=handle_commands
    )


async def main():
    # launch ssh server awaiting key_inputs
    try:
        await asyncio.create_task(run_ssh_server())

    except (OSError, asyncssh.Error) as e:
        logger.error(f"Error in running ssh server: {e}")
        exit(1)


if __name__ == '__main__':
    logger.info("Launching Autoinstaller!")
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(main())
        loop.run_forever()

    except KeyboardInterrupt:
        logging.info("Terminating server...")

    finally:
        loop.close()
