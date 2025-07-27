#!/bin/bash

# NewsAPIを直接テストするスクリプト

set -e

echo "📰 NewsAPIテストスクリプト"
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
        echo "💡 ヒント: 環境変数 NEWS_API_KEY を設定するか、SSMパラメータを確認してください"
        echo "   例: export NEWS_API_KEY=\"your-api-key-here\""
        exit 1
    fi
    
    echo "✅ SSMからAPIキー取得完了: ${API_KEY:0:10}..."
    echo "💡 次回は高速化のため環境変数を設定できます: export NEWS_API_KEY=\"${API_KEY:0:10}...\""
fi
echo ""

# 日付設定（過去7日間）
TODAY=$(date '+%Y-%m-%d')
WEEK_AGO=$(date -d '7 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-7d '+%Y-%m-%d')

echo "📅 検索期間: $WEEK_AGO ～ $TODAY"
echo ""

# 検索クエリ（複数パターンをテスト）
echo "🔍 検索クエリのテストを開始..."
echo ""

# パターン1: 基本的なクエリ
SEARCH_QUERY_1="Yokohama DeNA BayStars OR ベイスターズ OR 横浜DeNA"
# パターン2: より具体的なクエリ
SEARCH_QUERY_2="横浜DeNA OR 横浜ベイスターズ OR DeNA OR バイスターズ OR 三浦大輔 OR 牧秀悟"
# パターン3: 英語重視
SEARCH_QUERY_3="DeNA BayStars OR Yokohama DeNA OR BayStars OR 横浜"
# パターン4: 野球関連も含む
SEARCH_QUERY_4="横浜 野球 OR DeNA 野球 OR ベイスターズ OR ハマスタ"
# パターン5: GPTおすすめ
SEARCH_QUERY_5="横浜DeNAベイスターズ"


# デフォルトは最も広範囲なクエリ
SEARCH_QUERY="$SEARCH_QUERY_5"

echo "📋 使用する検索クエリ:"
echo "  1. $SEARCH_QUERY_1"
echo "  2. $SEARCH_QUERY_2" 
echo "  3. $SEARCH_QUERY_3"
echo "  4. $SEARCH_QUERY_4"
echo "  4. $SEARCH_QUERY_5 (使用中)"
ENCODED_QUERY=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$SEARCH_QUERY'))")

# NewsAPI URL構築
URL="https://newsapi.org/v2/everything?q=${ENCODED_QUERY}&from=${WEEK_AGO}&to=${TODAY}&sortBy=publishedAt&pageSize=20&apiKey=${API_KEY}"

echo "🔍 検索クエリ: $SEARCH_QUERY"
echo "🌐 リクエストURL:"
echo "${URL//$API_KEY/***API_KEY***}"
echo ""

# APIを実行
echo "🚀 NewsAPIを呼び出し中..."
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "$URL")

# ステータスコードを抽出
HTTP_STATUS=$(echo "$RESPONSE" | tail -n1 | cut -d: -f2)
RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')

echo "📊 HTTPステータス: $HTTP_STATUS"
echo ""

if [ "$HTTP_STATUS" == "200" ]; then
    echo "✅ APIリクエスト成功"
    echo ""
    
    # JSONを整形して表示
    echo "📄 レスポンス内容:"
    echo "-----------------------------------------------"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
    echo "-----------------------------------------------"
    echo ""
    
    # 記事数を抽出
    TOTAL_RESULTS=$(echo "$RESPONSE_BODY" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('totalResults', 0))" 2>/dev/null || echo "0")
    ARTICLES_COUNT=$(echo "$RESPONSE_BODY" | python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data.get('articles', [])))" 2>/dev/null || echo "0")
    
    echo "📈 検索結果:"
    echo "  - 総結果数: $TOTAL_RESULTS 件"
    echo "  - 取得記事数: $ARTICLES_COUNT 件"
    
    if [ "$ARTICLES_COUNT" -gt "0" ]; then
        echo ""
        echo "📰 記事タイトル一覧:"
        echo "$RESPONSE_BODY" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for i, article in enumerate(data.get('articles', [])[:5], 1):
    title = article.get('title', 'タイトルなし')
    published = article.get('publishedAt', '')
    print(f'{i}. {title}')
    if published:
        print(f'   発行日: {published}')
    print()
" 2>/dev/null || echo "記事の解析に失敗しました"
    else
        echo ""
        echo "⚠️  該当する記事が見つかりませんでした"
        echo ""
        echo "💡 検索のヒント:"
        echo "  - 検索期間を広げてみる"
        echo "  - 検索キーワードを変更してみる"
        echo "  - 言語フィルタを確認する"
    fi
    
else
    echo "❌ APIリクエスト失敗"
    echo ""
    echo "📄 エラーレスポンス:"
    echo "-----------------------------------------------"
    echo "$RESPONSE_BODY"
    echo "-----------------------------------------------"
fi

echo ""
echo "🎉 テスト完了！"