import discord
from discord.ext import commands, tasks
import os
import asyncio
from dotenv import load_dotenv
import datetime
import logging
import traceback
import re

from sheet_logger import log_to_sheet

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")]
)
logger = logging.getLogger("MemberCheckBot")

# Load environment variables
load_dotenv()

# Bot configuration from environment variables
TOKEN = os.getenv("TOKEN")
SERVER_A_ID = int(os.getenv("SERVER_A_ID", "0"))
SERVER_B_ID = int(os.getenv("SERVER_B_ID", "0"))
ROLE_X_ID = int(os.getenv("ROLE_X_ID", "0"))
EXEMPT_ROLES = [int(role_id) for role_id in os.getenv("EXEMPT_ROLES", "").split(",") if role_id]
ACTIVE_CRITERIA = int(os.getenv("ACTIVE_CRITERIA", "1"))
INVITE_LINK = os.getenv("INVITE_LINK", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))
WARNING_CHANNEL_ID = int(os.getenv("WARNING_CHANNEL_ID", "0"))
WARNING_SECONDS = float(os.getenv("WARNING_SECONDS", "16800"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MOD_ROLE_IDS = os.getenv("MOD_ROLE_IDS",[817330791176470548, 817333718870917130]).upper()

REFERENCE_SERVER_NAME = os.getenv("REFERENCE_SERVER_NAME", "Reference Server Name Not Set")
TARGET_SERVER_NAME = os.getenv("TARGET_SERVER_NAME", "Target Server Name Not Set")

# Set up intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Store users who have received warnings with timestamps
warned_users = {}

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user.name} ({bot.user.id})")
    logger.info(f"Active criteria: {ACTIVE_CRITERIA}")
    
    # Check if both servers are accessible
    server_a = bot.get_guild(SERVER_A_ID)
    server_b = bot.get_guild(SERVER_B_ID)
    
    REFERENCE_SERVER_NAME = server_a.name if server_a else REFERENCE_SERVER_NAME
    TARGET_SERVER_NAME = server_b.name if server_b else TARGET_SERVER_NAME
    
    if not server_a:
        logger.critical(f"Cannot access reference server A (ID: {SERVER_A_ID})")
    else:
        logger.info(f"Connected to reference server: {server_a.name}")
    
    if not server_b:
        logger.critical(f"Cannot access target server B (ID: {SERVER_B_ID})")
    else:
        logger.info(f"Connected to target server: {server_b.name}")
    
    # New permission check
    await send_log(f"Bot {bot.user.name} is starting up", "INFO")
    permissions_ok = await check_bot_permissions()
    if not permissions_ok:
        await send_log("Bot is missing required permissions. Some features may not work.", "WARNING")
    
    # Start the periodic check task
    check_members_task.start()

@bot.event
async def on_member_join(member):
    """Check members when they join server B"""
    if member.guild.id != SERVER_B_ID:
        return
    
    logger.info(f"Member joined Server B: {member.name} (ID: {member.id})")
    await check_single_member(member, immediate=True)

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_members_task():
    """Periodically check all members in server B"""
    logger.info("Starting periodic member check")
    
    await send_log(f"Starting periodic member check for {TARGET_SERVER_NAME}", "INFO")
    
    try:
        server_b = bot.get_guild(SERVER_B_ID)
        if not server_b:
            logger.error(f"Could not find server B (ID: {SERVER_B_ID})")
            return
        
        members_checked = 0
        members_warned = 0
        members_kicked = 0
        
        # Fetch all members
        await server_b.chunk()
        
        # Process all members
        for member in server_b.members:
            # Skip bots
            if member.bot:
                continue
                
            result = await check_single_member(member)
            if result == "warned":
                members_warned += 1
            elif result == "kicked":
                members_kicked += 1
            
            members_checked += 1
        
        # Process warnings that have expired
        current_time = datetime.datetime.now()
        for user_id, warn_time in list(warned_users.items()):
            # If warning has expired, kick the user
            secs_diff = (current_time - warn_time).total_seconds()
            if secs_diff >= WARNING_SECONDS:
                member = server_b.get_member(user_id)
                if member:
                    await kick_member(member, "Warning period expired")
                    members_kicked += 1
                warned_users.pop(user_id, None)
        
        logger.info(f"Periodic check complete: {members_checked} members checked, {members_warned} warned, {members_kicked} kicked")
    
    except Exception as e:
        logger.error(f"Error during periodic member check: {e}")

@check_members_task.before_loop
async def before_check_members():
    """Wait for the bot to be ready before starting the task"""
    await bot.wait_until_ready()
    # Initial delay to ensure bot is properly connected
    await asyncio.sleep(10)

async def check_single_member(member, immediate=False):
    """
    Check if a single member meets the criteria
    Returns: "exempt", "ok", "warned", "kicked"
    """
    try:
        # Skip bot accounts
        if member.bot:
            logger.info(f"Skipping bot account: {member.name} (ID: {member.id})")
            return "exempt"
        
        await send_log(f"Checking member {member.name} (ID: {member.id})", "INFO")
		
		# Check if member has exempt roles (protected roles)
        if any(role.id in EXEMPT_ROLES for role in member.roles):
            logger.info(f"Member {member.name} (ID: {member.id}) has exempt role, skipping check")
            return "exempt"
        
        # Get server A
        server_a = bot.get_guild(SERVER_A_ID)
        if not server_a:
            logger.error(f"Could not find server A (ID: {SERVER_A_ID})")
            return "error"
        
        # Try to find the member in server A
        try:
            member_in_a = await server_a.fetch_member(member.id)
        except discord.NotFound:
            member_in_a = None
        except discord.HTTPException as e:
            logger.error(f"HTTP error when fetching member {member.id} in server A: {e}")
            return "error"
        
        # Determine which check to perform and if the member passes
        passes_check = True
        
        # Criteria 1: User must be in server A
        if ACTIVE_CRITERIA == 1:
            if not member_in_a:
                passes_check = False
                reason = f"not a member of our main server: {REFERENCE_SERVER_NAME}"
        
        # Criteria 2: User must have role X in server A
        elif ACTIVE_CRITERIA == 2:
            if not member_in_a:
                passes_check = False
                reason = f"not a member of our main server: {REFERENCE_SERVER_NAME}"
            else:
                has_role = any(role.id == ROLE_X_ID for role in member_in_a.roles)
                if not has_role:
                    passes_check = False
                    reason = f"doesn't have the required role in our main server: {REFERENCE_SERVER_NAME}"
        
        # If the member passes, we're done
        if passes_check:
            return "ok"
        
        # If the user already has a warning and immediate is True, kick them
        if member.id in warned_users and immediate:
            await kick_member(member, reason)
            return "kicked"
        
        # If the user doesn't have a warning yet, warn them
        if member.id not in warned_users:
            await warn_member(member, reason)
            return "warned"
        
        # Otherwise, we've already warned them and are waiting for the timer
        return "warned"
        
    except Exception as e:
        logger.error(f"Error checking member {member.name} (ID: {member.id}): {e}")
        await send_log(f"Error checking member {member.name} (ID: {member.id}): {e}", "ERROR", error=traceback.format_exc())
        return "error"

async def warn_member(member, reason):
    """Send warning to member and log in warning channel"""
    try:
        # Create embed for warning
        embed = discord.Embed(
            title="Warning: You may be removed from the server",
            description=f"You are at risk of being removed because you are {reason}.",
            color=discord.Color.yellow()
        )
        
        embed.add_field(
            name=f"You have {WARNING_SECONDS/3600} hours to comply",
            value=f"Join our main server using this link: {INVITE_LINK}\n"
                  f"{'And get the required role' if ACTIVE_CRITERIA == 2 else ''}",
            inline=False
        )
        
        embed.set_footer(text="This is an automated message.")
        
        # Try to send DM
        try:
            await member.send(embed=embed)
            logger.info(f"Sent warning DM to {member.name} (ID: {member.id})")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Failed to send warning DM to {member.name} (ID: {member.id}): {e}")
        
        # Try to send message to warning channel
        if WARNING_CHANNEL_ID:
            channel = bot.get_channel(WARNING_CHANNEL_ID)
            if channel:
                warning_embed = discord.Embed(
                    title=f"⚠️ Member Warning: {member.name}",
                    description=f"Member {member.mention} has been warned because they are {reason}.",
                    color=discord.Color.yellow()
                )
                warning_embed.add_field(
                    name="Action Required",
                    value=f"User has {WARNING_SECONDS/3600} hours to comply or will be removed.",
                    inline=False
                )
                
                
                await send_log(f"⚠️ Member {member.name} (ID: {member.id}) has been warned: {reason}", "WARNING")
                await channel.send(
                    f"Hey {member.mention},",
                    embed=warning_embed
    			)


            
        
        # Add user to warned users with timestamp
        warned_users[member.id] = datetime.datetime.now()
        
    except Exception as e:
        logger.error(f"Error warning {member.name} (ID: {member.id}): {e}")

async def kick_member(member, reason):
    """Kick a member after sending them a DM with the embed"""
    try:
        # Create embed for kick message
        embed = discord.Embed(
            title="You have been removed from the server",
            description=f"You were removed because you are {reason}.",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="How to rejoin",
            value=f"Join our main server first using this link: {INVITE_LINK}\n"
                  f"{'And get the required role' if ACTIVE_CRITERIA == 2 else ''}\n"
                  f"Then you can rejoin the server you were removed from.",
            inline=False
        )
        
        embed.set_footer(text="This is an automated message.")
        
        # Try to send DM first
        try:
            await member.send(embed=embed)
            logger.info(f"Sent kick DM to {member.name} (ID: {member.id})")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Failed to send kick DM to {member.name} (ID: {member.id}): {e}")
        
        # Try to send message to warning channel
        if WARNING_CHANNEL_ID:
            channel = bot.get_channel(WARNING_CHANNEL_ID)
            if channel:
                kick_embed = discord.Embed(
                    title=f"🔨 Member Kicked: {member.name}",
                    description=f"Member {member.mention} has been kicked because they are {reason}.",
                    color=discord.Color.red()
                )
                mod_mentions = " ".join([f"<@&{role_id}>" for role_id in MOD_ROLE_IDS])
                await channel.send(
                    f"Hey {member.mention},",
                    embed=kick_embed
                )
        
        # Kick member
        await send_log(f"🔨 Member {member.name} (ID: {member.id}) has been kicked: {reason}", "WARNING")
        await member.kick(reason=f"Failed to meet server criteria: {reason}")
        logger.info(f"Kicked {member.name} (ID: {member.id})")
        
        # Remove from warned users list if present
        warned_users.pop(member.id, None)
        
        return True
        
    except discord.Forbidden:
        logger.error(f"Bot doesn't have permission to kick {member.name} (ID: {member.id})")
        return False
    except Exception as e:
        logger.error(f"Error kicking {member.name} (ID: {member.id}): {e}")
        return False


# Add this function after your other functions
async def send_log(message, level="INFO", error=None):
    """Send logs to a specified channel on the reference server"""
    if not LOG_CHANNEL_ID:
        return
        
    # Only log if the level is sufficient
    log_levels = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    if log_levels.get(level, 0) < log_levels.get(LOG_LEVEL, 1):
        return
    
    try:
        # Standard logging to console/file
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        elif level == "CRITICAL":
            logger.critical(message)
        else:
            logger.debug(message)
        
        # Try to send to log channel
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            return
            
        # Check permission to send messages
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            logger.warning(f"Bot doesn't have permission to send logs to channel {LOG_CHANNEL_ID}")
            return
            
        # Create embed for log message
        color_map = {
            "DEBUG": discord.Color.light_grey(),
            "INFO": discord.Color.blue(),
            "WARNING": discord.Color.gold(),
            "ERROR": discord.Color.red(),
            "CRITICAL": discord.Color.dark_red()
        }
        
        embed = discord.Embed(
            title=f"{level} Log",
            description=message,
            color=color_map.get(level, discord.Color.default()),
            timestamp=datetime.datetime.now()
        )
        
        if error:
            embed.add_field(
                name="Error Details",
                value=f"```\n{str(error)[:1000]}\n```",
                inline=False
            )
            
            # Add traceback for errors
            if level in ["ERROR", "CRITICAL"] and error:
                tb = traceback.format_exception(type(error), error, error.__traceback__)
                tb_text = "".join(tb)
                if len(tb_text) > 1000:
                    tb_text = tb_text[:997] + "..."
                embed.add_field(
                    name="Traceback",
                    value=f"```py\n{tb_text}\n```",
                    inline=False
                )
        
        await channel.send(embed=embed)
        
        # try:
        #     user_id = None
        #     user_name = None
            
        #     # Try to extract user ID if present in message
        #     id_match = re.search(r'ID: (\d+)', message)
        #     if id_match:
        #         user_id = id_match.group(1)
                    
        #     # Try to extract user name if present
        #     name_match = re.search(r'Member (\S+)', message)
        #     if name_match:
        #         user_name = name_match.group(1)
            
        #     # Log to Google Sheet
        #     server_info = f"{REFERENCE_SERVER_NAME}/{TARGET_SERVER_NAME}"
        #     log_to_sheet(level, message, user_id, user_name, server_info, str(error) if error else None)

        # except Exception as sheet_err:
        #     # This won't break the bot if sheet logging fails
        #     logger.warning(f"Sheet logging error (non-critical): {sheet_err}")
		
        
    except Exception as e:
        logger.error(f"Failed to send log to channel: {e}")


async def check_bot_permissions():
    """Check if the bot has all necessary permissions in both servers"""
    required_permissions = {
        "kick_members": "Kick Members",
        "send_messages": "Send Messages",
        "embed_links": "Embed Links",
        "read_message_history": "Read Message History",
        "view_channel": "View Channels"
    }
    
    missing_permissions = {}
    servers = {}
    
    try:
        # Check permissions in Server A
        server_a = bot.get_guild(SERVER_A_ID)
        if server_a:
            servers["Server A"] = server_a
            missing_in_a = []
            for perm_attr, perm_name in required_permissions.items():
                if not getattr(server_a.me.guild_permissions, perm_attr):
                    missing_in_a.append(perm_name)
            if missing_in_a:
                missing_permissions["Server A"] = missing_in_a
        else:
            await send_log(f"Cannot access reference server A (ID: {SERVER_A_ID})", "CRITICAL")
        
        # Check permissions in Server B
        server_b = bot.get_guild(SERVER_B_ID)
        if server_b:
            servers["Server B"] = server_b
            missing_in_b = []
            for perm_attr, perm_name in required_permissions.items():
                if not getattr(server_b.me.guild_permissions, perm_attr):
                    missing_in_b.append(perm_name)
            if missing_in_b:
                missing_permissions["Server B"] = missing_in_b
        else:
            await send_log(f"Cannot access target server B (ID: {SERVER_B_ID})", "CRITICAL")
        
        # Check channel permissions
        for server_name, server in servers.items():
            # Check warning channel
            if WARNING_CHANNEL_ID and server.id == SERVER_B_ID:
                channel = bot.get_channel(WARNING_CHANNEL_ID)
                if channel:
                    perms = channel.permissions_for(server.me)
                    if not perms.send_messages or not perms.embed_links:
                        await send_log(f"Bot doesn't have required permissions in warning channel (<#{WARNING_CHANNEL_ID}>)", "WARNING")
                else:
                    await send_log(f"Warning channel not found (ID: {WARNING_CHANNEL_ID})", "WARNING")
            
            # Check log channel
            if LOG_CHANNEL_ID and server.id == SERVER_A_ID:
                channel = bot.get_channel(LOG_CHANNEL_ID)
                if channel:
                    perms = channel.permissions_for(server.me)
                    if not perms.send_messages or not perms.embed_links:
                        logger.warning(f"Bot doesn't have required permissions in log channel (<#{LOG_CHANNEL_ID}>)")
                else:
                    logger.warning(f"Log channel not found (ID: {LOG_CHANNEL_ID})")
        
        # Send missing permissions to log
        for server_name, missing_perms in missing_permissions.items():
            perms_text = ", ".join(missing_perms)
            message = f"Missing required permissions in {server_name}: {perms_text}"
            await send_log(message, "CRITICAL")
            
        return len(missing_permissions) == 0
            
    except Exception as e:
        await send_log("Failed to check bot permissions", "ERROR", e)
        return False


async def verify_channel_access(channel_id):
    """Verify that a channel exists and the bot can access it"""
    if not channel_id:
        return False, "No channel ID provided"
        
    channel = bot.get_channel(channel_id)
    if not channel:
        return False, f"Channel not found (ID: {channel_id})"
        
    # Check permissions
    permissions = channel.permissions_for(channel.guild.me)
    if not permissions.view_channel:
        return False, f"Bot cannot view channel (ID: {channel_id})"
    if not permissions.send_messages:
        return False, f"Bot cannot send messages to channel (ID: {channel_id})"
    if not permissions.embed_links:
        return False, f"Bot cannot send embeds to channel (ID: {channel_id})"
        
    return True, "Channel accessible"




@bot.command(name="status")
@commands.has_permissions(administrator=True)
async def status_command(ctx):
    """Show the current bot status and configuration"""
    server_a = bot.get_guild(SERVER_A_ID)
    server_b = bot.get_guild(SERVER_B_ID)
    
    embed = discord.Embed(
        title="Member Check Bot - Status",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Active Criteria",
        value=f"Criteria {ACTIVE_CRITERIA}: {'Membership Check' if ACTIVE_CRITERIA == 1 else 'Role Check'}",
        inline=False
    )
    
    embed.add_field(
        name="Reference Server (A)",
        value=f"{server_a.name if server_a else 'Not Found'} (ID: {SERVER_A_ID})",
        inline=True
    )
    
    embed.add_field(
        name="Target Server (B)",
        value=f"{server_b.name if server_b else 'Not Found'} (ID: {SERVER_B_ID})",
        inline=True
    )
    
    if ACTIVE_CRITERIA == 2 and server_a:
        role = discord.utils.get(server_a.roles, id=ROLE_X_ID)
        embed.add_field(
            name="Required Role (X)",
            value=f"{role.name if role else 'Not Found'} (ID: {ROLE_X_ID})",
            inline=False
        )
    
    embed.add_field(
        name="Warning Period",
        value=f"{WARNING_SECONDS/3600} hours",
        inline=True
    )
    
    embed.add_field(
        name="Check Interval",
        value=f"{CHECK_INTERVAL} seconds",
        inline=True
    )
    
    embed.add_field(
        name="Exempt Roles",
        value=", ".join([str(role_id) for role_id in EXEMPT_ROLES]) if EXEMPT_ROLES else "None",
        inline=False
    )
    
    # Add currently warned users
    warned_users_text = "None" if not warned_users else "\n".join(
        [f"<@{user_id}> - warned {(datetime.datetime.now() - time).seconds // 3600}h ago" 
         for user_id, time in warned_users.items()][:10]  # Limit to first 10
    )
    
    embed.add_field(
        name=f"Currently Warned Users ({len(warned_users)})",
        value=warned_users_text,
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name="checkall")
@commands.has_permissions(administrator=True)
async def checkall_command(ctx):
    """Force check all members in server B"""
    await ctx.send("Starting manual check of all members...")
    await check_members_task()
    await ctx.send("Manual check completed!")

@bot.command(name="check")
@commands.has_permissions(administrator=True)
async def check_command(ctx, user_id: int):
    """Check a specific user by ID"""
    try:
        server_b = bot.get_guild(SERVER_B_ID)
        member = server_b.get_member(user_id)
        
        if not member:
            await ctx.send(f"User with ID {user_id} not found in server B.")
            return
            
        result = await check_single_member(member, immediate=True)
        await ctx.send(f"Check result for {member.name}: {result}")
    except Exception as e:
        await ctx.send(f"Error checking user: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        return
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
        return
    logger.error(f"Command error: {error}")
    await ctx.send(f"Command error: {error}")

# Run the bot
if __name__ == "__main__":
    if not TOKEN:
        logger.critical("No Discord token provided. Please set TOKEN in .env file.")
        exit(1)
        
    if not SERVER_A_ID or not SERVER_B_ID:
        logger.critical("Server IDs not properly configured. Check SERVER_A_ID and SERVER_B_ID in .env file.")
        exit(1)
    
    logger.info("Starting bot...")
    bot.run(TOKEN)