"""
    via discord.py - rapptz's code.
"""
import discord
from discord.ext import commands
import player
from lib.time_format import format_seconds_to_hhmmss
from player.ytdl import extract_info

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

        state.channel = ctx.message.channel
        info = await extract_info(self.bot.loop, song, ytdl_options={
            'default_search': 'auto',
            'quiet': True,
        })
        await self.bot.say('Playing %s %s' % (info.title, info.duration))
        state.syncer.play(info.download_url)

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        state = player.get_player_state(ctx.message.server)
        if state:
            state.syncer.stop()\

    @commands.command(pass_context=True, no_pm=True)
    async def progress(self, ctx):
        state = player.get_player_state(ctx.message.server)
        if state:
            await self.bot.say('estimated progress is  %s' % format_seconds_to_hhmmss(state.syncer.estimated_progress))

    @commands.command(pass_context=True, no_pm=True)
    async def state(self, ctx):
        state = player.get_player_state(ctx.message.server)
        if state:
            await self.bot.say('FSM State %r %r' % (state.syncer.state, state.syncer.fsm_state))
        else:
            await self.bot.say('no fsm state')

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value: int):
        """Sets the volume of the currently playing song."""

        state = player.get_player_state(ctx.message.server)
        if state:
            new_volume = value / 100.0
            state.syncer.volume(new_volume)
            await self.bot.say('Set the volume to {:.0%}'.format(new_volume))
