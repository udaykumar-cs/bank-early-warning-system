import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is not set. Add it to your .env file.")
    
    # Use SQLite instead of PostgreSQL (no server needed)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///bank_ews.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    CRISIS_THRESHOLD = 0.5
    RARE_EVENT_THRESHOLD = 0.85
    STRESS_PREVALENCE_THRESHOLD = 0.15
    RATE_LIMIT = 100
    MAX_BATCH_SIZE = 50
    LOG_LEVEL = 'INFO'
    
    # Update these paths to match YOUR system
    MODEL_CRISIS_PATH = r"D:\Bank_EWS_Project\models\bank_stress_early_warning.pkl"
    MODEL_RARE_PATH = r"D:\Bank_EWS_Project\models\bank_stress_rare_event.pkl"
    SCALER_PATH = r"D:\Bank_EWS_Project\models\scaler.pkl"
    
    FEATURE_COLUMNS = [
        'crar_total', 'npa_ratio', 'total_provisions', 'net_profit',
        'interest_income', 'interest_expense', 'operating_expense',
        'credit_growth', 'repo_rate', 'inflation'
    ]