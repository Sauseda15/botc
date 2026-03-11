# === discord_bot/cogs/game_cog.py ===
import asyncio
import datetime
import os
import discord
from discord.ext import commands
import logging
from views.views import Game, GameType

# Logging setup
logging.basicConfig(level=logging.INFO)

# Configurable constants
PHOTOS_FOLDER = os.path.join(os.getcwd(), "photos")
PLAYERS_ROLE_ID = int(os.getenv("PLAYERS_ROLE_ID", 0))  # Use env var or fallback

class GameCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.games = {}
        self.players = []
        self.game_mode = None
        self.game_time = None
        self.signup_message = None
        self.text_channel = None
        self.voice_channel = None
        self.event = None

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f'{self.bot.user} connected.')
        guild = self.bot.guilds[0]
        logging.info(f'Guild: {guild.name}')
        try:
            synced = await self.bot.tree.sync()
            logging.info(f'Synced {len(synced)} commands.')
        except discord.HTTPException as e:
            logging.error(f'Sync error: {e}')

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before, after):
        status = after.status.name
        if status == "started":
            await self.handle_event_start(after)
        elif status == "ended":
            await self.handle_event_end(after)

    async def handle_event_start(self, event):
        logging.info(f'Starting event: {event.name}')

        text_channel = discord.utils.get(
            event.guild.text_channels,
           name=f"{self.game_mode.name} Game"
           )

        players_role = discord.utils.get(event.guild.roles, id=PLAYERS_ROLE_ID)
        if text_channel and players_role:
            await text_channel.send(
                f'{players_role.mention} The {event.name} game has started! Join the voice channel.'
            )

        player_ids = [user_id for user_id, _, role in self.players if role == 'player']
        storyteller_ids = [user_id for user_id, _, role in self.players if role == "storyteller"]

        if not storyteller_ids:
            logging.error("No storyteller found for the game.")
            return

        storyteller_id = storyteller_ids[0]

        game = Game(
            bot = self.bot,
            game_mode = self.game_mode,
            players = player_ids,
            storyteller_id = storyteller_id
            )

        self.games[event.name] = game
        await game.start_game()

    async def handle_event_end(self, event):
        text_channel = discord.utils.get(event.guild.text_channels, name=f"{event.name} Game")
        await text_channel.send(f'The {event.name} game has ended. Thanks for playing!')

    @commands.hybrid_command(name='create_game', aliases=['cg'])
    async def create_game(self, ctx: commands.Context):
        await ctx.author.send('Creating a new game...')
        self.players.clear()

        script_select = discord.ui.Select(
            placeholder='Select a game mode:',
            options=[
                discord.SelectOption(label='Trouble\'s Brewing', value='troubles_brewing'),
                discord.SelectOption(label='Sects & Violets', value='sects_and_violets'),
                discord.SelectOption(label='Bad Moon Rising', value='bad_moon_rising')
            ]
        )
        view = discord.ui.View()
        view.add_item(script_select)
        msg = await ctx.author.send('Select a game mode:', view=view)
        interaction = await self.wait_for_interaction(ctx, msg)
        if not interaction:
            return

        self.players.append((interaction.user.display_name, 'storyteller'))
        selected_mode = interaction.data['values'][0]

        mode_map = {
            'troubles_brewing': GameType.TROUBLES_BREWING,
            'sects_and_violets': GameType.SECTS_AND_VIOLETS,
            'bad_moon_rising': GameType.BAD_MOON_RISING
        }
        
        self.game_mode = mode_map.get(selected_mode) # Convert to GameType enum

        if not self.game_mode:
            await ctx.author.send('Invalid game mode selected.')
            return

        await ctx.author.send('Enter the date/time for the game (YYYY-MM-DD HH:MM):')
        msg = await self.wait_for_message(ctx)
        self.game_time = self.parse_game_time(msg.content) if msg else None
        if not self.game_time:
            await ctx.author.send('Invalid date/time format.')
            return

        await self.create_game_channels(ctx)
        await self.create_discord_event(ctx)

    async def wait_for_interaction(self, ctx, message):
        def check(i): return i.user == ctx.author and i.message.id == message.id
        try:
            return await self.bot.wait_for('interaction', check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.author.send('Timeout: No response.')
            return None

    async def wait_for_message(self, ctx):
        def check(m): return m.author == ctx.author and m.channel.type == discord.ChannelType.private
        try:
            return await self.bot.wait_for('message', check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.author.send('Timeout: No response.')
            return None

    def parse_game_time(self, raw: str):
        try:
            return datetime.datetime.strptime(raw, '%Y-%m-%d %H:%M')
        except ValueError:
            return None

    async def create_game_channels(self, ctx):
        category = await ctx.guild.create_category(f'{self.game_mode} Game')
        self.text_channel = await ctx.guild.create_text_channel(f'{self.game_mode} Game', category=category)
        self.voice_channel = await ctx.guild.create_voice_channel(f'{self.game_mode} Game', category=category)
        await self.player_signup_sheet(ctx)
        await ctx.send(f'Created channels for {self.game_mode}', ephemeral=True)

    async def create_discord_event(self, ctx):
        start_time = datetime.datetime.now()
        end_time = self.game_time + datetime.timedelta(hours=2)
        self.event = await ctx.guild.create_scheduled_event(
            name=f'{self.game_mode} Game',
            start_time=start_time,
            end_time=end_time,
            description=f'signup here {self.signup_message.id}',
            location=f"Voice: {self.voice_channel.name}",
            entity_type=discord.EntityType.voice
        )
        await ctx.send(f'Event created for {self.game_mode}', ephemeral=True)

    async def player_signup_sheet(self, ctx):
        options = [
            discord.SelectOption(label=label.capitalize(), value=value)
            for label, value in [
                ('player', 'player'),
                ('storyteller', 'storyteller'),
                ('spectator', 'spectator'),
                ('traveler', 'traveler'),
                ('absent', 'absent')
            ]
        ]
        select = discord.ui.Select(placeholder='Choose your role', options=options, custom_id='action_select')
        view = discord.ui.View()
        view.add_item(select)
        self.signup_message = await self.text_channel.send('Choose your role:', view=view)

        def check(i): return i.data.get('custom_id') == 'action_select'

        while True:
            try:
                interaction = await self.bot.wait_for('interaction', check=check, timeout=120)
                await self.add_player(interaction, interaction.data['values'][0])
                await interaction.response.send_message(f'Joined as {interaction.data["values"][0]}', ephemeral=True)
                await self.update_signup_sheet()
            except asyncio.TimeoutError:
                await self.text_channel.send('Signup timed out.')
                break

    async def add_player(self, interaction, role):
        user_id = interaction.user.id
        name = interaction.user.display_name
        for i, (pid, pname, _) in enumerate(self.players):
            if pid == user_id:
                self.players[i] = (user_id, name, role)
                return

        self.players.append((user_id, name, role))

    async def update_signup_sheet(self):
        if not self.players:
            await self.text_channel.send('No players signed up.')
            return

        embed = discord.Embed(
            title='Signup Sheet',
            description='List of players',
           timestamp=self.game_time
           )

        for role in ['player', 'storyteller', 'spectator', 'traveler', 'absent']:
            filtered = [name for _, name, r in self.players if r == role]
            embed.add_field(
                name=f'{role.capitalize()}s',
                value='\n'.join(filtered) or 'None yet',
                inline=False
            )

        if self.signup_message:
            await self.signup_message.edit(content=None, embed=embed)
        else:
            self.signup_message = await self.text_channel.send(embed=embed)

# Make the cog globally available if needed from the API
active_game_cog = None

def setup(bot: commands.Bot):
    global active_game_cog
    active_game_cog = GameCog(bot)
    bot.add_cog(active_game_cog)
