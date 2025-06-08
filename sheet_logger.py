import requests
import os
import logging
import json

logger = logging.getLogger("MemberCheckBot")


class SheetLogger:
    def __init__(self):
        # Configure more detailed logging
        logger.info("==== SHEET LOGGER INITIALIZATION ====")
        
        # Check if sheet logging is enabled
        self.enabled = os.getenv("ENABLE_SHEET_LOGGING", "false").lower() == "true"
        logger.info(f"Sheet logging enabled: {self.enabled}")
        if not self.enabled:
            logger.info("Google Sheet logging is disabled")
            return
        

        
        # Get the Apps Script URL and secret from environment variables
        self.script_url = os.getenv("GOOGLE_SCRIPT_URL", "")
        self.secret_key = os.getenv("GOOGLE_SCRIPT_SECRET", "")

        logger.info(f"Script URL: {self.script_url}")
        logger.info(f"Secret Key: {'***' if self.secret_key else 'None'}")
        
        # Validate configuration
        if not self.script_url or not self.secret_key:
            logger.warning("Google Sheet logging disabled: Missing URL or secret key")
            self.enabled = False
            return
            
        logger.info("Google Sheet logging initialized")
    
    def log(self, level, message, user_id=None, user_name=None, server=None, error=None):
        """Send a log entry to the Google Sheet"""
        if not self.enabled:
            return False
            
        try:
            # Prepare the payload
            payload = {
                "secretKey": self.secret_key,
                "level": level,
                "message": message,
                "userId": str(user_id) if user_id else "",
                "userName": user_name if user_name else "",
                "server": server if server else "",
                "error": str(error) if error else ""
            }

            logger.debug(f"Sending log to Google Apps Script: {level} - {message}...")
            
            
            # Send to Google Apps Script with a short timeout
            # to avoid blocking the bot if the request is slow
            response = requests.post(
                self.script_url,
                json=payload,
                timeout=5
            )

            # ADD RESPONSE DEBUGGING HERE
            logger.debug(f"Response status: {response.status_code}")
            
            try:
                # Try to parse the JSON response
                response_data = response.json()
                logger.debug(f"Response content: {response_data}")
                
                if response.status_code == 200:
                    if response_data.get("success") == True:
                        logger.debug("Sheet logging successful")
                        return True
                    else:
                        logger.warning(f"Sheet API error: {response_data.get('error', 'Unknown error')}")
                        return False
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse API response: {response.text[:100]}")
                
            logger.warning(f"Sheet logging failed: HTTP {response.status_code}")
            return False
            
        except requests.exceptions.Timeout:
            logger.warning("Sheet logging timed out")
            return False
        except Exception as e:
            logger.warning(f"Error logging to Google Sheet: {e}")
            return False

# Create singleton instance
sheet_logger = SheetLogger()

# Simplified helper function
def log_to_sheet(level, message, user_id=None, user_name=None, server=None, error=None):
    """Helper function to log to Google Sheet"""
    return sheet_logger.log(level, message, user_id, user_name, server, error)