#!/usr/bin/env python3
"""
Deploy script for uploading files to PythonAnywhere
"""

import requests
import os
from pathlib import Path

# Configuration - UPDATE THESE
PYTHONANYWHERE_USERNAME = "YOUR_USERNAME"  # Change this!
API_TOKEN = "YOUR_API_TOKEN"  # Get from Account -> API Token

# API base URL (use eu.pythonanywhere.com if you're on the EU server)
API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}"

# Files to upload
FILES_TO_UPLOAD = [
    "bank_report.py",
    "telegram_bot.py",
    "requirements.txt",
    "config.env",
    "fonts/Arial.ttf",
    "fonts/NotoSansHebrew-Regular.ttf",
]

def upload_file(local_path, remote_path):
    """Upload a single file to PythonAnywhere."""
    url = f"{API_BASE}/files/path/home/{PYTHONANYWHERE_USERNAME}/{remote_path}"

    with open(local_path, "rb") as f:
        response = requests.post(
            url,
            files={"content": f},
            headers={"Authorization": f"Token {API_TOKEN}"}
        )

    if response.status_code in [200, 201]:
        print(f"✓ Uploaded: {remote_path}")
        return True
    else:
        print(f"✗ Failed: {remote_path} - {response.status_code}: {response.text}")
        return False

def create_directory(remote_path):
    """Create a directory on PythonAnywhere (by uploading a placeholder)."""
    # PythonAnywhere creates directories automatically when uploading files
    pass

def main():
    script_dir = Path(__file__).parent

    print("Deploying to PythonAnywhere...")
    print(f"Username: {PYTHONANYWHERE_USERNAME}")
    print()

    if PYTHONANYWHERE_USERNAME == "YOUR_USERNAME" or API_TOKEN == "YOUR_API_TOKEN":
        print("ERROR: Please update PYTHONANYWHERE_USERNAME and API_TOKEN in this script!")
        print()
        print("To get your API token:")
        print("1. Go to pythonanywhere.com")
        print("2. Click Account (top right)")
        print("3. Go to API Token section")
        print("4. Create a new token if needed")
        return

    success_count = 0
    fail_count = 0

    for file_path in FILES_TO_UPLOAD:
        local_path = script_dir / file_path
        if local_path.exists():
            if upload_file(local_path, file_path):
                success_count += 1
            else:
                fail_count += 1
        else:
            print(f"✗ Not found: {file_path}")
            fail_count += 1

    print()
    print(f"Done! {success_count} uploaded, {fail_count} failed")

    if success_count > 0:
        print()
        print("Next steps:")
        print("1. Open a Bash console on PythonAnywhere")
        print("2. Restart the bot with:")
        print(f"   cd /home/{PYTHONANYWHERE_USERNAME}")
        print("   source venv/bin/activate")
        print("   pkill -f telegram_bot.py  # Stop existing bot")
        print("   nohup python telegram_bot.py &")

if __name__ == "__main__":
    main()
