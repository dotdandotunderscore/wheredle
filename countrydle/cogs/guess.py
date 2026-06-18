import discord
from discord import app_commands
from discord.ext import commands

from .. import db
from ..game import countries
from ..game import repository as repo


def _board_embed(title, rows):
    """Build the shared 'who guessed what' board embed from repository rows."""
    embed = discord.Embed(title=title, colour=0x2ECC71)
    if not rows:
        embed.description = "No guesses yet — be the first!"
        return embed
    lines = []
    for i, row in enumerate(rows, 1):
        flag = countries.flag_emoji(row["guess_iso"])
        country = countries.get(row["guess_iso"])
        name = country.name if country else row["guess_iso"]
        lines.append(f"`{i:>2}` {flag} **{name}** — {row['score']} pts ({round(row['distance_km'])} km) · {row['display_name']}")
    embed.description = "\n".join(lines)
    return embed


def _resolve_iso(value):
    """Map an autocomplete value (ISO2) or free-typed text to an ISO2 code, or None."""
    return value if countries.get(value) else countries.resolve(value)


class ConfirmGuess(discord.ui.View):
    """One-shot confirmation: locking is irreversible, so make the user confirm."""

    def __init__(self, cog, puzzle_id, iso2, user_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.puzzle_id = puzzle_id
        self.iso2 = iso2
        self.user_id = user_id

    @discord.ui.button(label="Lock it in", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        conn = db.connect(self.cog.db_path)
        try:
            puzzle = repo.get_puzzle(conn, self.puzzle_id)
            try:
                result = repo.record_guess(conn, puzzle, self.user_id, interaction.user.display_name, self.iso2)
            except repo.AlreadyGuessed:
                await interaction.response.edit_message(content="You already guessed today.", view=None)
                return
            country = countries.get(self.iso2)
            answer = countries.get(puzzle["answer_iso"])
            verdict = "Bang on! 100 pts 🎯" if result["exact"] else f"{result['score']} pts · {round(result['distance_km'])} km away"
            answer_line = f"\n🌍 Answer: **{countries.flag_emoji(puzzle['answer_iso'])} {answer.name}**"
            header = f"Locked **{countries.flag_emoji(self.iso2)} {country.name}** — {verdict}{answer_line}"
            board_rows = repo.board(conn, self.puzzle_id)
            embed = _board_embed("Today's guesses so far", board_rows)
            await interaction.response.edit_message(content=header, embed=embed, view=None)
            channel = self.cog.bot.get_channel(self.cog.bot.config.channel_id)
            if channel:
                existing_id = self.cog._board_messages.get(self.puzzle_id)
                if existing_id:
                    try:
                        msg = await channel.fetch_message(existing_id)
                        await msg.edit(embed=embed)
                    except discord.NotFound:
                        msg = await channel.send(embed=embed)
                        self.cog._board_messages[self.puzzle_id] = msg.id
                else:
                    msg = await channel.send(embed=embed)
                    self.cog._board_messages[self.puzzle_id] = msg.id
        finally:
            conn.close()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="Cancelled — guess again when ready.", view=None)


class GuessCog(commands.Cog):
    """Slash commands for guessing and viewing the gated results board."""

    def __init__(self, bot, db_path):
        self.bot = bot
        self.db_path = db_path
        self._board_messages: dict[int, int] = {}  # puzzle_id → channel message id

    @app_commands.command(name="guess", description="Guess which country today's photo was taken in")
    @app_commands.describe(country="Start typing a country name")
    async def guess(self, interaction, country: str):
        conn = db.connect(self.db_path)
        try:
            puzzle = repo.get_live_puzzle(conn)
            if puzzle is None:
                await interaction.response.send_message("No puzzle is live right now.", ephemeral=True)
                return
            if repo.has_guessed(conn, puzzle["id"], interaction.user.id):
                embed = _board_embed("Today's guesses so far", repo.board(conn, puzzle["id"]))
                await interaction.response.send_message("You've already guessed — here's the board:", embed=embed, ephemeral=True)
                return
            iso2 = _resolve_iso(country)
            if iso2 is None:
                await interaction.response.send_message(f"Didn't recognise **{country}**. Try the autocomplete.", ephemeral=True)
                return
            resolved = countries.get(iso2)
            view = ConfirmGuess(self, puzzle["id"], iso2, interaction.user.id)
            await interaction.response.send_message(
                f"Lock in **{countries.flag_emoji(iso2)} {resolved.name}**? You only get one guess.",
                view=view,
                ephemeral=True,
            )
        finally:
            conn.close()

    @guess.autocomplete("country")
    async def country_autocomplete(self, interaction, current):
        needle = current.lower()
        matches = [c for c in countries.all_countries() if needle in c.name.lower()]
        return [
            app_commands.Choice(name=f"{countries.flag_emoji(c.iso2)} {c.name}", value=c.iso2)
            for c in matches[:25]
        ]

    @app_commands.command(name="results", description="See everyone's guesses (after you've guessed)")
    async def results(self, interaction):
        conn = db.connect(self.db_path)
        try:
            puzzle = repo.get_live_puzzle(conn)
            if puzzle is None:
                await interaction.response.send_message("No puzzle is live right now.", ephemeral=True)
                return
            if not repo.has_guessed(conn, puzzle["id"], interaction.user.id):
                await interaction.response.send_message("Guess first with `/guess`, then you can see the board.", ephemeral=True)
                return
            embed = _board_embed("Today's guesses so far", repo.board(conn, puzzle["id"]))
            await interaction.response.send_message(embed=embed, ephemeral=True)
        finally:
            conn.close()


async def setup(bot):
    """discord.py extension entry point."""
    await bot.add_cog(GuessCog(bot, bot.db_path))
