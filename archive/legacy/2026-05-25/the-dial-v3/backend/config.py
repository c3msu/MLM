"""
The Dial - Configuration
FRED API and other settings
"""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "macro_data.db"

# FRED API Configuration
# Get your API key from: https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# FRED Series IDs for each module
FRED_SERIES = {
    "liquidity": [
        {"id": "WALCL", "name": "美联储资产负债表", "unit": "B", "frequency": "w"},
        {"id": "RESBALNS", "name": "银行准备金", "unit": "B", "frequency": "w"},
        {"id": "WTREGEN", "name": "TGA账户", "unit": "B", "frequency": "d"},
        {"id": "RRPONTSYD", "name": "ON RRP", "unit": "B", "frequency": "d"},
        {"id": "M2SL", "name": "M2货币供应", "unit": "B", "frequency": "m"},
    ],
    "funding": [
        {"id": "SOFR", "name": "SOFR利率", "unit": "%", "frequency": "d"},
        {"id": "EFFR", "name": "有效联邦基金利率", "unit": "%", "frequency": "d"},
        {"id": "TEDRATE", "name": "TED利差", "unit": "%", "frequency": "d"},
    ],
    "treasury": [
        {"id": "DGS2", "name": "2年国债收益率", "unit": "%", "frequency": "d"},
        {"id": "DGS10", "name": "10年国债收益率", "unit": "%", "frequency": "d"},
        {"id": "DGS30", "name": "30年国债收益率", "unit": "%", "frequency": "d"},
        {"id": "T10Y2Y", "name": "期限利差", "unit": "%", "frequency": "d"},
    ],
    "rates": [
        {"id": "FEDFUNDS", "name": "联邦基金利率", "unit": "%", "frequency": "m"},
        {"id": "MPRIME", "name": "Prime利率", "unit": "%", "frequency": "m"},
    ],
    "credit": [
        {"id": "BAMLC0A0CM", "name": "投资级利差", "unit": "bp", "frequency": "d"},
        {"id": "BAMLH0A0HYM2", "name": "高收益利差", "unit": "bp", "frequency": "d"},
    ],
    "risk": [
        {"id": "VIXCLS", "name": "VIX指数", "unit": "index", "frequency": "d"},
        {"id": "DTWEXBGS", "name": "美元指数", "unit": "index", "frequency": "d"},
    ],
    "external": [
        {"id": "DEXUSEU", "name": "欧元汇率", "unit": "rate", "frequency": "d"},
    ],
}

# Data update settings
UPDATE_SETTINGS = {
    "auto_update": False,  # Set to True to enable automatic updates
    "update_time": "06:00",  # Daily update time
    "retention_days": 1825,  # Keep 5 years of data
}

# Scoring weights for each module
MODULE_WEIGHTS = {
    "liquidity": 0.20,
    "funding": 0.15,
    "treasury": 0.15,
    "rates": 0.15,
    "credit": 0.15,
    "risk": 0.10,
    "external": 0.10,
}


def get_fred_api_key():
    """Get FRED API key from environment or config file"""
    # First check environment variable
    api_key = os.getenv("FRED_API_KEY", "")
    
    # Then check config file
    if not api_key:
        config_file = BASE_DIR / ".fred_api_key"
        if config_file.exists():
            api_key = config_file.read_text().strip()
    
    return api_key


def save_fred_api_key(api_key: str):
    """Save FRED API key to config file"""
    config_file = BASE_DIR / ".fred_api_key"
    config_file.write_text(api_key.strip())
    # Set restrictive permissions (owner read/write only)
    os.chmod(config_file, 0o600)
    print(f"API key saved to {config_file}")


def check_api_key():
    """Check if FRED API key is configured"""
    api_key = get_fred_api_key()
    if not api_key:
        print("⚠️  FRED API key not found!")
        print("Please set FRED_API_KEY environment variable or run:")
        print("  python config.py --save-key YOUR_API_KEY")
        return False
    print(f"✅ FRED API key configured (length: {len(api_key)})")
    return True


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 2 and sys.argv[1] == "--save-key":
        save_fred_api_key(sys.argv[2])
    else:
        check_api_key()
