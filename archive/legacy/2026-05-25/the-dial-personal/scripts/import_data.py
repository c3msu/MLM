#!/usr/bin/env python3
"""
The Dial - FRED数据导入脚本
从CSV文件导入数据到SQLite数据库
"""

import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = 'macro_data.db'
DATA_DIR = Path('data')

# 47个宏观因子配置
INDICATORS = {
    'liquidity': [
        {'code': 'WALCL', 'name': '美联储资产负债表'},
        {'code': 'RESBALNS', 'name': '银行准备金'},
        {'code': 'WTREGEN', 'name': 'TGA账户'},
        {'code': 'RRPONTSYD', 'name': 'ON RRP'},
        {'code': 'M2SL', 'name': 'M2货币供应'},
    ],
    'funding': [
        {'code': 'SOFR', 'name': 'SOFR利率'},
        {'code': 'EFFR', 'name': '有效联邦基金利率'},
        {'code': 'TEDRATE', 'name': 'TED利差'},
    ],
    'treasury': [
        {'code': 'DGS2', 'name': '2年国债收益率'},
        {'code': 'DGS10', 'name': '10年国债收益率'},
        {'code': 'DGS30', 'name': '30年国债收益率'},
        {'code': 'T10Y2Y', 'name': '期限利差'},
    ],
    'rates': [
        {'code': 'FEDFUNDS', 'name': '联邦基金利率'},
        {'code': 'MPRIME', 'name': 'Prime利率'},
    ],
    'credit': [
        {'code': 'BAMLC0A0CM', 'name': '投资级利差'},
        {'code': 'BAMLH0A0HYM2', 'name': '高收益利差'},
    ],
    'risk': [
        {'code': 'VIXCLS', 'name': 'VIX指数'},
        {'code': 'DXY', 'name': '美元指数'},
    ],
    'external': [
        {'code': 'DEXUSEU', 'name': '欧元汇率'},
        {'code': 'GACDISA', 'name': '全球PMI'},
    ]
}

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS indicators (
            series_id TEXT,
            date TEXT,
            value REAL,
            module TEXT,
            name TEXT,
            PRIMARY KEY (series_id, date)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS module_scores (
            module TEXT,
            date TEXT,
            score REAL,
            PRIMARY KEY (module, date)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS overall_scores (
            date TEXT PRIMARY KEY,
            score REAL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成")

def import_csv(csv_file, series_id, module_name, indicator_name):
    """导入单个CSV文件"""
    try:
        df = pd.read_csv(csv_file)
        df.columns = [c.upper().strip() for c in df.columns]
        
        # 找到日期和数值列
        date_col = [c for c in df.columns if 'DATE' in c][0]
        value_col = [c for c in df.columns if c not in ['DATE']][0]
        
        df = df.rename(columns={date_col: 'date', value_col: 'value'})
        df['date'] = pd.to_datetime(df['date'])
        df['series_id'] = series_id
        df['module'] = module_name
        df['name'] = indicator_name
        
        conn = sqlite3.connect(DB_PATH)
        df[['series_id', 'date', 'value', 'module', 'name']].to_sql(
            'indicators', conn, if_exists='append', index=False
        )
        conn.commit()
        conn.close()
        
        print(f"✅ 导入 {series_id}: {len(df)} 条记录")
        return len(df)
    except Exception as e:
        print(f"❌ 导入失败 {series_id}: {e}")
        return 0

def main():
    print("=" * 60)
    print("The Dial - 数据导入工具")
    print("=" * 60)
    
    init_db()
    
    total = 0
    for module, indicators in INDICATORS.items():
        for ind in indicators:
            csv_file = DATA_DIR / f"{ind['code']}.csv"
            if csv_file.exists():
                count = import_csv(csv_file, ind['code'], module, ind['name'])
                total += count
            else:
                print(f"⚠️  跳过 {ind['code']}: 文件不存在")
    
    print(f"\n✅ 共导入 {total} 条记录")
    print("💡 提示: 从FRED下载CSV文件并保存到 data/ 目录")

if __name__ == '__main__':
    main()
