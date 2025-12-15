#!/usr/bin/env python3
"""
GitHub Actions Bot Handler

This script runs in GitHub Actions to handle Telegram messages.
It processes one message at a time (stateless) and responds via Telegram API.
"""

import os
import json
import requests
import tempfile
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
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'


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
    # Get file path
    response = requests.get(f'{TELEGRAM_API}/getFile', params={'file_id': file_id})
    file_path = response.json()['result']['file_path']

    # Download file
    file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
    response = requests.get(file_url)

    with open(dest_path, 'wb') as f:
        f.write(response.content)


def handle_start(chat_id: int):
    """Handle /start command"""
    send_message(chat_id,
        "שלום! אני בוט להפקת דוחות בנק\n\n"
        "פקודות:\n"
        "/start - התחל מחדש\n"
        "/help - עזרה\n\n"
        "שלח לי קובץ xlsx או pdf מהבנק ואקבל דוח PDF"
    )


def handle_help(chat_id: int):
    """Handle /help command"""
    send_message(chat_id,
        "איך להשתמש:\n\n"
        "1. שלח קובץ xlsx או pdf מהבנק\n"
        "2. המתן לעיבוד (עד דקה)\n"
        "3. קבל PDF עם סיכום הכנסות והוצאות\n\n"
        "הערה: בגלל שהבוט רץ על GitHub Actions,\n"
        "כל קובץ מעובד בנפרד ומיד מוחזר כדוח."
    )


def handle_document(chat_id: int, document: dict):
    """Handle uploaded document - process and return report immediately"""
    file_name = document.get('file_name', 'file')
    file_id = document['file_id']

    # Check file type
    if not file_name.endswith(('.xlsx', '.csv', '.pdf')):
        send_message(chat_id, "אנא שלח קובץ xlsx, csv או pdf")
        return

    send_message(chat_id, f"מעבד את {file_name}...")

    try:
        # Download file
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, file_name)
            download_file(file_id, file_path)

            # Process file
            file_ext = Path(file_path).suffix.lower()

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
                    send_message(chat_id, "לא הצלחתי לזהות את פורמט הקובץ")
                    return
            elif file_ext == '.csv':
                for encoding in ['utf-8', 'windows-1255', 'iso-8859-8']:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                send_message(chat_id, "פורמט לא נתמך")
                return

            # Generate PDF
            output_path = os.path.join(temp_dir, 'bank_report.pdf')

            generator = BankReportGenerator(file_path, output_path)
            generator.df = df
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
                f"הדוח שלך מוכן!\n\n"
                f"הכנסות: {generator.total_income:,.0f} ש\"ח\n"
                f"הוצאות: {generator.total_expenses:,.0f} ש\"ח\n"
                f"מאזן: {generator.balance:,.0f} ש\"ח"
            )
            send_document(chat_id, output_path, 'bank_report.pdf', caption)

    except Exception as e:
        send_message(chat_id, f"שגיאה בעיבוד הקובץ: {str(e)}")


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
    elif document:
        handle_document(chat_id, document)
    else:
        send_message(chat_id, "שלח קובץ xlsx או pdf, או הקלד /help לעזרה")


if __name__ == '__main__':
    main()
