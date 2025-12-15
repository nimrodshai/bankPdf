"""
Configuration file for Bank Report Generator
Customize categories, column mappings, and appearance settings here.
"""

# Category definitions - add keywords to automatically categorize transactions
# Format: 'Category Name': ['keyword1', 'keyword2', ...]
CATEGORY_KEYWORDS = {
    # Credit cards
    'כ. אשראי': ['ויזה', 'visa', 'מאסטרקארד', 'mastercard', 'אשראי', 'ישראכרט',
                 'לאומי קארד', 'כאל', 'max', 'מקס'],

    # Standing orders
    'ה. קבע': ['הו"ק', 'הוק', 'הוראת קבע', 'standing order'],

    # Checks
    'שיקים': ['שיק', 'צק', 'check', 'cheque'],

    # Childcare
    'גן': ['גן', 'גנון', 'צהרון', 'מעון', 'משפחתון'],

    # Utilities
    'מים': ['מים', 'מקורות', 'תאגיד מים', 'מי '],
    'חשמל': ['חשמל', 'חח"י', 'חברת חשמל', 'iec'],
    'גז': ['גז', 'פזגז', 'סופרגז', 'אמישראגז'],
    'ארנונה': ['ארנונה', 'עירייה', 'עיריית', 'מועצה'],

    # Insurance
    'ביטוח': ['ביטוח', 'insurance', 'מגדל', 'הראל', 'כלל', 'הפניקס', 'מנורה', 'איילון'],

    # Income
    'משכורת': ['משכורת', 'שכר', 'salary', 'העברת שכר'],
    'הכנסה': ['הכנסה', 'העברה', 'זיכוי', 'החזר'],

    # Cash
    'מזומן': ['מזומן', 'משיכת', 'atm', 'כספומט', 'משיכה'],

    # Food & Groceries
    'מזון': ['סופר', 'שופרסל', 'רמי לוי', 'מגה', 'ויקטורי', 'יוחננוף', 'אושר עד'],

    # Transport
    'תחבורה': ['דלק', 'פז', 'דור אלון', 'סונול', 'רכב', 'חניה', 'רב קו', 'אוטובוס'],

    # Communication
    'תקשורת': ['סלקום', 'פרטנר', 'הוט', 'בזק', 'פלאפון', 'גולן', 'אינטרנט'],
}

# Hebrew months
HEBREW_MONTHS = {
    1: 'ינואר', 2: 'פברואר', 3: 'מרץ', 4: 'אפריל',
    5: 'מאי', 6: 'יוני', 7: 'יולי', 8: 'אוגוסט',
    9: 'ספטמבר', 10: 'אוקטובר', 11: 'נובמבר', 12: 'דצמבר'
}

# Column mappings for different Israeli banks
# The key is what appears in your bank file, value is the normalized name
COLUMN_MAPPINGS = {
    # Date columns
    'תאריך': 'date',
    'תאריך ערך': 'date',
    'תאריך פעולה': 'date',
    'תאריך עסקה': 'date',

    # Amount columns
    'סכום': 'amount',
    'סכום בש"ח': 'amount',
    'סכום העסקה': 'amount',
    'זכות': 'credit',
    'חובה': 'debit',

    # Description columns
    'תיאור': 'description',
    'פרטים': 'description',
    'תיאור הפעולה': 'description',
    'שם בית העסק': 'description',

    # Other columns
    'אסמכתא': 'reference',
    'יתרה': 'balance',
    'מספר כרטיס': 'card_number',
}

# PDF Appearance Settings
PDF_SETTINGS = {
    'page_size': 'A4',
    'margin_cm': 1.5,
    'title_font_size': 18,
    'table_font_size': 10,
    'chart_width_cm': 16,
    'chart_height_cm': 7,
}

# Chart colors
CHART_COLORS = {
    'income': '#2ecc71',  # Green
    'expenses': '#e74c3c',  # Red
    'balance_positive': '#3498db',  # Blue
    'balance_negative': '#e74c3c',  # Red
}

# Expense categories color palette for pie chart
EXPENSE_COLORS = [
    '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#e67e22', '#34495e', '#7f8c8d', '#c0392b',
    '#16a085', '#27ae60', '#2980b9', '#8e44ad', '#f1c40f'
]
