import datetime
import logging
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import db
from ..game import countries
from ..game import repository as repo
from ..sourcing.images import fetch_clean_image

log = logging.getLogger("countrydle.daily")

REPORT_EMOJI = "🚩"
REPORT_THRESHOLD = 3  # distinct flag reactions that auto-void a puzzle


class DailyCog(commands.Cog):
    """Posts a new puzzle each day and reveals the previous day's answer."""

    def __init__(self, bot, db_path, channel_id, timezone, post_hour, admin_ids):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id
        self.tz = ZoneInfo(timezone)
        self.admin_ids = admin_ids
        self.daily_post.change_interval(time=datetime.time(hour=post_hour, tzinfo=self.tz))
        self.daily_post.start()

    def cog_unload(self):
        self.daily_post.cancel()

    @tasks.loop(time=datetime.time(hour=9))  # interval is reset in __init__ from config
    async def daily_post(self):
        await self._post_today()

    @daily_post.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _post_today(self):
        """Close yesterday's puzzle (reveal it) and post today's."""
        conn = db.connect(self.db_path)
        try:
            closed, new = repo.rotate_daily(conn, self._today())
            channel = self.bot.get_channel(self.channel_id)
            if channel is None:
                log.warning("channel %s not found", self.channel_id)
                return
            if closed is not None:
                await channel.send(embed=self._reveal_embed(conn, closed))
            if new is None:
                await channel.send("⚠️ No puzzles queued — run `scripts/fetch_candidates.py`.")
                return
            await self._send_puzzle(channel, new, conn)
        finally:
            conn.close()

    async def _send_puzzle(self, channel, puzzle, conn):
        """Download + clean the image, post the puzzle, and store its message id."""
        image = fetch_clean_image(puzzle["image_path"])
        embed = discord.Embed(
            title="🌍 Today's Countrydle",
            description="Where on Earth was this taken? Use `/guess` — one guess only.",
            colour=0x3498DB,
        )
        embed.set_footer(text=f"React {REPORT_EMOJI} if the puzzle looks broken")
        embed.set_image(url="attachment://puzzle.jpg")
        message = await channel.send(embed=embed, file=discord.File(image, filename="puzzle.jpg"))
        repo.set_message_id(conn, puzzle["id"], message.id)

    def _reveal_embed(self, conn, puzzle):
        """Build the reveal embed: answer, leaderboard, and required photo attribution."""
        country = countries.get(puzzle["answer_iso"])
        name = country.name if country else puzzle["answer_iso"]
        embed = discord.Embed(
            title=f"📍 Yesterday's answer: {countries.flag_emoji(puzzle['answer_iso'])} {name}",
            colour=0xF1C40F,
        )
        rows = repo.board(conn, puzzle["id"])
        if rows:
            lines = [f"`{i:>2}` {r['display_name']} — {r['score']} pts" for i, r in enumerate(rows[:15], 1)]
            embed.add_field(name="🏆 Leaderboard", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="🏆 Leaderboard", value="Nobody guessed 😢", inline=False)
        credit = " · ".join(part for part in (puzzle["author"], puzzle["license"]) if part)
        if credit or puzzle["attribution_url"]:
            value = "\n".join(part for part in (credit, puzzle["attribution_url"]) if part)
            embed.add_field(name="📷 Photo (Wikimedia Commons)", value=value, inline=False)
        return embed

    def _today(self):
        return datetime.datetime.now(self.tz).date().isoformat()

    @app_commands.command(name="postnow", description="(admin) Post today's puzzle immediately")
    async def postnow(self, interaction):
        if interaction.user.id not in self.admin_ids:
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        await interaction.response.send_message("Posting…", ephemeral=True)
        await self._post_today()

    @app_commands.command(name="skip", description="(admin) Void the current puzzle and post the next")
    async def skip(self, interaction):
        if interaction.user.id not in self.admin_ids:
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        await interaction.response.send_message("Skipping…", ephemeral=True)
        await self._void_and_repost(interaction.channel, "Puzzle skipped by an admin.")

    async def _void_and_repost(self, channel, reason):
        """Void the live puzzle (no reveal) and post the next queued one."""
        conn = db.connect(self.db_path)
        try:
            new = repo.void_live(conn, self._today())
            await channel.send(f"🚫 {reason}")
            if new is None:
                await channel.send("⚠️ No puzzles queued — run `scripts/fetch_candidates.py`.")
                return
            await self._send_puzzle(channel, new, conn)
        finally:
            conn.close()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Auto-void the live puzzle once enough players flag it as broken."""
        if str(payload.emoji) != REPORT_EMOJI:
            return
        conn = db.connect(self.db_path)
        try:
            live = repo.get_live_puzzle(conn)
            if live is None or live["message_id"] != payload.message_id:
                return
        finally:
            conn.close()
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        flags = next((r for r in message.reactions if str(r.emoji) == REPORT_EMOJI), None)
        if flags is not None and flags.count >= REPORT_THRESHOLD:
            await self._void_and_repost(channel, f"Puzzle voided after {flags.count} reports.")


async def setup(bot):
    """discord.py extension entry point."""
    cfg = bot.config
    await bot.add_cog(
        DailyCog(bot, cfg.database_path, cfg.channel_id, cfg.timezone, cfg.post_hour, cfg.admin_ids)
    )
