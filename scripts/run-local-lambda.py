#!/usr/bin/env python3
"""
Lambda関数をローカルで実行するスクリプト
AWS環境変数とSSMパラメータを模擬して、mcp_orchestratorをローカル実行
"""

import os
import sys
import json
import asyncio
import boto3
import argparse
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
lambda_dir = Path(__file__).parent.parent / "lambdas" / "mcp_orchestrator"
build_dir = lambda_dir / "build"

# buildディレクトリが存在する場合はそちらを優先
if build_dir.exists():
    print(f"📦 buildディレクトリを使用: {build_dir}")
    sys.path.insert(0, str(build_dir))
else:
    print(f"📦 ソースディレクトリを使用: {lambda_dir}")
    sys.path.insert(0, str(lambda_dir))

def setup_environment(mock_hour=None):
    """環境変数を設定"""
    # AWS Lambda環境を模擬
    os.environ["AWS_REGION"] = "ap-northeast-1"
    os.environ["S3_BUCKET_NAME"] = "mainichi-homeru-prod-articles-902275209296"
    os.environ["CLAUDE_API_KEY_PARAMETER"] = "/mainichi-homeru/claude-api-key"
    os.environ["OPENAI_API_KEY_PARAMETER"] = "/mainichi-homeru/openai-api-key"
    
    # ローカル実行フラグ
    os.environ["LOCAL_EXECUTION"] = "true"
    
    # テスト用時間偽装の設定
    if mock_hour is not None:
        os.environ["MOCK_TIME_HOUR"] = str(mock_hour)
        print(f"🔧 環境変数を設定しました（{mock_hour}時でテスト実行）")
    else:
        # MOCK_TIME_HOUR環境変数をクリア
        if "MOCK_TIME_HOUR" in os.environ:
            del os.environ["MOCK_TIME_HOUR"]
        print("🔧 環境変数を設定しました（実時間で実行）")

def check_aws_credentials():
    """AWS認証情報を確認"""
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials is None:
            print("❌ AWS認証情報が見つかりません")
            print("💡 以下のコマンドで認証してください:")
            print("   aws configure")
            print("   または")
            print("   export AWS_PROFILE=your-profile")
            return False
        
        print(f"✅ AWS認証確認済み (Access Key: {credentials.access_key[:10]}...)")
        return True
    except Exception as e:
        print(f"❌ AWS認証エラー: {e}")
        return False

async def run_lambda_locally():
    """Lambda関数をローカルで実行"""
    try:
        print("📦 Lambda関数をインポート中...")
        
        # app.pyをインポート
        import app
        
        print("🚀 MCP Orchestratorを実行中...")
        
        # Lambda関数を実行（空のイベント）
        event = {}
        context = type('Context', (), {
            'function_name': 'mainichi-homeru-prod-mcp-orchestrator-local',
            'function_version': '$LATEST',
            'invoked_function_arn': 'arn:aws:lambda:ap-northeast-1:local:function:mcp-orchestrator',
            'memory_limit_in_mb': '128',
            'remaining_time_in_millis': lambda: 900000,  # 15分
            'log_group_name': '/aws/lambda/local-mcp-orchestrator',
            'log_stream_name': 'local-stream',
            'aws_request_id': 'local-request-id'
        })()
        
        # ローカル実行用：MCPOrchestratorを直接実行
        orchestrator = app.MCPOrchestrator()
        mcp_result = await orchestrator.execute_pipeline()
        
        # Lambda handler風のレスポンスを作成
        if mcp_result['status'] == 'success':
            # デバッグ: MCP結果を詳細チェック
            print(f"🔍 MCP結果デバッグ:")
            print(f"   ステータス: {mcp_result.get('status')}")
            print(f"   キー: {list(mcp_result.keys())}")
            print(f"   final_article の型: {type(mcp_result.get('final_article'))}")
            print(f"   final_article の長さ: {len(mcp_result.get('final_article', ''))}")
            if mcp_result.get('final_article'):
                print(f"   final_article の最初の100文字: {mcp_result['final_article'][:100]}...")
            else:
                print(f"   ❌ final_article が空またはNone!")
            
            # S3に記事を保存（時間帯別ファイル名）
            import pytz
            jst = pytz.timezone('Asia/Tokyo')
            
            # 時間偽装の確認
            mock_hour = os.environ.get('MOCK_TIME_HOUR')
            if mock_hour:
                mock_hour_int = int(mock_hour)
                time_suffix = "morning" if 6 <= mock_hour_int <= 12 else "evening"
                print(f"🕙 時間偽装使用: {mock_hour_int}時 -> {time_suffix}")
            else:
                now_jst = app.datetime.now(jst)
                time_suffix = "morning" if 6 <= now_jst.hour <= 12 else "evening"
            
            today = app.datetime.now().strftime('%Y-%m-%d')
            filename = f'{today}-{time_suffix}.md'
            bucket_name = os.environ['S3_BUCKET_NAME']
            
            print(f"📝 S3に記事を保存中: {bucket_name}/articles/{filename}")
            
            app.s3_client.put_object(
                Bucket=bucket_name,
                Key=f'articles/{filename}',
                Body=mcp_result['final_article'].encode('utf-8'),
                ContentType='text/markdown',
                Metadata={
                    'generated-by': 'mcp-orchestrator-local',
                    'quality-score': str(mcp_result['quality_score']),
                    'generation-time': mcp_result['pipeline_execution_time'],
                    'time-period': time_suffix
                }
            )
            
            result = {
                'statusCode': 200,
                'body': app.json.dumps({
                    'message': 'MCP article generated successfully (local)',
                    'date': today,
                    'quality_score': mcp_result['quality_score'],
                    'preview': mcp_result['final_article'][:200] + '...'
                }, ensure_ascii=False)
            }
        else:
            result = {
                'statusCode': 500,
                'body': app.json.dumps({
                    'error': 'MCP pipeline failed (local)',
                    'details': mcp_result.get('error', 'Unknown error')
                })
            }
        
        print("\n" + "="*50)
        print("🎉 実行完了！")
        print("="*50)
        print(f"📊 ステータスコード: {result.get('statusCode')}")
        
        # レスポンスボディをパース
        if 'body' in result:
            try:
                body = json.loads(result['body'])
                print(f"📝 メッセージ: {body.get('message', 'N/A')}")
                print(f"📅 日付: {body.get('date', 'N/A')}")
                print(f"⭐ 品質スコア: {body.get('quality_score', 'N/A')}")
                
                if 'preview' in body:
                    print(f"\n📰 記事内容（全文）:")
                    print("=" * 80)
                    # プレビューではなく、元の記事全文を表示
                    full_article = mcp_result.get('final_article', body.get('preview', ''))
                    print(f"🔍 デバッグ: full_article の長さ = {len(full_article)} 文字")
                    print(f"🔍 デバッグ: mcp_result キー = {list(mcp_result.keys())}")
                    if full_article:
                        print(full_article)
                    else:
                        print("❌ 記事内容が空です！")
                        print(f"🔍 mcp_result['final_article'] = {mcp_result.get('final_article', 'キーが存在しません')}")
                        print(f"🔍 body['preview'] = {body.get('preview', 'キーが存在しません')}")
                    print("=" * 80)
                    
                    # スクレイピング情報を読み込んで表示
                    print(f"\n📰 スクレイピング済み記事情報:")
                    print("=" * 60)
                    
                    # scraped_dataディレクトリから最新の記事情報を取得
                    scraped_data_dir = Path(__file__).parent / "scraped_data"
                    if scraped_data_dir.exists():
                        json_files = list(scraped_data_dir.glob("*.json"))
                        # seen_articles.jsonを除外
                        article_files = [f for f in json_files if f.name != "seen_articles.json"]
                        
                        if article_files:
                            # 最新のファイル順にソート
                            article_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                            
                            print(f"📊 スクレイピング済み記事: {len(article_files)} 件")
                            print("\n最新の記事（最大3件）:")
                            
                            for i, file_path in enumerate(article_files[:3], 1):
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        article_data = json.load(f)
                                    
                                    print(f"\n📄 記事 {i}:")
                                    print(f"   タイトル: {article_data.get('title', 'N/A')[:80]}...")
                                    print(f"   URL: {article_data.get('url', 'N/A')}")
                                    print(f"   スクレイピング日時: {article_data.get('scraped_at', 'N/A')}")
                                    print(f"   公開日: {article_data.get('publish_date', 'N/A')}")
                                    print(f"   ベイスターズ関連: {article_data.get('is_baystars_related', False)}")
                                    print(f"   検出キーワード: {', '.join(article_data.get('baystars_keywords_found', [])[:5])}")
                                    print(f"   要約: {article_data.get('summary', 'N/A')[:150]}...")
                                    
                                    # 画像情報
                                    images = article_data.get('images', [])
                                    if images:
                                        print(f"   画像: {len(images)} 枚")
                                    
                                except Exception as e:
                                    print(f"   ❌ 記事読み込みエラー ({file_path.name}): {e}")
                        else:
                            print("📭 スクレイピング済み記事が見つかりません")
                            print("💡 まず baystars-news-scraper.py を実行してください")
                    else:
                        print("📁 scraped_data ディレクトリが見つかりません")
                    
                    print("=" * 60)
                    
                    # 収集されたニュース情報も表示（phasesから取得）
                    print(f"\n🔍 MCP結果のキー: {list(mcp_result.keys())}")
                    
                    # phasesの中からdata_collectionのデータを取得
                    if 'phases' in mcp_result and 'data_collection' in mcp_result['phases']:
                        data_collection = mcp_result['phases']['data_collection']
                        collected_data = data_collection.get('data', {})
                        
                        print(f"\n📊 データ収集フェーズの結果:")
                        print(f"   ステータス: {data_collection.get('status', '不明')}")
                        print(f"   収集データキー: {list(collected_data.keys())}")
                        
                        # 各データカテゴリを詳細表示
                        if 'news_info' in collected_data:
                            news_info = collected_data['news_info']
                            print(f"\n📰 ニュース情報:")
                            print(f"   データタイプ: {type(news_info)}")
                            
                            if isinstance(news_info, dict):
                                print(f"   データソース: {news_info.get('data_source', '不明')}")
                                print(f"   ニュース件数: {len(news_info.get('recent_news', []))} 件")
                                print(f"   話題の選手: {', '.join(news_info.get('trending_players', []))}")
                                
                                if news_info.get('recent_news'):
                                    print(f"\n📰 取得されたニュース:")
                                    for i, news in enumerate(news_info['recent_news'][:5], 1):
                                        title = news.get('title', news.get('headline', 'タイトルなし'))
                                        source = news.get('source', '不明ソース')
                                        print(f"   [{i}] {title}")
                                        print(f"       🔗 ソース: {source}")
                                
                                if news_info.get('positive_highlights'):
                                    print(f"\n✨ 注目ポイント:")
                                    for highlight in news_info['positive_highlights'][:3]:
                                        print(f"   • {highlight}")
                            elif isinstance(news_info, list):
                                print(f"   ニュース件数: {len(news_info)} 件")
                                if news_info:
                                    print(f"\n📰 取得されたニュース:")
                                    for i, news in enumerate(news_info[:5], 1):
                                        if isinstance(news, dict):
                                            title = news.get('title', news.get('headline', 'タイトルなし'))
                                            source = news.get('source', '不明ソース')
                                            print(f"   [{i}] {title}")
                                            print(f"       🔗 ソース: {source}")
                                        else:
                                            print(f"   [{i}] {str(news)[:100]}...")
                            else:
                                print(f"   内容: {str(news_info)[:200]}...")
                        
                        if 'game_info' in collected_data:
                            game_info = collected_data['game_info']
                            print(f"\n⚾ 試合情報:")
                            print(f"   試合予定: {game_info.get('has_game_today', '不明')}")
                            if game_info.get('game_result'):
                                result = game_info['game_result']
                                print(f"   対戦相手: {result.get('opponent', '不明')}")
                        
                        if 'player_info' in collected_data:
                            player_info = collected_data['player_info']
                            print(f"\n👥 選手情報:")
                            print(f"   注目選手: {', '.join(player_info.get('featured_players', []))}")
                            print(f"   テーマ: {player_info.get('theme', '不明')}")
                        
                        print()
                    else:
                        print(f"\n⚠️  phasesまたはdata_collectionが見つかりません")
                        if 'phases' in mcp_result:
                            print(f"   使用可能なphases: {list(mcp_result['phases'].keys())}")
            except json.JSONDecodeError:
                print(f"📄 レスポンス: {result['body']}")
        
        return result
        
    except Exception as e:
        print(f"❌ 実行エラー: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """メイン関数"""
    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description='Lambda関数をローカルで実行')
    parser.add_argument('--mock-hour', type=int, metavar='HOUR', 
                       help='テスト用の時間を指定（0-23）例: --mock-hour 10')
    
    args = parser.parse_args()
    
    print("🖥️  Lambda ローカル実行スクリプト")
    print("=" * 50)
    
    # 引数の検証
    if args.mock_hour is not None:
        if not (0 <= args.mock_hour <= 23):
            print("❌ エラー: --mock-hour は 0-23 の値を指定してください")
            return 1
        print(f"🕙 時間モック: {args.mock_hour}時で実行")
    
    # 環境設定
    setup_environment(args.mock_hour)
    
    # AWS認証確認
    if not check_aws_credentials():
        return 1
    
    # Lambda実行
    try:
        result = asyncio.run(run_lambda_locally())
        if result:
            print(f"\n✅ 実行成功: {result.get('statusCode', 'Unknown')}")
            return 0
        else:
            print("\n❌ 実行失敗")
            return 1
    except KeyboardInterrupt:
        print("\n⚠️  実行が中断されました")
        return 1
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {e}")
        return 1

if __name__ == "__main__":
    exit(main())