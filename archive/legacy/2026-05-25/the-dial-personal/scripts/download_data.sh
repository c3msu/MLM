#!/bin/bash
# The Dial - FRED数据下载脚本

DATA_DIR="data"
mkdir -p $DATA_DIR

echo "=========================================="
echo "The Dial - FRED数据下载"
echo "=========================================="
echo ""

# 核心指标列表
INDICATORS=(
    "WALCL:liquidity:美联储资产负债表"
    "RESBALNS:liquidity:银行准备金"
    "WTREGEN:liquidity:TGA账户"
    "RRPONTSYD:liquidity:ON_RRP"
    "M2SL:liquidity:M2货币供应"
    "SOFR:funding:SOFR利率"
    "EFFR:funding:有效联邦基金利率"
    "TEDRATE:funding:TED利差"
    "DGS2:treasury:2年国债"
    "DGS10:treasury:10年国债"
    "DGS30:treasury:30年国债"
    "T10Y2Y:treasury:期限利差"
    "FEDFUNDS:rates:联邦基金利率"
    "MPRIME:rates:Prime利率"
    "BAMLC0A0CM:credit:投资级利差"
    "BAMLH0A0HYM2:credit:高收益利差"
    "VIXCLS:risk:VIX指数"
    "DXY:risk:美元指数"
    "DEXUSEU:external:欧元汇率"
    "GACDISA:external:全球PMI"
)

for item in "${INDICATORS[@]}"; do
    IFS=':' read -r code module name <<< "$item"
    echo -n "下载 $code ($name)... "
    
    curl -s "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$code" \
        -o "$DATA_DIR/$code.csv"
    
    if [ $? -eq 0 ] && [ -s "$DATA_DIR/$code.csv" ]; then
        echo "✅"
        sleep 0.3
    else
        echo "❌"
        rm -f "$DATA_DIR/$code.csv"
    fi
done

echo ""
echo "✅ 下载完成！"
echo "下一步: python scripts/import_data.py"
