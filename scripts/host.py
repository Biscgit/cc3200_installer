import asyncio
import sys

import asyncssh


async def run_client():
    async with asyncssh.connect(
            'localhost',
            port=8027,
            username='user',
            client_keys=['client_key'],
            known_hosts=None,
    ) as conn:
        print("sending")
        result = await conn.run('echo "Hello, world!"')
        print(result.stdout, end='')
        print(result.stderr, file=sys.stderr)
        result = await conn.run('echo "Hello, world2!')
        print(result.stdout, end='')
        print(result.stderr, file=sys.stderr)


loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(run_client())
except (OSError, asyncssh.Error) as exc:
    print('Error connecting to server: ' + str(exc))
finally:
    loop.close()
