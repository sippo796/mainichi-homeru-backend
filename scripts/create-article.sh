#!/bin/bash

# 記事作成Lambda（mcp_orchestrator）を呼び出して新しい記事を生成するスクリプト

set -e

# 設定
LAMBDA_FUNCTION_PREFIX="mainichi-homeru-prod-mcp-orchestrator"
PROD_BUCKET="mainichi-homeru-prod-articles-902275209296"

echo "📝 記事作成スクリプトを開始します..."

# AWS認証チェック
check_aws_auth() {
    echo "🔐 AWS認証状況をチェック中..."
    
    if ! command -v aws &> /dev/null; then
        echo "❌ AWS CLIがインストールされていません"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        echo "❌ AWS認証が必要です。'aws configure' を実行してください。"
        exit 1
    fi
    
    echo "✅ AWS認証確認済み"
}

# Lambda関数名を検索
find_lambda_function() {
    echo "🔍 記事作成Lambda関数を検索中..."
    
    FUNCTION_NAME=$(aws lambda list-functions --query "Functions[?contains(FunctionName, '$LAMBDA_FUNCTION_PREFIX')].FunctionName" --output text | head -1)
    
    if [ -z "$FUNCTION_NAME" ]; then
        echo "❌ 記事作成Lambda関数が見つかりません"
        exit 1
    fi
    
    echo "✅ Lambda関数を発見: $FUNCTION_NAME"
}

# 記事作成Lambda関数を実行
invoke_article_creation() {
    echo "🚀 記事作成Lambda関数を実行中..."
    
    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --invocation-type Event \
        --payload '{}' \
        /tmp/response.json > /dev/null
    
    echo "✅ 記事作成Lambda関数を実行しました"
    echo "⏳ 記事生成には1-2分程度かかります"
}

# 記事作成の完了を確認
check_article_creation() {
    echo "⏳ 記事作成の完了を待機中..."
    
    local max_attempts=30
    local attempt=1
    local today=$(date '+%Y-%m-%d')
    
    while [ $attempt -le $max_attempts ]; do
        echo "🔍 確認中... ($attempt/$max_attempts)"
        
        if aws s3 ls "s3://$PROD_BUCKET/articles/$today.md" &>/dev/null; then
            echo "🎉 記事作成が完了しました！"
            echo "📄 作成された記事: $today.md"
            
            echo ""
            echo "📖 記事プレビュー:"
            echo "=================="
            aws s3 cp "s3://$PROD_BUCKET/articles/$today.md" - | head -10
            echo "=================="
            return 0
        fi
        
        sleep 5
        ((attempt++))
    done
    
    echo "⚠️  記事作成の完了確認がタイムアウトしました"
    return 1
}

# メイン処理
main() {
    echo "🎯 目的: 新しいベイスターズ記事を自動生成します"
    echo ""
    
    check_aws_auth
    find_lambda_function
    invoke_article_creation
    check_article_creation
    
    echo ""
    echo "🎉 記事作成完了！"
    echo "💡 フロントエンドで確認してください"
}

main "$@"