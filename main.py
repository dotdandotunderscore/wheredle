import logging

import discord
from discord.ext import commands

from countrydle.config import Config
from countrydle.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("countrydle")


def create_bot(config):
    """Construct the Discord bot, load cogs, and sync slash commands to the guild."""
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.config = config
    bot.db_path = config.database_path

    async def setup_hook():
        await bot.load_extension("countrydle.cogs.guess")
        await bot.load_extension("countrydle.cogs.daily")
        await bot.load_extension("countrydle.cogs.stats")
        if config.guild_id:
            guild = discord.Object(id=config.guild_id)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)

    bot.setup_hook = setup_hook

    @bot.event
    async def on_ready():
        log.info("logged in as %s (guild=%s, channel=%s)", bot.user, config.guild_id, config.channel_id)

    return bot


def main():
    """Entry point: load config, ensure the database exists, then run the bot."""
    config = Config.from_env()
    init_db(config.database_path)
    bot = create_bot(config)
    bot.run(config.require_token())


if __name__ == "__main__":
    main()
