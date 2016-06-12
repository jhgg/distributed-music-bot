import asyncio
from discord.ext import commands
import bot.client
from bot.music import Music
import voice.server
import secrets

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
discord.add_cog(Music(discord))

discord.run(secrets.discord_token)
