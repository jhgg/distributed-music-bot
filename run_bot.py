import asyncio

from discord.ext import commands

import bot.client
import secrets
import voice.server

loop = asyncio.get_event_loop()
discord = bot.client.Bot(loop=loop, command_prefix=commands.when_mentioned_or('$'),
                         description='A playlist example for discord.py')
rpc_server = voice.server.Server(loop=loop, discord=discord)


@discord.event
async def on_ready():
    print('Logged in as')
    print(discord.user.name)
    print(discord.user.id)
    print('------')


rpc_server.start()
discord.rpc_server = rpc_server
discord.load_extension('bot.cogs.loader')

discord.run(secrets.discord_token)
