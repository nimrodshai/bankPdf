#!/usr/bin/env python3
"""
Bank/Credit Card Statement PDF Report Generator
Processes Israeli bank CSV/XLSX files and generates PDF reports with summaries and charts.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import re
try:
    import matplotlib.pyplot as plt
    import matplotlib
    from matplotlib import font_manager
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from bidi.algorithm import get_display
import os
import sys
import argparse
from pathlib import Path
import calendar


def rtl(text):
    """Convert Hebrew text to RTL display order."""
    if text is None:
        return ''
    text = str(text)
    # Only apply bidi algorithm to text that contains Hebrew characters
    if any('\u0590' <= c <= '\u05FF' for c in text):
        return get_display(text)
    return text

# Register Hebrew font for PDF
HEBREW_FONT_NAME = 'HebrewFont'

def setup_hebrew_fonts():
    """Register Hebrew-compatible fonts for PDF generation."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # List of possible font paths (bundled font first, then system fonts)
    font_paths = [
        os.path.join(script_dir, 'fonts', 'Arial.ttf'),  # Bundled Arial font
        os.path.join(script_dir, 'fonts', 'NotoSansHebrew-Regular.ttf'),  # Bundled Noto font
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',  # macOS
        '/System/Library/Fonts/ArialHB.ttc',  # macOS
        '/Library/Fonts/Arial Unicode.ttf',  # macOS
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(HEBREW_FONT_NAME, font_path))
                print(f"Using font: {font_path}")
                return HEBREW_FONT_NAME
            except Exception as e:
                print(f"Failed to load font {font_path}: {e}")
                continue

    print("Warning: No Hebrew font found, using Helvetica")
    return 'Helvetica'  # Fallback (won't support Hebrew well)

# Initialize Hebrew font
HEBREW_FONT = setup_hebrew_fonts()

# Hebrew months mapping
HEBREW_MONTHS = {
    1: 'ינואר', 2: 'פברואר', 3: 'מרץ', 4: 'אפריל',
    5: 'מאי', 6: 'יוני', 7: 'יולי', 8: 'אוגוסט',
    9: 'ספטמבר', 10: 'אוקטובר', 11: 'נובמבר', 12: 'דצמבר'
}

# Category definitions for automatic categorization
CATEGORY_KEYWORDS = {
    'כ. אשראי': ['ישראכרט', 'ויזה', 'visa', 'מאסטרקארד', 'mastercard', 'לאומי קארד', 'כאל', 'max', 'מקס'],
    'מזומן': ['משיכה', 'משיכת מזומן', 'בנקט', 'כספומט', 'atm'],
    'ה. קבע': ['הו"ק', 'הוק', 'הוראת קבע', 'standing', 'מנותבת'],
    'מים': ['מים', 'מקורות', 'תאגיד מים', 'מי רעננה', 'מי '],
    'חשמל': ['חשמל', 'חח"י', 'חברת חשמל', 'iec'],
    'גז': ['גז', 'פזגז', 'סופרגז', 'אמישראגז'],
    'ארנונה': ['ארנונה', 'עירייה', 'עיריית', 'מועצה'],
    'ביטוח': ['ביטוח', 'מגדל', 'הראל', 'כלל', 'הפניקס', 'מנורה', 'איילון'],
    'תקשורת': ['yes', 'הוט', 'סלקום', 'פרטנר', 'בזק', 'פלאפון', 'גולן'],
    'שיקים': ['שיק', 'צק', 'check', 'cheque'],
    'עמלות': ['עמלה', 'דמי', 'מפעולות'],
    'אחר': [],
}


def detect_statement_format(df_raw):
    """Detect the type of Israeli bank/credit card statement format."""
    for idx in range(min(50, len(df_raw))):
        row = df_raw.iloc[idx]
        row_str = ' '.join([str(x) for x in row.values if pd.notna(x)])
        # Credit card statement format
        if 'שם בית עסק' in row_str or 'סכום חיוב' in row_str:
            return 'credit_card', idx
        # Bank account statement format
        if 'תנועות בחשבון' in row_str or ('חובה' in row_str and 'זכות' in row_str):
            return 'bank_account', idx
    return 'unknown', -1


def parse_bank_account_statement(file_path):
    """Parse Israeli bank account statement format (תנועות בחשבון)."""
    df_raw = pd.read_excel(file_path, header=None)

    # Find the header row with column names
    header_row = -1
    for idx in range(len(df_raw)):
        row = df_raw.iloc[idx]
        row_str = ' '.join([str(x) for x in row.values if pd.notna(x)])
        if 'חובה' in row_str and 'זכות' in row_str:
            header_row = idx
            break

    if header_row == -1:
        raise ValueError("Could not find header row in bank account statement")

    print(f"Found header at row {header_row}")

    # Get headers
    headers = df_raw.iloc[header_row].tolist()

    # Find column indices
    col_indices = {}
    for i, h in enumerate(headers):
        h_str = str(h).strip() if pd.notna(h) else ''
        if h_str == 'תאריך':
            col_indices['date'] = i
        elif 'הפעולה' in h_str or h_str == 'פעולה':
            col_indices['description'] = i  # This is the main description column
        elif 'פרטים' in h_str:
            col_indices['details'] = i  # Additional details
        elif 'חובה' in h_str:
            col_indices['debit'] = i
        elif 'זכות' in h_str:
            col_indices['credit'] = i
        elif 'יתרה' in h_str:
            col_indices['balance'] = i
        elif 'אסמכתא' in h_str:
            col_indices['reference'] = i
        elif 'עבור' in h_str:
            col_indices['for'] = i  # "עבור" column with additional info

    print(f"Column indices: {col_indices}")

    # Extract transactions
    transactions = []
    for idx in range(header_row + 1, len(df_raw)):
        row = df_raw.iloc[idx]

        # Skip empty rows
        if row.isna().all():
            continue

        # Get date
        date_val = row.iloc[col_indices.get('date', 0)] if 'date' in col_indices else None
        if pd.isna(date_val):
            continue

        transaction = {}

        # Parse date
        try:
            transaction['date'] = pd.to_datetime(date_val, errors='coerce')
        except:
            continue

        # Get description - combine multiple columns for full description
        desc_parts = []
        if 'description' in col_indices:
            desc = row.iloc[col_indices['description']]
            if pd.notna(desc) and str(desc).strip():
                desc_parts.append(str(desc).strip())
        if 'details' in col_indices:
            details = row.iloc[col_indices['details']]
            if pd.notna(details) and str(details).strip():
                desc_parts.append(str(details).strip())
        if 'for' in col_indices:
            for_info = row.iloc[col_indices['for']]
            if pd.notna(for_info) and str(for_info).strip():
                desc_parts.append(str(for_info).strip())

        transaction['description'] = ' - '.join(desc_parts) if desc_parts else ''

        # Get debit (expense) and credit (income)
        debit = 0
        credit = 0
        if 'debit' in col_indices:
            debit_val = row.iloc[col_indices['debit']]
            if pd.notna(debit_val) and debit_val != '':
                try:
                    debit = float(debit_val)
                except:
                    debit = 0

        if 'credit' in col_indices:
            credit_val = row.iloc[col_indices['credit']]
            if pd.notna(credit_val) and credit_val != '':
                try:
                    credit = float(credit_val)
                except:
                    credit = 0

        # Amount: positive for income (credit), negative for expense (debit)
        transaction['amount'] = credit - debit
        transaction['is_income'] = credit > 0

        if transaction['amount'] != 0:
            transactions.append(transaction)

    df = pd.DataFrame(transactions)
    print(f"Extracted {len(df)} transactions")
    return df


def parse_credit_card_statement(file_path):
    """Parse Israeli credit card statement format."""
    df_raw = pd.read_excel(file_path, header=None)

    # Find the transaction section header
    header_row = -1
    for idx in range(len(df_raw)):
        row = df_raw.iloc[idx]
        row_values = [str(x).strip() for x in row.values if pd.notna(x)]
        if 'שם בית עסק' in row_values or any('שם בית עסק' in str(x) for x in row_values):
            header_row = idx
            break

    if header_row == -1:
        raise ValueError("Could not find transaction header in credit card statement")

    # Get the header row
    headers = df_raw.iloc[header_row].tolist()

    # Find relevant column indices
    col_indices = {}
    for i, h in enumerate(headers):
        h_str = str(h).strip() if pd.notna(h) else ''
        if 'שם כרטיס' in h_str:
            col_indices['card'] = i
        elif 'תאריך' in h_str and 'חיוב' not in h_str:
            col_indices['date'] = i
        elif 'שם בית עסק' in h_str:
            col_indices['description'] = i
        elif 'סכום חיוב' in h_str or 'סכום קנייה' in h_str:
            if 'amount' not in col_indices:  # Take first amount column
                col_indices['amount'] = i
        elif 'תאור סוג עסקת' in h_str or 'סוג עסקה' in h_str:
            col_indices['transaction_type'] = i

    # If we didn't find amount, look for it specifically
    if 'amount' not in col_indices:
        for i, h in enumerate(headers):
            h_str = str(h).strip() if pd.notna(h) else ''
            if 'סכום' in h_str:
                col_indices['amount'] = i
                break

    print(f"Found header at row {header_row}")
    print(f"Column indices: {col_indices}")

    # Extract transactions (rows after header until next section or end)
    transactions = []
    for idx in range(header_row + 1, len(df_raw)):
        row = df_raw.iloc[idx]

        # Check if this is a new section header or empty
        first_val = row.iloc[0] if pd.notna(row.iloc[0]) else ''
        if isinstance(first_val, str) and ('מספר חשבון' in first_val or 'פירוט' in first_val or 'רכישות' in first_val):
            # Skip section headers, but continue looking for more transactions
            continue

        # Check if we have valid data
        if 'amount' in col_indices and 'description' in col_indices:
            amount_val = row.iloc[col_indices['amount']] if col_indices['amount'] < len(row) else None
            desc_val = row.iloc[col_indices['description']] if col_indices['description'] < len(row) else None

            # Skip if no valid amount
            if pd.isna(amount_val) or amount_val == '' or amount_val == 0:
                continue

            # Skip header rows that appear again
            if isinstance(desc_val, str) and 'שם בית עסק' in desc_val:
                continue

            try:
                amount = float(amount_val)
            except (ValueError, TypeError):
                continue

            transaction = {
                'amount': amount,
                'description': str(desc_val) if pd.notna(desc_val) else '',
            }

            # Get date if available
            if 'date' in col_indices:
                date_val = row.iloc[col_indices['date']]
                if pd.notna(date_val):
                    transaction['date'] = pd.to_datetime(date_val, errors='coerce')

            # Get transaction type if available
            if 'transaction_type' in col_indices:
                type_val = row.iloc[col_indices['transaction_type']]
                transaction['transaction_type'] = str(type_val) if pd.notna(type_val) else ''

            # Get card number if available
            if 'card' in col_indices:
                card_val = row.iloc[col_indices['card']]
                transaction['card'] = str(card_val) if pd.notna(card_val) else ''

            transactions.append(transaction)

    df = pd.DataFrame(transactions)
    print(f"Extracted {len(df)} transactions")
    return df


def parse_pdf_bank_statement(file_path):
    """Parse Bank Hapoalim PDF statement (תנועות בחשבון)."""
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber is required to parse PDF files. Install with: pip install pdfplumber")

    transactions = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            # Extract tables from the page
            tables = page.extract_tables()

            for table in tables:
                if not table:
                    continue

                for row in table:
                    if not row or len(row) < 4:
                        continue

                    # Skip header rows
                    row_str = ' '.join([str(cell) for cell in row if cell])
                    if 'תאריך' in row_str and 'פעולה' in row_str:
                        continue
                    if 'יתרה' in row_str and 'זכות' in row_str and 'חובה' in row_str:
                        continue

                    # Try to parse the row - Bank Hapoalim format:
                    # Date | Description | Debit | Credit | Balance
                    try:
                        # Find date pattern (DD/MM/YYYY)
                        date_str = None
                        description = None
                        debit = 0
                        credit = 0

                        for cell in row:
                            if not cell:
                                continue
                            cell_str = str(cell).strip()

                            # Check for date pattern
                            date_match = re.match(r'(\d{1,2}/\d{1,2}/\d{4})', cell_str)
                            if date_match and not date_str:
                                date_str = date_match.group(1)
                                continue

                            # Check for amount with ₪ symbol (balance column - skip)
                            if '₪' in cell_str:
                                continue

                            # Check for numeric amount (debit/credit)
                            # Remove commas and try to parse as float
                            clean_num = cell_str.replace(',', '').replace(' ', '')
                            try:
                                amount = float(clean_num)
                                if amount > 0:
                                    if debit == 0 and credit == 0:
                                        # First number could be debit or credit
                                        # We'll determine based on position later
                                        debit = amount
                                    elif debit > 0 and credit == 0:
                                        credit = amount
                                continue
                            except ValueError:
                                pass

                            # Otherwise it's probably the description
                            if cell_str and not date_str:
                                continue
                            if cell_str and len(cell_str) > 2:
                                description = cell_str

                        # If we found a valid date and either debit or credit
                        if date_str and (debit > 0 or credit > 0):
                            # Parse date
                            try:
                                date = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce')
                            except:
                                continue

                            if pd.isna(date):
                                continue

                            # In Bank Hapoalim PDFs, the column order is:
                            # תאריך | פעולה | חובה | זכות | יתרה
                            # If only one amount found, determine if debit or credit
                            # by checking the description
                            if credit == 0 and debit > 0:
                                # Check if it's income based on description
                                if description:
                                    desc_lower = description.lower()
                                    if any(word in description for word in ['משכורת', 'קצבת', 'זכות', 'העברה לזכות']):
                                        credit = debit
                                        debit = 0

                            transaction = {
                                'date': date,
                                'description': description or '',
                                'amount': credit - debit,  # Positive for income, negative for expense
                                'is_income': credit > 0
                            }

                            if transaction['amount'] != 0:
                                transactions.append(transaction)

                    except Exception as e:
                        continue

    # If table extraction didn't work well, try text extraction
    if len(transactions) == 0:
        transactions = parse_pdf_bank_statement_text(file_path)

    df = pd.DataFrame(transactions)
    print(f"Extracted {len(df)} transactions from PDF")
    return df


def parse_pdf_bank_statement_text(file_path):
    """Parse Bank Hapoalim PDF using text extraction.

    The PDF text format (RTL, so appears reversed):
    ₪Balance Amount Description Date
    e.g.: ₪6,623.99 806.95 טקנבמ הכישמ 30/11/2025

    Uses balance-based detection: if balance went up it's income, if down it's expense.
    """
    raw_transactions = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')

            for line in lines:
                # Skip header lines and empty lines
                if not line.strip():
                    continue
                if 'הפוקת' in line or 'ךיראת' in line or 'הרתי' in line:
                    continue
                if '##' in line or line.strip().isdigit():
                    continue

                # Look for lines with date pattern (DD/MM/YYYY at the end for RTL)
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
                if not date_match:
                    continue

                date_str = date_match.group(1)

                # Find all numbers in the line (amounts)
                # Format: ₪Balance Amount Description Date
                numbers = re.findall(r'[\d,]+\.\d{2}', line)

                if len(numbers) < 2:
                    continue

                # First number with ₪ is balance
                balance_match = re.search(r'₪([\d,]+\.\d{2})', line)
                if not balance_match:
                    continue

                balance_str = balance_match.group(1)
                balance = float(balance_str.replace(',', ''))

                # Find amounts that are not the balance
                amounts = [n for n in numbers if n != balance_str]

                if not amounts:
                    continue

                # Get the transaction amount (absolute value for now)
                amount = float(amounts[0].replace(',', ''))

                # Extract description - remove date, numbers, and ₪ symbol
                description = line
                description = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', description)
                description = re.sub(r'₪[\d,]+\.\d{2}', '', description)
                description = re.sub(r'[\d,]+\.\d{2}', '', description)
                description = description.replace('##', '').strip()
                description = re.sub(r'\s+', ' ', description).strip()

                # The PDF text is already in visual order (reversed),
                # apply bidi to get logical order for proper display
                description = get_display(description)

                # Parse date
                try:
                    date = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce')
                except:
                    continue

                if pd.isna(date):
                    continue

                raw_transactions.append({
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'balance': balance
                })

    # Sort by date and then by balance to get correct order
    raw_transactions.sort(key=lambda x: (x['date'], x['balance']))

    # Now determine income/expense based on balance changes
    transactions = []
    prev_balance = None

    for txn in raw_transactions:
        amount = txn['amount']
        balance = txn['balance']

        if prev_balance is not None:
            # Calculate expected balance change
            balance_diff = balance - prev_balance

            # If balance went up, it's income (positive)
            # If balance went down, it's expense (negative)
            if balance_diff > 0:
                # Income - balance increased
                amount = abs(amount)
                is_income = True
            else:
                # Expense - balance decreased
                amount = -abs(amount)
                is_income = False
        else:
            # First transaction - use the amount and balance to guess
            # If balance > amount, likely this was income that increased balance
            # This is a fallback, not perfect
            is_income = False
            amount = -abs(amount)

        prev_balance = balance

        transaction = {
            'date': txn['date'],
            'description': txn['description'],
            'amount': amount,
            'is_income': is_income
        }

        if transaction['amount'] != 0:
            transactions.append(transaction)

    return transactions


class BankReportGenerator:
    def __init__(self, input_file: str, output_file: str = None):
        self.input_file = input_file
        self.output_file = output_file or self._generate_output_filename()
        self.df = None
        self.summary_data = None
        self.month_name = None
        self.year = None

    def _generate_output_filename(self) -> str:
        """Generate output filename based on input file."""
        base = Path(self.input_file).stem
        output_dir = Path(self.input_file).parent
        return str(output_dir / f"{base}_report.pdf")

    def load_data(self):
        """Load data from CSV, XLSX, or PDF file."""
        file_ext = Path(self.input_file).suffix.lower()

        if file_ext == '.pdf':
            # Parse PDF bank statement
            print("Detected PDF bank statement")
            self.df = parse_pdf_bank_statement(self.input_file)
            self.statement_type = 'bank_account'
        elif file_ext == '.xlsx':
            # Detect statement format
            df_raw = pd.read_excel(self.input_file, header=None)
            stmt_format, _ = detect_statement_format(df_raw)

            if stmt_format == 'credit_card':
                print("Detected credit card statement format")
                self.df = parse_credit_card_statement(self.input_file)
                self.statement_type = 'credit_card'
            elif stmt_format == 'bank_account':
                print("Detected bank account statement format")
                self.df = parse_bank_account_statement(self.input_file)
                self.statement_type = 'bank_account'
            else:
                print("Unknown format, trying default parsing")
                self.df = pd.read_excel(self.input_file)
                self.statement_type = 'unknown'
        elif file_ext == '.csv':
            # Try different encodings common for Israeli banks
            for encoding in ['utf-8', 'windows-1255', 'iso-8859-8']:
                try:
                    self.df = pd.read_csv(self.input_file, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")

        print(f"Loaded {len(self.df)} transactions")
        print(f"Columns: {list(self.df.columns)}")
        return self

    def normalize_columns(self):
        """Normalize column names to standard format."""
        # Common column name mappings for Israeli banks
        column_mappings = {
            'תאריך': 'date',
            'תאריך ערך': 'date',
            'תאריך פעולה': 'date',
            'סכום': 'amount',
            'סכום חיוב': 'amount',
            'זכות': 'credit',
            'חובה': 'debit',
            'תיאור': 'description',
            'פרטים': 'description',
            'שם בית עסק': 'description',
            'אסמכתא': 'reference',
            'יתרה': 'balance',
        }

        # Rename columns based on mapping
        new_columns = {}
        for col in self.df.columns:
            col_str = str(col).strip()
            for heb, eng in column_mappings.items():
                if heb in col_str:
                    new_columns[col] = eng
                    break

        if new_columns:
            self.df = self.df.rename(columns=new_columns)

        # Handle credit/debit columns if separate
        if 'credit' in self.df.columns and 'debit' in self.df.columns:
            self.df['amount'] = self.df['credit'].fillna(0) - self.df['debit'].fillna(0)

        return self

    def parse_dates(self):
        """Parse date column and extract month/year."""
        if 'date' in self.df.columns:
            self.df['date'] = pd.to_datetime(self.df['date'], dayfirst=True, errors='coerce')

        # Extract month and year from most common date
        if 'date' in self.df.columns:
            valid_dates = self.df['date'].dropna()
            if len(valid_dates) > 0:
                most_common_month = valid_dates.dt.month.mode().iloc[0]
                most_common_year = valid_dates.dt.year.mode().iloc[0]
                self.month_name = HEBREW_MONTHS.get(most_common_month, str(most_common_month))
                self.year = most_common_year
                self.df['day'] = self.df['date'].dt.day
                self.df['month'] = self.df['date'].dt.month

        return self

    def categorize_transactions(self):
        """Categorize transactions based on description."""
        def get_category(row):
            description = row.get('description', '')
            transaction_type = row.get('transaction_type', '')

            if pd.isna(description):
                description = ''
            if pd.isna(transaction_type):
                transaction_type = ''

            desc_lower = str(description).lower()
            type_lower = str(transaction_type).lower()

            # Check transaction type first
            if 'הוראת קבע' in type_lower:
                return 'ה. קבע'

            # Then check description keywords
            for category, keywords in CATEGORY_KEYWORDS.items():
                for keyword in keywords:
                    if keyword.lower() in desc_lower:
                        return category
            return 'אחר'

        self.df['category'] = self.df.apply(get_category, axis=1)
        return self

    def calculate_summary(self):
        """Calculate monthly summary by category."""
        # Handle different statement types
        if hasattr(self, 'statement_type') and self.statement_type == 'bank_account':
            # Bank account: positive = income, negative = expense
            self.total_income = self.df[self.df['amount'] > 0]['amount'].sum()
            self.total_expenses = abs(self.df[self.df['amount'] < 0]['amount'].sum())
            self.balance = self.total_income - self.total_expenses

            # Summary by category for expenses only
            expenses_df = self.df[self.df['amount'] < 0].copy()
            self.summary_by_category = expenses_df.groupby('category').agg({
                'amount': lambda x: x.abs().sum(),
                'date': 'count'
            }).reset_index()
        else:
            # Credit card: all amounts are expenses (positive values)
            self.total_expenses = self.df['amount'].abs().sum()
            self.total_income = 0
            self.balance = -self.total_expenses

            # Summary by category
            self.summary_by_category = self.df.groupby('category').agg({
                'amount': lambda x: x.abs().sum(),
                'date': 'count'
            }).reset_index()

        self.summary_by_category.columns = ['category', 'total', 'count']
        self.summary_by_category = self.summary_by_category.sort_values('total', ascending=False)

        return self

    def create_charts(self):
        """Create charts for the report."""
        if not HAS_MATPLOTLIB:
            self.chart_path = None
            return self

        # Set up matplotlib for Hebrew support
        script_dir = os.path.dirname(os.path.abspath(__file__))
        hebrew_font = None
        font_paths = [
            os.path.join(script_dir, 'fonts', 'Arial.ttf'),  # Bundled Arial font (full charset)
            os.path.join(script_dir, 'fonts', 'NotoSansHebrew-Regular.ttf'),  # Bundled Noto font
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            '/System/Library/Fonts/ArialHB.ttc',
            '/Library/Fonts/Arial Unicode.ttf',
        ]
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    hebrew_font = font_manager.FontProperties(fname=font_path)
                    break
                except:
                    continue

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # === Chart 1: Income vs Expenses Bar Chart ===
        labels = [rtl('הכנסות'), rtl('הוצאות')]
        values = [self.total_income, self.total_expenses]
        bar_colors = ['#2ecc71', '#e74c3c']  # Green for income, Red for expenses

        bars = axes[0].bar(labels, values, color=bar_colors, width=0.5)

        # Add value labels on bars
        for bar, val in zip(bars, values):
            axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 200,
                        f'₪{val:,.0f}', ha='center', fontsize=12, fontweight='bold')

        axes[0].set_ylabel(rtl('סכום (₪)'), fontsize=12,
                          fontproperties=hebrew_font if hebrew_font else None)
        axes[0].set_title(rtl('הכנסות מול הוצאות'), fontsize=14, fontweight='bold',
                         fontproperties=hebrew_font if hebrew_font else None)

        # Add balance annotation
        balance_text = f'{rtl("מאזן")}: ₪{self.balance:,.0f}'
        balance_color = '#2ecc71' if self.balance >= 0 else '#e74c3c'
        axes[0].text(0.5, 0.95, balance_text, transform=axes[0].transAxes,
                    fontsize=14, fontweight='bold', ha='center', va='top',
                    color=balance_color,
                    fontproperties=hebrew_font if hebrew_font else None)

        if hebrew_font:
            for label in axes[0].get_xticklabels():
                label.set_fontproperties(hebrew_font)

        # === Chart 2: Expenses by Category Pie Chart ===
        category_totals = self.summary_by_category[self.summary_by_category['total'] > 0]

        if len(category_totals) > 0:
            # Limit to top 8 categories
            if len(category_totals) > 8:
                top_cats = category_totals.head(7)
                other_total = category_totals.iloc[7:]['total'].sum()
                other_row = pd.DataFrame({'category': ['אחר (שאר)'], 'total': [other_total], 'count': [0]})
                category_totals = pd.concat([top_cats, other_row], ignore_index=True)

            rtl_labels = [rtl(cat) for cat in category_totals['category'].values]

            colors_pie = plt.cm.Set3(np.linspace(0, 1, len(category_totals)))
            wedges, texts, autotexts = axes[1].pie(
                category_totals['total'].values,
                labels=rtl_labels,
                autopct='%1.1f%%',
                startangle=90,
                colors=colors_pie
            )
            if hebrew_font:
                for text in texts:
                    text.set_fontproperties(hebrew_font)
            axes[1].set_title(rtl('התפלגות הוצאות לפי קטגוריה'), fontsize=14, fontweight='bold',
                            fontproperties=hebrew_font if hebrew_font else None)

        plt.tight_layout()

        # Save chart
        self.chart_path = '/tmp/bank_charts.png'
        plt.savefig(self.chart_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        return self

    def generate_pdf(self):
        """Generate the PDF report."""
        doc = SimpleDocTemplate(
            self.output_file,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        styles = getSampleStyleSheet()

        # Create custom styles with Hebrew font
        title_style = ParagraphStyle(
            'HebrewTitle',
            parent=styles['Heading1'],
            fontName=HEBREW_FONT,
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=20
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontName=HEBREW_FONT,
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=10
        )

        elements = []

        # Title
        title = rtl(f"{self.month_name} {self.year}")
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 15))

        # === INCOMES SECTION ===
        elements.append(Paragraph(rtl("הכנסות"), subtitle_style))
        elements.append(Spacer(1, 5))

        # Income table: Date | Amount | Description
        income_data = [[rtl('תיאור'), rtl('סכום'), rtl('תאריך')]]

        income_df = self.df[self.df['amount'] > 0].copy()
        for _, row in income_df.iterrows():
            date_str = f"{row['date'].day}/{row['date'].month}" if pd.notna(row.get('date')) else ''
            desc = str(row.get('description', ''))[:25]
            income_data.append([
                rtl(desc),
                f"₪{row['amount']:,.0f}",
                date_str
            ])

        # Total income row
        income_data.append([
            rtl('סה"כ הכנסות'),
            f"₪{self.total_income:,.0f}",
            ''
        ])

        income_table = Table(income_data, colWidths=[8*cm, 4*cm, 2.5*cm])
        income_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), HEBREW_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C6EFCE')),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            # Total row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#A9D08E')),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
        ]))
        elements.append(income_table)
        elements.append(Spacer(1, 25))

        # === EXPENSES SECTION ===
        elements.append(Paragraph(rtl("הוצאות"), subtitle_style))
        elements.append(Spacer(1, 5))

        # Expense table: Date | Description | Category | Amount
        expense_data = [[rtl('קטגוריה'), rtl('תיאור'), rtl('סכום'), rtl('תאריך')]]

        expense_df = self.df[self.df['amount'] < 0].copy()
        expense_df = expense_df.sort_values('date', ascending=False)

        # Show each transaction individually
        for _, row in expense_df.iterrows():
            date_str = f"{row['date'].day}/{row['date'].month}" if pd.notna(row.get('date')) else ''
            category = row.get('category', '')
            amount = abs(row['amount'])
            desc = str(row.get('description', ''))[:25]

            expense_data.append([
                rtl(category),
                rtl(desc),
                f"₪{amount:,.0f}",
                date_str
            ])

        # Total expenses row
        expense_data.append([
            rtl('סה"כ הוצאות'),
            '',
            f"₪{self.total_expenses:,.0f}",
            ''
        ])

        expense_table = Table(expense_data, colWidths=[4*cm, 6*cm, 3*cm, 2.5*cm])
        expense_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), HEBREW_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FFC7CE')),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            # Total row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FF6B6B')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
        ]))
        elements.append(expense_table)
        elements.append(Spacer(1, 30))

        # === BALANCE SECTION ===
        balance_data = [
            [rtl('הכנסות'), f"₪{self.total_income:,.0f}"],
            [rtl('הוצאות'), f"-₪{self.total_expenses:,.0f}"],
            [rtl('מאזן'), f"₪{self.balance:,.0f}"],
        ]

        balance_table = Table(balance_data, colWidths=[6*cm, 4*cm])

        # Determine balance color
        if self.balance >= 0:
            balance_bg = colors.HexColor('#C6EFCE')  # Green
        else:
            balance_bg = colors.HexColor('#FFC7CE')  # Red

        balance_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), HEBREW_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            # Income row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C6EFCE')),
            # Expense row
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFC7CE')),
            # Balance row
            ('BACKGROUND', (0, 2), (-1, 2), balance_bg),
            ('FONTSIZE', (0, 2), (-1, 2), 14),
        ]))
        elements.append(balance_table)
        elements.append(Spacer(1, 30))

        # Add charts (if matplotlib is available)
        if self.chart_path and os.path.exists(self.chart_path):
            elements.append(Paragraph(rtl("גרפים"), subtitle_style))
            elements.append(Spacer(1, 10))
            elements.append(Image(self.chart_path, width=17*cm, height=7.5*cm))

        # Build PDF
        doc.build(elements)
        print(f"PDF report generated: {self.output_file}")

        return self

    def process(self):
        """Run the full processing pipeline."""
        return (self
                .load_data()
                .normalize_columns()
                .parse_dates()
                .categorize_transactions()
                .calculate_summary()
                .create_charts()
                .generate_pdf())


class YearlyReportGenerator:
    """Generate yearly report with monthly savings/loss chart."""

    def __init__(self, output_file: str = None, year: int = None):
        self.output_file = output_file or '/tmp/yearly_report.pdf'
        self.df = None
        self.year = year
        self.monthly_data = None

    def set_data(self, df):
        """Set the transaction dataframe."""
        self.df = df
        return self

    def normalize_columns(self):
        """Normalize column names to standard format."""
        column_mappings = {
            'תאריך': 'date',
            'תאריך ערך': 'date',
            'תאריך פעולה': 'date',
            'סכום': 'amount',
            'סכום חיוב': 'amount',
            'זכות': 'credit',
            'חובה': 'debit',
            'תיאור': 'description',
            'פרטים': 'description',
            'שם בית עסק': 'description',
        }

        new_columns = {}
        for col in self.df.columns:
            col_str = str(col).strip()
            for heb, eng in column_mappings.items():
                if heb in col_str:
                    new_columns[col] = eng
                    break

        if new_columns:
            self.df = self.df.rename(columns=new_columns)

        if 'credit' in self.df.columns and 'debit' in self.df.columns:
            self.df['amount'] = self.df['credit'].fillna(0) - self.df['debit'].fillna(0)

        return self

    def parse_dates(self):
        """Parse date column."""
        if 'date' in self.df.columns:
            self.df['date'] = pd.to_datetime(self.df['date'], dayfirst=True, errors='coerce')
            self.df = self.df.dropna(subset=['date'])
            self.df['month'] = self.df['date'].dt.month
            self.df['year'] = self.df['date'].dt.year

        # Determine the year from data if not specified
        if self.year is None and 'year' in self.df.columns:
            self.year = self.df['year'].mode().iloc[0] if len(self.df) > 0 else datetime.now().year

        return self

    def calculate_monthly_summary(self):
        """Calculate monthly savings (income - expenses) for each month."""
        monthly_data = []

        for month in range(1, 13):
            # Get the last day of the month
            _, last_day = calendar.monthrange(self.year, month)

            # Filter transactions for this month (1st to last day)
            start_date = pd.Timestamp(year=self.year, month=month, day=1)
            end_date = pd.Timestamp(year=self.year, month=month, day=last_day, hour=23, minute=59, second=59)

            month_df = self.df[
                (self.df['date'] >= start_date) &
                (self.df['date'] <= end_date)
            ]

            if len(month_df) > 0:
                income = month_df[month_df['amount'] > 0]['amount'].sum()
                expenses = abs(month_df[month_df['amount'] < 0]['amount'].sum())
            else:
                income = 0
                expenses = 0

            savings = income - expenses

            monthly_data.append({
                'month': month,
                'month_name': HEBREW_MONTHS[month],
                'income': income,
                'expenses': expenses,
                'savings': savings,
                'transaction_count': len(month_df)
            })

        self.monthly_data = pd.DataFrame(monthly_data)
        return self

    def create_yearly_chart(self):
        """Create bar chart showing monthly savings/loss."""
        if not HAS_MATPLOTLIB:
            self.chart_path = None
            return self

        # Set up Hebrew font
        script_dir = os.path.dirname(os.path.abspath(__file__))
        hebrew_font = None
        font_paths = [
            os.path.join(script_dir, 'fonts', 'Arial.ttf'),
            os.path.join(script_dir, 'fonts', 'NotoSansHebrew-Regular.ttf'),
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            '/System/Library/Fonts/ArialHB.ttc',
        ]
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    hebrew_font = font_manager.FontProperties(fname=font_path)
                    break
                except:
                    continue

        fig, ax = plt.subplots(figsize=(14, 7))

        months = [rtl(name) for name in self.monthly_data['month_name']]
        savings = self.monthly_data['savings'].values

        # Color bars based on positive/negative
        colors = ['#2ecc71' if s >= 0 else '#e74c3c' for s in savings]

        bars = ax.bar(months, savings, color=colors, width=0.7, edgecolor='black', linewidth=0.5)

        # Add value labels on bars
        for bar, val in zip(bars, savings):
            y_pos = bar.get_height()
            offset = 200 if val >= 0 else -400
            va = 'bottom' if val >= 0 else 'top'
            ax.text(bar.get_x() + bar.get_width()/2, y_pos + offset,
                    f'₪{val:,.0f}', ha='center', va=va, fontsize=9, fontweight='bold')

        # Add horizontal line at 0
        ax.axhline(y=0, color='black', linestyle='-', linewidth=1)

        # Labels and title
        ax.set_ylabel(rtl('חיסכון/הפסד (₪)'), fontsize=12,
                     fontproperties=hebrew_font if hebrew_font else None)
        ax.set_title(rtl(f'חיסכון חודשי - {self.year}'), fontsize=16, fontweight='bold',
                    fontproperties=hebrew_font if hebrew_font else None)

        # Set Hebrew font for x-axis labels
        if hebrew_font:
            for label in ax.get_xticklabels():
                label.set_fontproperties(hebrew_font)

        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha='right')

        # Add total summary
        total_savings = savings.sum()
        savings_text = f'{rtl("סה״כ שנתי")}: ₪{total_savings:,.0f}'
        color = '#2ecc71' if total_savings >= 0 else '#e74c3c'
        ax.text(0.98, 0.95, savings_text, transform=ax.transAxes,
               fontsize=14, fontweight='bold', ha='right', va='top', color=color,
               fontproperties=hebrew_font if hebrew_font else None,
               bbox=dict(boxstyle='round', facecolor='white', edgecolor=color, alpha=0.8))

        plt.tight_layout()

        self.chart_path = '/tmp/yearly_chart.png'
        plt.savefig(self.chart_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        return self

    def generate_pdf(self):
        """Generate the yearly PDF report."""
        doc = SimpleDocTemplate(
            self.output_file,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'HebrewTitle',
            parent=styles['Heading1'],
            fontName=HEBREW_FONT,
            fontSize=20,
            alignment=TA_CENTER,
            spaceAfter=20
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontName=HEBREW_FONT,
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=10
        )

        elements = []

        # Title
        elements.append(Paragraph(rtl(f'דוח שנתי - {self.year}'), title_style))
        elements.append(Spacer(1, 20))

        # Add chart
        if self.chart_path and os.path.exists(self.chart_path):
            elements.append(Image(self.chart_path, width=17*cm, height=8.5*cm))
            elements.append(Spacer(1, 25))

        # Monthly summary table
        elements.append(Paragraph(rtl('סיכום חודשי'), subtitle_style))
        elements.append(Spacer(1, 10))

        table_data = [[rtl('חיסכון/הפסד'), rtl('הוצאות'), rtl('הכנסות'), rtl('חודש')]]

        for _, row in self.monthly_data.iterrows():
            savings_str = f'₪{row["savings"]:,.0f}'
            table_data.append([
                savings_str,
                f'₪{row["expenses"]:,.0f}',
                f'₪{row["income"]:,.0f}',
                rtl(row['month_name'])
            ])

        # Add yearly totals
        total_income = self.monthly_data['income'].sum()
        total_expenses = self.monthly_data['expenses'].sum()
        total_savings = self.monthly_data['savings'].sum()

        table_data.append([
            f'₪{total_savings:,.0f}',
            f'₪{total_expenses:,.0f}',
            f'₪{total_income:,.0f}',
            rtl('סה"כ שנתי')
        ])

        table = Table(table_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])

        # Build style list with conditional formatting for savings column
        style_commands = [
            ('FONTNAME', (0, 0), (-1, -1), HEBREW_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            # Total row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#D9E2F3')),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
        ]

        # Color savings cells based on positive/negative
        for i, row in enumerate(self.monthly_data.itertuples(), start=1):
            if row.savings >= 0:
                style_commands.append(('BACKGROUND', (0, i), (0, i), colors.HexColor('#C6EFCE')))
            else:
                style_commands.append(('BACKGROUND', (0, i), (0, i), colors.HexColor('#FFC7CE')))

        # Color total savings
        if total_savings >= 0:
            style_commands.append(('BACKGROUND', (0, -1), (0, -1), colors.HexColor('#A9D08E')))
        else:
            style_commands.append(('BACKGROUND', (0, -1), (0, -1), colors.HexColor('#FF6B6B')))
            style_commands.append(('TEXTCOLOR', (0, -1), (0, -1), colors.white))

        table.setStyle(TableStyle(style_commands))
        elements.append(table)

        # Build PDF
        doc.build(elements)
        print(f"Yearly PDF report generated: {self.output_file}")

        return self

    def process(self):
        """Run the full yearly report pipeline."""
        return (self
                .normalize_columns()
                .parse_dates()
                .calculate_monthly_summary()
                .create_yearly_chart()
                .generate_pdf())


def main():
    parser = argparse.ArgumentParser(
        description='Generate PDF report from bank/credit card statement CSV/XLSX'
    )
    parser.add_argument(
        'input_files',
        nargs='+',
        help='Path to bank statement file(s) (CSV or XLSX). Can specify multiple files or a directory.'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output PDF filename (default: bank_report.pdf in first file\'s directory)'
    )

    args = parser.parse_args()

    # Collect all files to process
    files_to_process = []
    for input_path in args.input_files:
        if os.path.isdir(input_path):
            # If directory, find all xlsx and csv files
            import glob
            for ext in ['*.xlsx', '*.csv', '*.pdf']:
                files_to_process.extend(glob.glob(os.path.join(input_path, ext)))
        elif os.path.exists(input_path):
            files_to_process.append(input_path)
        else:
            print(f"Warning: File not found: {input_path}")

    if not files_to_process:
        print("Error: No valid files found to process")
        sys.exit(1)

    print(f"Found {len(files_to_process)} file(s) to merge...")

    # Load and merge data from all files
    all_dataframes = []
    for input_file in files_to_process:
        print(f"Loading: {input_file}")
        try:
            file_ext = Path(input_file).suffix.lower()
            if file_ext == '.pdf':
                df = parse_pdf_bank_statement(input_file)
            elif file_ext == '.xlsx':
                df_raw = pd.read_excel(input_file, header=None)
                stmt_format, _ = detect_statement_format(df_raw)

                if stmt_format == 'credit_card':
                    df = parse_credit_card_statement(input_file)
                elif stmt_format == 'bank_account':
                    df = parse_bank_account_statement(input_file)
                else:
                    print(f"  Unknown format, skipping: {input_file}")
                    continue
            elif file_ext == '.csv':
                for encoding in ['utf-8', 'windows-1255', 'iso-8859-8']:
                    try:
                        df = pd.read_csv(input_file, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                print(f"  Unsupported format, skipping: {input_file}")
                continue

            all_dataframes.append(df)
            print(f"  Loaded {len(df)} transactions")
        except Exception as e:
            print(f"  Error loading {input_file}: {e}")

    if not all_dataframes:
        print("Error: No data loaded from any files")
        sys.exit(1)

    # Merge all dataframes
    merged_df = pd.concat(all_dataframes, ignore_index=True)
    print(f"\nTotal transactions merged: {len(merged_df)}")

    # Determine output path
    if args.output:
        output_file = args.output
    else:
        first_file_dir = Path(files_to_process[0]).parent
        output_file = str(first_file_dir / "bank_report.pdf")

    # Create generator with merged data
    generator = BankReportGenerator(files_to_process[0], output_file)
    generator.df = merged_df
    generator.statement_type = 'bank_account'

    # Run the rest of the pipeline (skip load_data since we already have data)
    (generator
     .normalize_columns()
     .parse_dates()
     .categorize_transactions()
     .calculate_summary()
     .create_charts()
     .generate_pdf())

    print(f"\nDone! Created merged report: {output_file}")


if __name__ == '__main__':
    main()
