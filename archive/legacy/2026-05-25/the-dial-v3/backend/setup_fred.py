#!/usr/bin/env python3
"""
The Dial - FRED API Setup Tool
Interactive script to configure FRED API key
"""

import os
import sys
import getpass
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
from config import save_fred_api_key, get_fred_api_key, check_api_key, FRED_SERIES


def print_header():
    """Print welcome header"""
    print("=" * 60)
    print("  The Dial - FRED API 配置工具")
    print("=" * 60)
    print()


def print_menu():
    """Print main menu"""
    print("\n请选择操作:")
    print("  1. 输入FRED API Key")
    print("  2. 查看当前API Key状态")
    print("  3. 查看FRED指标列表")
    print("  4. 测试API连接")
    print("  5. 删除已保存的API Key")
    print("  0. 退出")
    print()


def input_api_key():
    """Input and save API key"""
    print("\n" + "-" * 60)
    print("获取FRED API Key的步骤:")
    print("  1. 访问 https://fred.stlouisfed.org/")
    print("  2. 点击右上角 'Register' 注册账户")
    print("  3. 登录后访问 https://fredaccount.stlouisfed.org/apikey")
    print("  4. 点击 'Request API Key' 并填写申请理由")
    print("  5. 复制生成的API Key")
    print("-" * 60)
    print()
    
    api_key = input("请输入您的FRED API Key: ").strip()
    
    if not api_key:
        print("❌ API Key不能为空")
        return False
    
    if len(api_key) < 20:
        print(f"⚠️  API Key长度较短 ({len(api_key)}字符)，请确认是否正确")
        confirm = input("是否继续保存? (y/n): ").strip().lower()
        if confirm != 'y':
            return False
    
    try:
        save_fred_api_key(api_key)
        print(f"✅ API Key已保存")
        
        # Verify
        saved_key = get_fred_api_key()
        if saved_key == api_key:
            print("✅ 验证成功")
            return True
        else:
            print("❌ 验证失败，保存的Key与输入不符")
            return False
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        return False


def show_api_status():
    """Show current API key status"""
    print("\n" + "-" * 60)
    print("当前API Key状态:")
    print("-" * 60)
    
    # Check environment variable
    env_key = os.getenv("FRED_API_KEY", "")
    if env_key:
        masked = env_key[:4] + "*" * (len(env_key) - 8) + env_key[-4:]
        print(f"  环境变量 FRED_API_KEY: {masked}")
    else:
        print("  环境变量 FRED_API_KEY: 未设置")
    
    # Check config file
    config_file = Path(__file__).parent / ".fred_api_key"
    if config_file.exists():
        file_key = config_file.read_text().strip()
        if file_key:
            masked = file_key[:4] + "*" * (len(file_key) - 8) + file_key[-4:]
            print(f"  配置文件 .fred_api_key: {masked}")
        else:
            print("  配置文件 .fred_api_key: 存在但为空")
    else:
        print("  配置文件 .fred_api_key: 不存在")
    
    # Check effective key
    effective_key = get_fred_api_key()
    if effective_key:
        print(f"\n  ✅ 有效API Key: 已配置 ({len(effective_key)}字符)")
    else:
        print(f"\n  ❌ 有效API Key: 未配置")
    
    print("-" * 60)


def show_series_list():
    """Show FRED series list"""
    print("\n" + "-" * 60)
    print("FRED指标列表 (共{}个)".format(sum(len(v) for v in FRED_SERIES.values())))
    print("-" * 60)
    
    module_names = {
        "liquidity": "流动性",
        "funding": "融资",
        "treasury": "国债",
        "rates": "利率",
        "credit": "信用",
        "risk": "风险",
        "external": "外部",
    }
    
    for module, indicators in FRED_SERIES.items():
        print(f"\n【{module_names.get(module, module)}】")
        for ind in indicators:
            print(f"  {ind['id']:12} - {ind['name']} ({ind['unit']}, {ind['frequency']})")
    
    print("\n" + "-" * 60)
    print("CSV下载链接:")
    print("  https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}")
    print("-" * 60)


def test_api_connection():
    """Test FRED API connection"""
    print("\n" + "-" * 60)
    print("测试FRED API连接...")
    print("-" * 60)
    
    api_key = get_fred_api_key()
    if not api_key:
        print("❌ 未配置API Key，请先设置")
        return
    
    try:
        import urllib.request
        import json
        
        # Test with GDP data
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id=GDPC1&api_key={api_key}&file_type=json&limit=1"
        
        print(f"  请求URL: {url[:60]}...")
        
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode())
            
            if 'observations' in data and len(data['observations']) > 0:
                obs = data['observations'][0]
                print(f"\n  ✅ API连接成功!")
                print(f"  示例数据: GDPC1 = {obs['value']} ({obs['date']})")
            else:
                print(f"\n  ⚠️  API返回空数据")
                print(f"  响应: {data}")
                
    except Exception as e:
        print(f"\n  ❌ API连接失败: {e}")
        print("\n  可能原因:")
        print("  - API Key错误")
        print("  - 网络连接问题")
        print("  - FRED服务暂时不可用")


def delete_api_key():
    """Delete saved API key"""
    print("\n" + "-" * 60)
    
    config_file = Path(__file__).parent / ".fred_api_key"
    
    if not config_file.exists():
        print("❌ 配置文件不存在")
        return
    
    confirm = input("确定要删除已保存的API Key吗? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        try:
            config_file.unlink()
            print("✅ API Key已删除")
        except Exception as e:
            print(f"❌ 删除失败: {e}")
    else:
        print("已取消")


def main():
    """Main function"""
    print_header()
    
    while True:
        print_menu()
        choice = input("请输入选项 (0-5): ").strip()
        
        if choice == '1':
            input_api_key()
        elif choice == '2':
            show_api_status()
        elif choice == '3':
            show_series_list()
        elif choice == '4':
            test_api_connection()
        elif choice == '5':
            delete_api_key()
        elif choice == '0':
            print("\n再见!")
            break
        else:
            print("\n❌ 无效选项，请重新输入")


if __name__ == "__main__":
    main()
