import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import db
from ..game import countries
from ..game import repository as repo
from ..sourcing.candidates import gather, queue_candidate
from ..sourcing.images import fetch_clean_image

log = logging.getLogger("wheredle.daily")

REPORT_EMOJI = "🚩"
REPORT_THRESHOLD = 3  # distinct flag reactions that auto-void a puzzle

APPROVE_EMOJI = "✅"
REJECT_EMOJI = "❌"
REVIEW_BATCH = 5             # review cards posted per topup tick (keeps under rate limits)
QUEUE_TARGET = 20           # stop fetching once this many puzzles are approved or awaiting review
LOW_QUEUE_THRESHOLD = 5     # @here the review channel when approved puzzles drop below this


class ConfirmWipe(discord.ui.View):
    """Confirmation gate for /wipequeue — prevents accidental queue destruction."""

    def __init__(self, cog, count):
        super().__init__(timeout=30)
        self.cog = cog
        self.count = count

    @discord.ui.button(label="Yes, wipe queue", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        conn = db.connect(self.cog.db_path)
        try:
            with conn:
                conn.execute("DELETE FROM puzzles WHERE status='queued'")
        finally:
            conn.close()
        await interaction.response.edit_message(content=f"Wiped {self.count} queued puzzle(s).", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class DailyCog(commands.Cog):
    """Posts a new puzzle each day and reveals the previous day's answer."""

    def __init__(self, bot, db_path, channel_id, review_channel_id, timezone, post_hour, admin_ids):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id
        self.review_channel_id = review_channel_id
        self.tz = ZoneInfo(timezone)
        self.admin_ids = admin_ids
        self._low_queue_alerted = False  # de-dupes the low-queue @everyone ping
        self.daily_post.change_interval(time=datetime.time(hour=post_hour, tzinfo=self.tz))
        self.daily_post.start()
        self.fetch_queue.start()
        self.post_reviews.start()

    def cog_unload(self):
        self.daily_post.cancel()
        self.fetch_queue.cancel()
        self.post_reviews.cancel()

    @tasks.loop(time=datetime.time(hour=9))  # interval is reset in __init__ from config
    async def daily_post(self):
        await self._post_today()

    @daily_post.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def fetch_queue(self):
        """Top up from Wikimedia Commons if the review pipeline (approved + pending) is low."""
        conn = db.connect(self.db_path)
        try:
            ready, pending = repo.queue_depth(conn)
            if ready + pending >= QUEUE_TARGET:
                log.info("fetch_queue: %d ready + %d pending, skipping", ready, pending)
                return
            added = 0
            with conn:
                for candidate, iso2 in gather():
                    if queue_candidate(conn, candidate, iso2):
                        added += 1
            log.info("fetch_queue: added %d pending puzzles (was %d ready, %d pending)", added, ready, pending)
        except Exception:
            log.exception("fetch_queue failed")
        finally:
            conn.close()

    @fetch_queue.before_loop
    async def _before_fetch(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def post_reviews(self):
        """Post un-reviewed pending puzzles to the review channel for admin vetting."""
        if not self.review_channel_id:
            return
        channel = self.bot.get_channel(self.review_channel_id)
        if channel is None:
            log.warning("review channel %s not found", self.review_channel_id)
            return
        conn = db.connect(self.db_path)
        try:
            for puzzle in repo.get_unposted_pending(conn, limit=REVIEW_BATCH):
                await self._post_review(channel, puzzle, conn)
            await self._alert_if_low(conn, channel)
        except Exception:
            log.exception("post_reviews failed")
        finally:
            conn.close()

    @post_reviews.before_loop
    async def _before_reviews(self):
        await self.bot.wait_until_ready()

    async def _alert_if_low(self, conn, channel):
        """Ping the review channel when the approved queue is running low (once per drain)."""
        ready, _ = repo.queue_depth(conn)
        if ready >= LOW_QUEUE_THRESHOLD:
            self._low_queue_alerted = False
            return
        if self._low_queue_alerted:
            return
        await channel.send(
            f"@everyone only **{ready}** approved puzzle(s) left in the queue — "
            "please review the cards above so the daily game doesn't run dry.",
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        self._low_queue_alerted = True

    async def _post_review(self, channel, puzzle, conn):
        """Post a location-blind review card and seed it with the vote reactions."""
        image = fetch_clean_image(puzzle["image_path"])
        embed = discord.Embed(
            title="🕵️ Review candidate",
            description=(
                f"Is this a good Wheredle photo? React {APPROVE_EMOJI} to approve or "
                f"{REJECT_EMOJI} to reject.\nThe location is hidden on purpose — judge the image alone."
            ),
            colour=0x9B59B6,
        )
        embed.set_image(url="attachment://review.jpg")
        message = await channel.send(embed=embed, file=discord.File(image, filename="review.jpg"))
        await message.add_reaction(APPROVE_EMOJI)
        await message.add_reaction(REJECT_EMOJI)
        repo.set_review_message_id(conn, puzzle["id"], message.id)

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
                await channel.send("⚠️ No approved puzzles queued — approve some in the review channel (or run `/fetchcandidates`).")
                return
            await self._send_puzzle(channel, new, conn)
        finally:
            conn.close()

    async def _send_puzzle(self, channel, puzzle, conn):
        """Download + clean the image, post the puzzle, and store its message id."""
        image = fetch_clean_image(puzzle["image_path"])
        embed = discord.Embed(
            title="🌍 Today's Wheredle",
            description="Where on Earth was this taken? Use `/guess` — one guess only.",
            colour=0x3498DB,
        )
        embed.set_footer(text=f"React {REPORT_EMOJI} if the puzzle looks broken")
        embed.set_image(url="attachment://puzzle.jpg")
        message = await channel.send(embed=embed, file=discord.File(image, filename="puzzle.jpg"))
        repo.set_message_id(conn, puzzle["id"], message.id)

    def _reveal_embed(self, conn, puzzle, title_prefix="📍 Yesterday's answer"):
        """Build the reveal embed: answer, leaderboard, and required photo attribution."""
        country = countries.get(puzzle["answer_iso"])
        name = country.name if country else puzzle["answer_iso"]
        embed = discord.Embed(
            title=f"{title_prefix}: {countries.flag_emoji(puzzle['answer_iso'])} {name}",
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
        """Reveal the live puzzle's answer, void it, and post the next queued one."""
        conn = db.connect(self.db_path)
        try:
            old = repo.get_live_puzzle(conn)
            new = repo.void_live(conn, self._today())
            if old is not None:
                await channel.send(f"🚫 {reason}", embed=self._reveal_embed(conn, old, title_prefix="📍 Answer"))
            else:
                await channel.send(f"🚫 {reason}")
            if new is None:
                await channel.send("⚠️ No approved puzzles queued — approve some in the review channel (or run `/fetchcandidates`).")
                return
            await self._send_puzzle(channel, new, conn)
        finally:
            conn.close()

    @app_commands.command(name="wipequeue", description="(admin) Delete all queued puzzles")
    async def wipequeue(self, interaction):
        if interaction.user.id not in self.admin_ids:
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        conn = db.connect(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM puzzles WHERE status='queued'").fetchone()[0]
        finally:
            conn.close()
        if count == 0:
            await interaction.response.send_message("No queued puzzles to wipe.", ephemeral=True)
            return
        view = ConfirmWipe(self, count)
        await interaction.response.send_message(
            f"This will permanently delete **{count} queued puzzle(s)**. Are you sure?",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="fetchcandidates", description="(admin) Fetch new candidates from Wikimedia Commons")
    @app_commands.describe(
        countries_per_run="Number of countries to sample (default 50)",
        per_country="Max candidates per country (default 5)",
    )
    async def fetchcandidates(self, interaction, countries_per_run: int = 50, per_country: int = 5):
        if interaction.user.id not in self.admin_ids:
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        loop = asyncio.get_running_loop()
        try:
            candidates = await loop.run_in_executor(
                None, lambda: list(gather(per_country=per_country, countries_per_run=countries_per_run))
            )
            conn = db.connect(self.db_path)
            try:
                added = 0
                with conn:
                    for candidate, iso2 in candidates:
                        if queue_candidate(conn, candidate, iso2):
                            added += 1
                ready, pending = repo.queue_depth(conn)
            finally:
                conn.close()
            await interaction.followup.send(
                f"Done — added **{added}** candidate(s) for review. "
                f"**{pending}** awaiting review, **{ready}** approved.",
                ephemeral=True,
            )
        except Exception:
            log.exception("fetchcandidates command failed")
            await interaction.followup.send("Fetch failed — check the logs.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Route review-channel votes and player report reactions."""
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return  # the bot seeds ✅/❌ itself — don't treat those as votes
        if self.review_channel_id and payload.channel_id == self.review_channel_id:
            await self._handle_review_vote(payload)
            return
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

    async def _handle_review_vote(self, payload):
        """Approve or reject a pending puzzle when an admin votes on its review card."""
        emoji = str(payload.emoji)
        if emoji not in (APPROVE_EMOJI, REJECT_EMOJI):
            return
        if payload.user_id not in self.admin_ids:
            return
        conn = db.connect(self.db_path)
        try:
            puzzle = repo.get_pending_by_review_message(conn, payload.message_id)
            if puzzle is None:
                return  # already resolved, or not a review card
            if emoji == APPROVE_EMOJI:
                repo.approve_puzzle(conn, puzzle["id"])
                verdict = f"{APPROVE_EMOJI} Approved — added to the live queue."
            else:
                repo.reject_puzzle(conn, puzzle["id"])
                verdict = f"{REJECT_EMOJI} Rejected."
        finally:
            conn.close()
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        embed = message.embeds[0] if message.embeds else discord.Embed()
        embed.description = verdict
        await message.edit(embed=embed)
        try:
            await message.clear_reactions()  # tidy-up only; needs Manage Messages
        except discord.Forbidden:
            pass


async def setup(bot):
    """discord.py extension entry point."""
    cfg = bot.config
    await bot.add_cog(
        DailyCog(
            bot,
            cfg.database_path,
            cfg.channel_id,
            cfg.review_channel_id,
            cfg.timezone,
            cfg.post_hour,
            cfg.admin_ids,
        )
    )
