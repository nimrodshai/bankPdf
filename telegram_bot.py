#!/usr/bin/env python3
"""
Telegram Bot for Bank Report Generator
Receives xlsx files and returns PDF reports
"""

import os
import logging
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import our bank report generator
from bank_report import (
    BankReportGenerator,
    YearlyReportGenerator,
    detect_statement_format,
    parse_bank_account_statement,
    parse_credit_card_statement,
    parse_pdf_bank_statement
)
import pandas as pd

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

# Store uploaded files per user
user_files = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "שלום! אני בוט להפקת דוחות בנק 🏦\n\n"
        "פקודות:\n"
        "/start - התחל מחדש\n"
        "/help - עזרה\n"
        "/clear - נקה קבצים שהועלו\n"
        "/report - הפק דוח PDF חודשי\n"
        "/yearly - הפק דוח שנתי עם גרף חיסכון חודשי\n\n"
        "פשוט שלח לי קבצי xlsx או pdf מהבנק ואז הקלד /report או /yearly"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "📋 איך להשתמש:\n\n"
        "1. שלח קובץ xlsx או pdf אחד או יותר מהבנק\n"
        "2. הקלד /report לדוח חודשי או /yearly לדוח שנתי\n"
        "3. קבל PDF עם סיכום הכנסות והוצאות\n\n"
        "סוגי דוחות:\n"
        "/report - דוח חודשי עם פירוט עסקאות\n"
        "/yearly - דוח שנתי עם גרף חיסכון/הפסד לכל חודש\n\n"
        "פקודות נוספות:\n"
        "/clear - נקה את הקבצים שהועלו\n"
        "/status - כמה קבצים הועלו"
    )


async def clear_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command"""
    user_id = update.effective_user.id
    if user_id in user_files:
        # Clean up temp files
        for file_path in user_files[user_id]:
            try:
                os.remove(file_path)
            except:
                pass
        del user_files[user_id]
    await update.message.reply_text("✅ כל הקבצים נמחקו")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    count = len(user_files.get(user_id, []))
    await update.message.reply_text(f"📁 יש לך {count} קבצים ממתינים לעיבוד")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded documents"""
    user_id = update.effective_user.id
    document = update.message.document

    # Check if it's a supported file type
    if not document.file_name.endswith(('.xlsx', '.csv', '.pdf')):
        await update.message.reply_text("❌ אנא שלח קובץ xlsx, csv או pdf")
        return

    # Download the file
    file = await context.bot.get_file(document.file_id)

    # Create temp directory for user if needed
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, document.file_name)

    await file.download_to_drive(file_path)

    # Store file path for user
    if user_id not in user_files:
        user_files[user_id] = []
    user_files[user_id].append(file_path)

    count = len(user_files[user_id])
    await update.message.reply_text(
        f"✅ קובץ התקבל: {document.file_name}\n"
        f"📁 סה\"כ קבצים: {count}\n\n"
        f"שלח עוד קבצים או הקלד /report להפקת הדוח"
    )


async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /report command - generate PDF from uploaded files"""
    user_id = update.effective_user.id

    if user_id not in user_files or not user_files[user_id]:
        await update.message.reply_text("❌ לא נמצאו קבצים. שלח קבצי xlsx או pdf תחילה")
        return

    await update.message.reply_text("⏳ מעבד את הקבצים...")

    try:
        # Load and merge all files
        all_dataframes = []
        for file_path in user_files[user_id]:
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
                    continue
            elif file_ext == '.csv':
                for encoding in ['utf-8', 'windows-1255', 'iso-8859-8']:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                continue

            all_dataframes.append(df)

        if not all_dataframes:
            await update.message.reply_text("❌ לא הצלחתי לקרוא את הקבצים")
            return

        # Merge data
        merged_df = pd.concat(all_dataframes, ignore_index=True)

        # Generate PDF
        output_path = tempfile.mktemp(suffix='.pdf')

        generator = BankReportGenerator(user_files[user_id][0], output_path)
        generator.df = merged_df
        generator.statement_type = 'bank_account'

        (generator
         .normalize_columns()
         .parse_dates()
         .categorize_transactions()
         .calculate_summary()
         .create_charts()
         .generate_pdf())

        # Send PDF back to user
        await update.message.reply_document(
            document=open(output_path, 'rb'),
            filename='bank_report.pdf',
            caption=f"📊 הדוח שלך מוכן!\n\n"
                    f"הכנסות: ₪{generator.total_income:,.0f}\n"
                    f"הוצאות: ₪{generator.total_expenses:,.0f}\n"
                    f"מאזן: ₪{generator.balance:,.0f}"
        )

        # Clean up
        os.remove(output_path)
        for file_path in user_files[user_id]:
            try:
                os.remove(file_path)
            except:
                pass
        del user_files[user_id]

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        await update.message.reply_text(f"❌ שגיאה בהפקת הדוח: {str(e)}")


async def generate_yearly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /yearly command - generate yearly PDF with monthly savings chart"""
    user_id = update.effective_user.id

    if user_id not in user_files or not user_files[user_id]:
        await update.message.reply_text("❌ לא נמצאו קבצים. שלח קבצי xlsx או pdf תחילה")
        return

    await update.message.reply_text("⏳ מעבד את הקבצים לדוח שנתי...")

    try:
        # Load and merge all files
        all_dataframes = []
        for file_path in user_files[user_id]:
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
                    continue
            elif file_ext == '.csv':
                for encoding in ['utf-8', 'windows-1255', 'iso-8859-8']:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                continue

            all_dataframes.append(df)

        if not all_dataframes:
            await update.message.reply_text("❌ לא הצלחתי לקרוא את הקבצים")
            return

        # Merge data
        merged_df = pd.concat(all_dataframes, ignore_index=True)

        # Generate yearly PDF
        output_path = tempfile.mktemp(suffix='.pdf')

        generator = YearlyReportGenerator(output_file=output_path)
        generator.df = merged_df
        generator.process()

        # Calculate totals for caption
        total_income = generator.monthly_data['income'].sum()
        total_expenses = generator.monthly_data['expenses'].sum()
        total_savings = generator.monthly_data['savings'].sum()

        # Send PDF back to user
        await update.message.reply_document(
            document=open(output_path, 'rb'),
            filename=f'yearly_report_{generator.year}.pdf',
            caption=f"📊 הדוח השנתי שלך מוכן! ({generator.year})\n\n"
                    f"סה\"כ הכנסות: ₪{total_income:,.0f}\n"
                    f"סה\"כ הוצאות: ₪{total_expenses:,.0f}\n"
                    f"סה\"כ חיסכון: ₪{total_savings:,.0f}"
        )

        # Clean up
        os.remove(output_path)
        for file_path in user_files[user_id]:
            try:
                os.remove(file_path)
            except:
                pass
        del user_files[user_id]

    except Exception as e:
        logger.error(f"Error generating yearly report: {e}")
        await update.message.reply_text(f"❌ שגיאה בהפקת הדוח השנתי: {str(e)}")


def main():
    """Start the bot"""
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
        return

    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_files))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CommandHandler("yearly", generate_yearly_report))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Start polling
    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
