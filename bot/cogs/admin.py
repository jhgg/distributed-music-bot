"""
    via discord.py - rapptz's code.


"""
from discord.ext import commands


def setup(bot):
    bot.add_cog(Admin(bot))


class Admin:
    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True)
    async def admin(self, ctx):
        if ctx.invoked_subcommand is None:
            await self.bot.say('Invalid admin command passed...')

    @admin.command()
    async def cluster_info(self):
        parts = []
        for client in self.bot.rpc_server.clients_by_connection_id.values():
            parts.append('- `%s`: %s/%s clients, acceptable regions: %s, %s ms' % (
                client.client_connection_id,  client.client_count, client.remote_info['max_clients'],
                client.remote_info['acceptable_regions'], ', '.join(str(int(i * 1000)) for i in client._pings)
            ))

        if not parts:
            parts.append('No connected clients')

        await self.bot.say('\n'.join(parts))
