import datetime

import discord
from discord import app_commands
from discord.ext import commands

from .. import db
from ..game import repository as repo
from ..game.share import share_text


class StatsCog(commands.Cog):
    """Leaderboards, personal stats, and shareable results."""

    def __init__(self, bot, db_path):
        self.bot = bot
        self.db_path = db_path

    @app_commands.command(name="leaderboard", description="See the Countrydle rankings")
    @app_commands.describe(period="all-time (default) or this-week")
    @app_commands.choices(
        period=[
            app_commands.Choice(name="all-time", value="all"),
            app_commands.Choice(name="this-week", value="week"),
        ]
    )
    async def leaderboard(self, interaction, period: app_commands.Choice[str] = None):
        scope = period.value if period else "all"
        since = None
        title = "🏆 Countrydle — All-time"
        if scope == "week":
            since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            title = "🏆 Countrydle — Last 7 days"
        conn = db.connect(self.db_path)
        try:
            rows = repo.leaderboard(conn, since=since)
        finally:
            conn.close()
        embed = discord.Embed(title=title, colour=0xF1C40F)
        if not rows:
            embed.description = "No scores yet — play with `/guess`!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, row in enumerate(rows):
                rank = medals[i] if i < 3 else f"`{i + 1:>2}`"
                lines.append(f"{rank} **{row['display_name']}** — {row['total']} pts ({row['played']} games, avg {row['average']})")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats", description="Your Countrydle stats (or another player's)")
    @app_commands.describe(user="Whose stats to show (defaults to you)")
    async def stats(self, interaction, user: discord.User = None):
        target = user or interaction.user
        conn = db.connect(self.db_path)
        try:
            stats = repo.user_stats(conn, target.id)
        finally:
            conn.close()
        embed = discord.Embed(title=f"📊 {target.display_name}", colour=0x3498DB)
        if stats["played"] == 0:
            embed.description = "No games played yet."
        else:
            embed.add_field(name="Games", value=str(stats["played"]))
            embed.add_field(name="Total", value=f"{stats['total']} pts")
            embed.add_field(name="Average", value=f"{stats['average']} pts")
            embed.add_field(name="Best", value=f"{stats['best']} pts")
            embed.add_field(name="🔥 Streak", value=f"{stats['streak']} days")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="share", description="Get a spoiler-free share line for today's guess")
    async def share(self, interaction):
        conn = db.connect(self.db_path)
        try:
            puzzle = repo.get_live_puzzle(conn)
            if puzzle is None:
                await interaction.response.send_message("No puzzle is live right now.", ephemeral=True)
                return
            guess = repo.get_guess(conn, puzzle["id"], interaction.user.id)
            if guess is None:
                await interaction.response.send_message("Guess first with `/guess`.", ephemeral=True)
                return
            text = share_text(puzzle["puzzle_date"], guess["score"], guess["distance_km"], guess["distance_km"] == 0)
        finally:
            conn.close()
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot):
    """discord.py extension entry point."""
    await bot.add_cog(StatsCog(bot, bot.db_path))
