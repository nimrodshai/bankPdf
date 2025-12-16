#!/usr/bin/env python3
"""
GitHub Actions Bot Handler

This script runs in GitHub Actions to handle Telegram messages.
Uses GitHub Gists to store files between messages for multi-file support.
"""

import os
import json
import requests
import tempfile
import base64
from pathlib import Path

# Import bank report functions
from bank_report import (
    BankReportGenerator,
    detect_statement_format,
    parse_bank_account_statement,
    parse_credit_card_statement,
    parse_pdf_bank_statement
)
import pandas as pd

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'
GITHUB_API = 'https://api.github.com'

# Gist description prefix to identify our storage gists
GIST_PREFIX = 'bankpdf-user-'


def send_message(chat_id: int, text: str):
    """Send a text message to a chat"""
    requests.post(f'{TELEGRAM_API}/sendMessage', json={
        'chat_id': chat_id,
        'text': text
    })


def send_document(chat_id: int, file_path: str, filename: str, caption: str = ''):
    """Send a document to a chat"""
    with open(file_path, 'rb') as f:
        requests.post(
            f'{TELEGRAM_API}/sendDocument',
            data={'chat_id': chat_id, 'caption': caption},
            files={'document': (filename, f)}
        )


def download_file(file_id: str, dest_path: str):
    """Download a file from Telegram"""
    response = requests.get(f'{TELEGRAM_API}/getFile', params={'file_id': file_id})
    file_path = response.json()['result']['file_path']
    file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
    response = requests.get(file_url)
    with open(dest_path, 'wb') as f:
        f.write(response.content)


def github_headers():
    """Get GitHub API headers"""
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }


def find_user_gist(chat_id: int):
    """Find existing gist for user"""
    response = requests.get(f'{GITHUB_API}/gists', headers=github_headers())
    if response.status_code == 200:
        for gist in response.json():
            if gist['description'] == f'{GIST_PREFIX}{chat_id}':
                return gist['id']
    return None


def get_user_files(chat_id: int):
    """Get list of stored files for user"""
    gist_id = find_user_gist(chat_id)
    if not gist_id:
        return {}

    response = requests.get(f'{GITHUB_API}/gists/{gist_id}', headers=github_headers())
    if response.status_code == 200:
        gist = response.json()
        # Return dict of filename -> file_info (contains telegram file_id)
        files = {}
        for filename, file_data in gist['files'].items():
            if filename == '_metadata.json':
                files = json.loads(file_data['content'])
                break
        return files
    return {}


def add_user_file(chat_id: int, filename: str, file_id: str):
    """Add a file reference for user"""
    gist_id = find_user_gist(chat_id)
    files = get_user_files(chat_id)

    # Add new file
    files[filename] = {'file_id': file_id, 'filename': filename}

    gist_data = {
        'description': f'{GIST_PREFIX}{chat_id}',
        'files': {
            '_metadata.json': {
                'content': json.dumps(files, indent=2)
            }
        }
    }

    if gist_id:
        # Update existing gist
        requests.patch(f'{GITHUB_API}/gists/{gist_id}',
                      headers=github_headers(), json=gist_data)
    else:
        # Create new gist
        gist_data['public'] = False
        requests.post(f'{GITHUB_API}/gists',
                     headers=github_headers(), json=gist_data)

    return len(files)


def clear_user_files(chat_id: int):
    """Delete user's gist"""
    gist_id = find_user_gist(chat_id)
    if gist_id:
        requests.delete(f'{GITHUB_API}/gists/{gist_id}', headers=github_headers())


def handle_start(chat_id: int):
    """Handle /start command"""
    clear_user_files(chat_id)
    send_message(chat_id,
        "שלום! אני בוט להפקת דוחות בנק\n\n"
        "פקודות:\n"
        "/start - התחל מחדש\n"
        "/help - עזרה\n"
        "/clear - נקה קבצים שהועלו\n"
        "/status - כמה קבצים הועלו\n"
        "/report - הפק דוח PDF\n\n"
        "שלח לי קבצי xlsx או pdf מהבנק ואז הקלד /report"
    )


def handle_help(chat_id: int):
    """Handle /help command"""
    send_message(chat_id,
        "איך להשתמש:\n\n"
        "1. שלח קובץ xlsx או pdf מהבנק\n"
        "2. שלח עוד קבצים אם יש\n"
        "3. הקלד /report להפקת הדוח\n\n"
        "פקודות נוספות:\n"
        "/clear - נקה קבצים שהועלו\n"
        "/status - כמה קבצים הועלו"
    )


def handle_clear(chat_id: int):
    """Handle /clear command"""
    clear_user_files(chat_id)
    send_message(chat_id, "כל הקבצים נמחקו")


def handle_status(chat_id: int):
    """Handle /status command"""
    files = get_user_files(chat_id)
    count = len(files)
    if count == 0:
        send_message(chat_id, "אין קבצים ממתינים. שלח קבצי xlsx או pdf")
    else:
        file_list = "\n".join([f"  - {f}" for f in files.keys()])
        send_message(chat_id, f"יש לך {count} קבצים ממתינים:\n{file_list}\n\nהקלד /report להפקת הדוח")


def handle_document(chat_id: int, document: dict):
    """Handle uploaded document - store for later processing"""
    file_name = document.get('file_name', 'file')
    file_id = document['file_id']

    # Check file type
    if not file_name.endswith(('.xlsx', '.csv', '.pdf')):
        send_message(chat_id, "אנא שלח קובץ xlsx, csv או pdf")
        return

    # Store file reference
    count = add_user_file(chat_id, file_name, file_id)

    send_message(chat_id,
        f"קובץ התקבל: {file_name}\n"
        f"סה\"כ קבצים: {count}\n\n"
        f"שלח עוד קבצים או הקלד /report להפקת הדוח"
    )


def handle_report(chat_id: int):
    """Handle /report command - generate PDF from all stored files"""
    files = get_user_files(chat_id)

    if not files:
        send_message(chat_id, "לא נמצאו קבצים. שלח קבצי xlsx או pdf תחילה")
        return

    send_message(chat_id, f"מעבד {len(files)} קבצים...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            all_dataframes = []
            first_file_path = None

            for filename, file_info in files.items():
                file_path = os.path.join(temp_dir, filename)
                download_file(file_info['file_id'], file_path)

                if first_file_path is None:
                    first_file_path = file_path

                # Process file
                file_ext = Path(file_path).suffix.lower()

                try:
                    if file_ext == '.pdf':
                        df = parse_pdf_bank_statement(file_path)
                    elif file_ext == '.xlsx':
                        df_raw = pd.read_excel(file_path, header=None)
                        stmt_format, _ = detect_statement_format(df_raw)

                        if stmt_format == 'credit_card':
                            df = parse_credit_card_statement(file_path)
                        elif stmt_format == 'bank_account':
                            df = parse_bank_account_statement(file_path)
                        else:
                            continue
                    elif file_ext == '.csv':
                        df = None
                        for encoding in ['utf-8', 'windows-1255', 'iso-8859-8']:
                            try:
                                df = pd.read_csv(file_path, encoding=encoding)
                                break
                            except UnicodeDecodeError:
                                continue
                        if df is None:
                            continue
                    else:
                        continue

                    all_dataframes.append(df)
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
                    continue

            if not all_dataframes:
                send_message(chat_id, "לא הצלחתי לקרוא את הקבצים")
                return

            # Merge all dataframes
            merged_df = pd.concat(all_dataframes, ignore_index=True)

            # Generate PDF
            output_path = os.path.join(temp_dir, 'bank_report.pdf')

            generator = BankReportGenerator(first_file_path, output_path)
            generator.df = merged_df
            generator.statement_type = 'bank_account'

            (generator
             .normalize_columns()
             .parse_dates()
             .categorize_transactions()
             .calculate_summary()
             .create_charts()
             .generate_pdf())

            # Send PDF back
            caption = (
                f"הדוח שלך מוכן!\n"
                f"עובדו {len(files)} קבצים\n\n"
                f"הכנסות: {generator.total_income:,.0f} ש\"ח\n"
                f"הוצאות: {generator.total_expenses:,.0f} ש\"ח\n"
                f"מאזן: {generator.balance:,.0f} ש\"ח"
            )
            send_document(chat_id, output_path, 'bank_report.pdf', caption)

            # Clear files after successful report
            clear_user_files(chat_id)

    except Exception as e:
        send_message(chat_id, f"שגיאה בהפקת הדוח: {str(e)}")


def main():
    """Main entry point - process single Telegram update"""
    update_json = os.environ.get('TELEGRAM_UPDATE', '{}')
    update = json.loads(update_json)

    if not update:
        print("No update received")
        return

    # Extract message
    message = update.get('message')
    if not message:
        print("No message in update")
        return

    chat_id = message['chat']['id']
    text = message.get('text', '')
    document = message.get('document')

    # Handle commands
    if text.startswith('/start'):
        handle_start(chat_id)
    elif text.startswith('/help'):
        handle_help(chat_id)
    elif text.startswith('/clear'):
        handle_clear(chat_id)
    elif text.startswith('/status'):
        handle_status(chat_id)
    elif text.startswith('/report'):
        handle_report(chat_id)
    elif document:
        handle_document(chat_id, document)
    else:
        send_message(chat_id, "שלח קובץ xlsx או pdf, או הקלד /help לעזרה")


if __name__ == '__main__':
    main()
