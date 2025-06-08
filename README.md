# Discord Server Membership Enforcer

A Discord bot that ensures users in your secondary server are also members of your main server, optionally with specific roles. Perfect for communities with multiple specialized servers.

## Features

### Core Functionality
- **Server Membership Check:** Ensures users in your target server are also members of your main server
- **Role Verification:** Optionally requires users to have a specific role in your main server
- **Warning System:** Warns users before removal with customizable grace periods
- **Protected Roles:** Designate roles that exempt users from checks
- **Detailed Logging:** Comprehensive activity logs in a dedicated channel

### Key Benefits
- Maintain connected communities across multiple Discord servers
- Encourage users to join your main server
- Automate enforcement of server membership rules
- Keep moderators informed with targeted notifications

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token ([Create one here](https://discord.com/developers/applications))
- Administrator permissions on both Discord servers

### Installation

1. **Clone or download this repository**

2. **Install dependencies**
   ```bash
   pip install discord.py python-dotenv
   ```

3. **Configure environment variables**
   - Rename `.env.example` to `.env`
   - Fill in your configuration values (see Configuration section)

4. **Run the bot**
   ```bash
   python member_check.py
   ```

## Basic Commands

| Command | Description | Example |
|---------|-------------|---------|
| `!status` | Shows bot status and configuration | `!status` |
| `!checkall` | Force check all members immediately | `!checkall` |
| `!check <user_id>` | Check a specific user | `!check 123456789012345678` |
| `!testwarn <user_id>` | Send a test warning to a user | `!testwarn 123456789012345678` |
| `!testkick <user_id>` | Test kick functionality (requires confirmation) | `!testkick 123456789012345678` |
| `!checkrole <user_id>` | Check if a user has the required role | `!checkrole 123456789012345678` |
| `!loglevel <level>` | Change logging level | `!loglevel DEBUG` |

## Configuration

Edit the `.env` file with your settings:

```properties
# Discord Application/Bot credentials
APP_ID = your_app_id
TOKEN = your_bot_token

# Server IDs
SERVER_A_ID = your_main_server_id      # Reference/main server
SERVER_B_ID = your_secondary_server_id # Target server to enforce membership

# Role settings
ROLE_X_ID = role_id_required           # Role required in SERVER_A (if using role check)
EXEMPT_ROLES = role_id1,role_id2       # Roles exempt from checks

# Mode settings
ACTIVE_CRITERIA = 2                    # 1=Membership only, 2=Membership+Role

# Operational settings
INVITE_LINK = https://discord.gg/yourinvite
CHECK_INTERVAL = 1800                  # Check frequency in seconds
WARNING_SECONDS = 16800                # Grace period before kicking

# Channel settings
WARNING_CHANNEL_ID = warning_channel_id # Where warnings/kicks are announced
LOG_CHANNEL_ID = log_channel_id        # Where all logs are sent

# Mod role settings
MOD_ROLE_IDS = [role_id1, role_id2]    # Roles to ping for warnings/kicks
```

## Understanding Member Checks

The bot performs checks in this order:

1. **Exempt Role Check**: Users with exempt roles are skipped entirely
2. **Server Membership**: Verifies if the user is in your main server
3. **Role Check** (if enabled): Verifies if the user has the required role
4. **Warning System**: If checks fail, warns the user and sets a timer
5. **Removal**: When grace period expires, user is removed if still non-compliant

## Troubleshooting

- **Bot not responding to commands**: Ensure bot has proper permissions
- **Members not being checked**: Verify `CHECK_INTERVAL` isn't too long
- **No logs appearing**: Check `LOG_CHANNEL_ID` and permissions
- **Everyone exempt from checks**: Double-check your `EXEMPT_ROLES` setting

## Security Considerations

⚠️ **IMPORTANT**: Never share your bot token! If compromised, immediately reset it in the [Discord Developer Portal](https://discord.com/developers/applications).

## License

This project is available under the MIT License.