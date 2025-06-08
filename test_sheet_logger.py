import os
from dotenv import load_dotenv
import logging
import sys

# Configure logging for this test
logging.basicConfig(
    level=logging.DEBUG,  # Notice: DEBUG level to see everything
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TestLogger")

# Load environment variables
load_dotenv()

# Import the sheet logger
from sheet_logger import log_to_sheet

def main():
    logger.info("Starting sheet logger test")
    
    # Print relevant environment variables (sanitized)
    print("\nEnvironment Variables:")
    enable_setting = os.getenv("ENABLE_SHEET_LOGGING", "false")
    print(f"ENABLE_SHEET_LOGGING: {enable_setting}")
    
    script_url = os.getenv("GOOGLE_SCRIPT_URL", "")
    print(f"GOOGLE_SCRIPT_URL: {script_url[:30]}...{script_url[-10:] if len(script_url) > 40 else ''}")
    
    secret_key = os.getenv("GOOGLE_SCRIPT_SECRET", "")
    print(f"GOOGLE_SCRIPT_SECRET: {'[SET]' if secret_key else '[NOT SET]'}")
    
    # Send a test log
    print("\nSending test log entry...")
    result = log_to_sheet(
        "TEST", 
        "This is a test message from test_sheet_logger.py", 
        user_id="111222333",
        user_name="TestUser",
        server="Test Server",
        error=None
    )
    
    print(f"\nLog result: {'SUCCESS' if result else 'FAILED'}")

if __name__ == "__main__":
    main()