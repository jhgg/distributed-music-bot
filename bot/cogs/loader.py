import discord
from discord.ext import commands

extensions = [
    'music',
    'admin'
]


def make_extension_import(extension):
    return 'bot.cogs.%s' % extension


def setup(bot):
    bot.add_cog(Reloader(bot))
    for extension in extensions:
        bot.load_extension(make_extension_import(extension))


class Reloader:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(no_pm=True)
    async def reload(self, *, extension: str):
        if extension not in extensions:
            raise discord.InvalidArgument('%s is not a valid extension to reload, the valid ones are: %s' % (
                extension, ', '.join(extensions)
            ))

        package = make_extension_import(extension)
        bot = self.bot
        bot.unload_extension(package)
        bot.load_extension(package)
        await bot.say('Reloaded %s extension' % extension)
