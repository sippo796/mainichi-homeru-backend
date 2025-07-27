#!/bin/bash

# Lambda関数のビルド&デプロイスクリプト

set -e

echo "🚀 Lambda関数のデプロイを開始します..."

# mcp_orchestratorのビルド&デプロイ
echo "📦 mcp_orchestrator をビルド中..."
cd lambdas/mcp_orchestrator

# 最新のapp.pyをbuildフォルダにコピー
echo "📋 app.py をbuildフォルダにコピー..."
cp app.py build/

echo "✅ ビルド完了"

# Terraformでプラン確認
echo "📋 Terraform planを実行中..."
cd ../../terraform
terraform plan

echo ""
echo "❓ 上記の変更を適用しますか？ (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "🚀 Terraform apply を実行中..."
    terraform apply -auto-approve
    
    echo ""
    echo "🎉 デプロイ完了！"
    echo "💡 テストするには: ../scripts/create-article.sh"
else
    echo "⏹️ デプロイをキャンセルしました"
fi