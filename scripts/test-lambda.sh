#!/bin/bash

# Lambda関数を直接実行してテストするスクリプト

set -e

echo "🧪 Lambda関数テストスクリプト"
echo "==============================================="

# Lambda関数名
FUNCTION_NAME="mainichi-homeru-prod-mcp-orchestrator"

echo "🎯 テスト対象: $FUNCTION_NAME"
echo ""

# Lambda関数を実行
echo "🚀 Lambda関数を実行中..."
RESULT=$(aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --payload '{}' \
    --cli-binary-format raw-in-base64-out \
    /tmp/lambda-response.json)

echo "✅ Lambda実行完了"
echo ""

# 実行結果を表示
echo "📊 実行結果:"
echo "$RESULT"
echo ""

# レスポンスファイルの内容を表示
if [ -f /tmp/lambda-response.json ]; then
    echo "📄 レスポンス内容 (全文):"
    echo "-----------------------------------------------"
    cat /tmp/lambda-response.json
    echo ""
    echo "-----------------------------------------------"
    echo ""
else
    echo "❌ レスポンスファイルが見つかりません"
fi

# CloudWatchログも表示
echo "📝 最新のCloudWatchログ (直近5分間):"
echo "==============================================="

# 最新のログストリームを取得
LOG_STREAM=$(aws logs describe-log-streams \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --order-by LastEventTime \
    --descending \
    --max-items 1 \
    --query 'logStreams[0].logStreamName' \
    --output text)

if [ "$LOG_STREAM" != "None" ] && [ -n "$LOG_STREAM" ]; then
    echo "📍 ログストリーム: $LOG_STREAM"
    echo ""
    
    # 過去5分間のログを取得
    START_TIME=$(($(date +%s) - 300))000
    
    aws logs get-log-events \
        --log-group-name "/aws/lambda/$FUNCTION_NAME" \
        --log-stream-name "$LOG_STREAM" \
        --start-time $START_TIME \
        --query 'events[*].message' \
        --output text
else
    echo "❌ ログストリームが見つかりません"
fi

echo ""
echo "🎉 テスト完了！"