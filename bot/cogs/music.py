"""
    via discord.py - rapptz's code.
"""
import discord
from discord.ext import commands
import player

from syncer.voice_syncer import SyncerState

if not discord.opus.is_loaded():
    discord.opus.load_opus('opus')


def setup(bot):
    bot.add_cog(Music(bot))


class Music:
    """Voice related commands.
    Works in multiple servers at once.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return None

        state = player.get_player_state(ctx.message.server, self.bot, create=True)
        if state.syncer.fsm_state == SyncerState.DISCONNECTED:
            state.syncer.connect(summoned_channel)

        return state

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song: str):
        state = player.get_player_state(ctx.message.server)
        if not state:
            state = await ctx.invoke(self.summon)
            if not state:
                return

        state.syncer.play(song)

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        state = player.get_player_state(ctx.message.server)
        if state:
            state.syncer.stop()

    @commands.command(pass_context=True, no_pm=True)
    async def state(self, ctx):
        state = player.get_player_state(ctx.message.server)
        if state:
            await self.bot.say('FSM State %r %r' % (state.syncer.state, state.syncer.fsm_state))
        else:
            await self.bot.say('no fsm state')

        #
    # @commands.command(pass_context=True, no_pm=True)
    # async def pause(self, ctx):
    #     state = self.get_voice_state(ctx.message.server)
    #
    #     if state.voice is None:
    #         await self.bot.say('We are not connected')
    #
    #     did_stop = state.voice.pause()
    #     if did_stop:
    #         await self.bot.say('Stopped the music')
    #     else:
    #         await self.bot.say('Nothing to stop sorry')
    #
    # @commands.command(pass_context=True, no_pm=True)
    # async def resume(self, ctx):
    #     state = self.get_voice_state(ctx.message.server)
    #
    #     if state.voice is None:
    #         await self.bot.say('We are not connected')
    #
    #     did_stop = state.voice.resume()
    #     if did_stop:
    #         await self.bot.say('Stopped the music')
    #     else:
    #         await self.bot.say('Nothing to stop sorry')
