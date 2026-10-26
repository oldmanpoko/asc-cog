from typing import Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red


class StreamWatch(commands.Cog):
    """Detects when members start/stop streaming (Activity type 1)."""

    def __init__(self, bot: Red):
        self.bot = bot
        # Red's Config is stored as JSON by default (data.json in the cog's data folder)
        self.config = Config.get_conf(
            self, identifier=7392015584, force_registration=True
        )
        self.config.register_guild(
            enabled=False,
            channel=None,    # announcement channel id
            live_role=None,  # optional role id given while live
        )
        # (guild_id, user_id) of members currently known to be live.
        # Prevents re-announcing when stream title/game changes.
        self._live: set = set()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def get_stream(member: discord.Member) -> Optional[discord.Streaming]:
        """Look through member.activities for an activity with type == 1 (streaming)."""
        for activity in member.activities:
            if activity.type is discord.ActivityType.streaming:  # value 1
                return activity
        return None

    # ------------------------------------------------------------------ listener

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # discord.py's name for the PRESENCE_UPDATE gateway event
        if after.bot or after.guild is None:
            return

        guild = after.guild
        settings = await self.config.guild(guild).all()
        if not settings["enabled"]:
            return

        key = (guild.id, after.id)
        stream = self.get_stream(after)

        if stream and key not in self._live:
            self._live.add(key)
            await self._went_live(after, stream, settings)
        elif not stream and key in self._live:
            self._live.discard(key)
            await self._went_offline(after, settings)

    async def _went_live(self, member, stream, settings):
        guild = member.guild

        role = guild.get_role(settings["live_role"]) if settings["live_role"] else None
        if role and guild.me.guild_permissions.manage_roles:
            try:
                await member.add_roles(role, reason="Started streaming")
            except discord.HTTPException:
                pass

        channel = guild.get_channel(settings["channel"]) if settings["channel"] else None
        if not channel or not channel.permissions_for(guild.me).send_messages:
            return

        embed = discord.Embed(
            title=f"🔴 {member.display_name} is live!",
            description=stream.details or stream.name or "No title",
            url=stream.url,
            colour=discord.Colour.purple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if stream.game:
            embed.add_field(name="Playing", value=stream.game)
        if stream.platform:
            embed.add_field(name="Platform", value=stream.platform)
        await channel.send(embed=embed)

    async def _went_offline(self, member, settings):
        role = member.guild.get_role(settings["live_role"]) if settings["live_role"] else None
        if role and role in member.roles and member.guild.me.guild_permissions.manage_roles:
            try:
                await member.remove_roles(role, reason="Stopped streaming")
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------ commands

    @commands.command()
    @commands.guild_only()
    async def isstreaming(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check whether a member is currently streaming."""
        member = member or ctx.author
        stream = self.get_stream(member)
        if stream:
            await ctx.send(f"🔴 **{member.display_name}** is streaming: {stream.url}")
        else:
            await ctx.send(f"⚫ **{member.display_name}** is not streaming.")

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def streamwatch(self, ctx: commands.Context):
        """Configure StreamWatch."""

    @streamwatch.command(name="toggle")
    async def sw_toggle(self, ctx: commands.Context):
        """Enable or disable stream detection in this server."""
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)
        await ctx.send(f"StreamWatch is now {'enabled' if not current else 'disabled'}.")

    @streamwatch.command(name="channel")
    async def sw_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set the announcement channel (omit to clear)."""
        await self.config.guild(ctx.guild).channel.set(channel.id if channel else None)
        await ctx.send(f"Announcement channel: {channel.mention if channel else 'cleared'}.")

    @streamwatch.command(name="role")
    async def sw_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set a role given while someone is live (omit to clear)."""
        await self.config.guild(ctx.guild).live_role.set(role.id if role else None)
        await ctx.send(f"Live role: {role.name if role else 'cleared'}.")

    @streamwatch.command(name="settings")
    async def sw_settings(self, ctx: commands.Context):
        """Show current settings."""
        s = await self.config.guild(ctx.guild).all()
        ch = ctx.guild.get_channel(s["channel"]) if s["channel"] else None
        role = ctx.guild.get_role(s["live_role"]) if s["live_role"] else None
        await ctx.send(
            f"**Enabled:** {s['enabled']}\n"
            f"**Channel:** {ch.mention if ch else 'not set'}\n"
            f"**Live role:** {role.name if role else 'not set'}"
        )
