#!/bin/bash

# NewsAPIの複数検索クエリを一括テストするスクリプト

set -e

echo "📰 NewsAPI 複数クエリテストスクリプト"
echo "==============================================="

# APIキーを取得（環境変数があればそれを使用、なければSSMから取得）
if [ -n "$NEWS_API_KEY" ]; then
    echo "🔐 環境変数からNewsAPI キーを使用: ${NEWS_API_KEY:0:10}..."
    API_KEY="$NEWS_API_KEY"
else
    echo "🔐 SSMからNewsAPI キーを取得中..."
    API_KEY=$(aws ssm get-parameter \
        --name "/mainichi-homeru/openai-api-key" \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text 2>/dev/null)

    if [ -z "$API_KEY" ] || [ "$API_KEY" == "None" ]; then
        echo "❌ NewsAPI キーが取得できませんでした"
        exit 1
    fi
    
    echo "✅ SSMからAPIキー取得完了: ${API_KEY:0:10}..."
fi
echo ""

# 日付設定（過去7日間）
TODAY=$(date '+%Y-%m-%d')
WEEK_AGO=$(date -d '7 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-7d '+%Y-%m-%d')

echo "📅 検索期間: $WEEK_AGO ～ $TODAY"
echo ""

# 検索クエリパターン
declare -a QUERIES=(
    "横浜DeNA OR ベイスターズ"
    "DeNA BayStars OR Yokohama DeNA"
    "横浜 野球 OR ベイスターズ OR ハマスタ"
    "三浦大輔 OR 牧秀悟 OR 佐野恵太"
    "横浜ベイスターズ OR バイスターズ"
    "DeNA OR 横浜スタジアム OR 横浜 プロ野球"
    "BayStars OR 横浜DeNA OR 横浜 championship"
)

declare -a NAMES=(
    "基本クエリ1"
    "英語重視" 
    "野球関連"
    "選手名"
    "ベイスターズ表記"
    "広範囲"
    "英語+横浜"
)

echo "🔍 ${#QUERIES[@]} パターンの検索クエリをテスト中..."
echo ""

BEST_QUERY=""
BEST_COUNT=0
BEST_INDEX=0

for i in "${!QUERIES[@]}"; do
    QUERY="${QUERIES[$i]}"
    NAME="${NAMES[$i]}"
    
    echo "[$((i+1))/${#QUERIES[@]}] 🔎 $NAME: $QUERY"
    
    # URLエンコード
    ENCODED_QUERY=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")
    URL="https://newsapi.org/v2/everything?q=${ENCODED_QUERY}&from=${WEEK_AGO}&to=${TODAY}&sortBy=publishedAt&pageSize=20&apiKey=${API_KEY}"
    
    # APIを実行
    RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "$URL")
    HTTP_STATUS=$(echo "$RESPONSE" | tail -n1 | cut -d: -f2)
    RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_STATUS" == "200" ]; then
        # 記事数を抽出
        TOTAL_RESULTS=$(echo "$RESPONSE_BODY" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('totalResults', 0))" 2>/dev/null || echo "0")
        ARTICLES_COUNT=$(echo "$RESPONSE_BODY" | python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data.get('articles', [])))" 2>/dev/null || echo "0")
        
        echo "   📊 結果: $TOTAL_RESULTS 件総数, $ARTICLES_COUNT 件取得"
        
        # ベストクエリを更新
        if [ "$TOTAL_RESULTS" -gt "$BEST_COUNT" ]; then
            BEST_COUNT="$TOTAL_RESULTS"
            BEST_QUERY="$QUERY"
            BEST_INDEX=$i
        fi
        
        # 記事があれば最初の3件のタイトルを表示
        if [ "$ARTICLES_COUNT" -gt "0" ]; then
            echo "   📰 記事例:"
            echo "$RESPONSE_BODY" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for i, article in enumerate(data.get('articles', [])[:3], 1):
    title = article.get('title', 'タイトルなし')[:80]
    print(f'     {i}. {title}...')
" 2>/dev/null || echo "     記事の解析に失敗"
        fi
    else
        echo "   ❌ エラー: HTTP $HTTP_STATUS"
    fi
    
    echo ""
done

echo "🏆 ベスト検索クエリ:"
echo "   クエリ: $BEST_QUERY"
echo "   結果数: $BEST_COUNT 件"
echo "   パターン: ${NAMES[$BEST_INDEX]}"
echo ""

echo "💡 Lambda関数での推奨設定:"
echo "   search_query = urllib.parse.quote(\"$BEST_QUERY\")"
echo ""

echo "🎉 テスト完了！"