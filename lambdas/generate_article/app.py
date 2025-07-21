import json
import boto3
import os
from datetime import datetime
import anthropic
import logging
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
ssm_client = boto3.client('ssm')

def get_claude_api_key():
    """Parameter StoreからClaude API Keyを安全に取得"""
    try:
        parameter_name = os.environ.get('CLAUDE_API_KEY_PARAMETER', '/mainichi-homeru/claude-api-key')
        response = ssm_client.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )
        return response['Parameter']['Value']
    except Exception as e:
        logger.error(f"Failed to get Claude API key from Parameter Store: {e}")
        # フォールバック：環境変数から取得（ローカルテスト用）
        return os.environ.get('CLAUDE_API_KEY', 'test-key')

def fetch_game_info():
    """FetchGameInfo Lambda関数を呼び出して試合情報を取得"""
    
    try:
        # 同じリージョンのLambda関数を呼び出し
        lambda_client = boto3.client('lambda')
        
        # FetchGameInfoFunction を呼び出し
        function_name = None
        
        # 環境変数から関数名を取得（設定されていない場合は自動検出）
        if 'FETCH_GAME_INFO_FUNCTION' in os.environ:
            function_name = os.environ['FETCH_GAME_INFO_FUNCTION']
        else:
            # 関数名を自動検出
            lambda_functions = lambda_client.list_functions()
            for func in lambda_functions['Functions']:
                if 'FetchGameInfo' in func['FunctionName']:
                    function_name = func['FunctionName']
                    break
        
        if not function_name:
            logger.warning("FetchGameInfo function not found, using mock data")
            return get_mock_game_info()
        
        logger.info(f"Calling FetchGameInfo function: {function_name}")
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )
        
        payload = json.loads(response['Payload'].read())
        
        if payload.get('statusCode') == 200:
            body = json.loads(payload['body'])
            return body.get('game_info', {})
        else:
            logger.error(f"FetchGameInfo function error: {payload}")
            return get_mock_game_info()
            
    except Exception as e:
        logger.error(f"Error calling FetchGameInfo function: {e}")
        return get_mock_game_info()

def get_mock_game_info():
    """試合情報が取得できない場合のフォールバック"""
    
    return {
        'has_game_today': True,
        'game_result': {
            'opponent': 'セリーグチーム',
            'result': '熱戦',
            'score': '接戦'
        },
        'recent_news': ['選手たちの頑張り'],
        'player_highlights': ['牧選手', '宮崎選手', '佐野選手']
    }

def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")

    try:
        # 今日の日付を取得
        today = datetime.now().strftime('%Y-%m-%d')
        today_jp = datetime.now().strftime('%Y年%m月%d日')

        logger.info(f"Generating article for: {today}")

        # 試合情報を取得
        game_info = fetch_game_info()
        logger.info(f"Retrieved game info: {json.dumps(game_info)}")
        
        # Claude APIで記事生成（試合情報付き）
        article_content = generate_article_with_claude(today_jp, game_info)

        # S3に保存
        bucket_name = os.environ['S3_BUCKET_NAME']

        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'articles/{today}.md',
            Body=article_content.encode('utf-8'),
            ContentType='text/markdown',
            Metadata={
                'generated-at': datetime.now().isoformat(),
                'version': '1.0'
            }
        )

        logger.info(f"Article generated and saved: {today}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Article generated successfully',
                'date': today,
                'preview': article_content[:100] + '...'
            }, ensure_ascii=False)
        }

    except Exception as e:
        logger.error(f"Error generating article: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to generate article',
                'message': str(e)
            })
        }

def generate_article_with_claude(today_jp, game_info=None):
    """Claude APIを使って記事を生成（試合情報統合版）"""
    
    api_key = get_claude_api_key()
    if api_key == 'test-key':
        # ローカルテスト用のモック記事
        if game_info and game_info.get('game_result'):
            opponent = game_info['game_result'].get('opponent', '相手チーム')
            return f"""# 今日もベイスターズ最高！({today_jp})

今日は{opponent}戦！テスト環境での記事生成です。

牧選手の打撃が本当に素晴らしいですね！今日も元気にベイスターズを応援していきましょう！

今日も一日頑張ろう！ 💪"""
        else:
            return f"""# 今日もベイスターズ最高！({today_jp})

テスト環境での記事生成です。

牧選手の打撃が本当に素晴らしいですね！今日も元気にベイスターズを応援していきましょう！

今日も一日頑張ろう！ 💪"""

    client = anthropic.Anthropic(api_key=api_key)

    # 試合情報を活用したプロンプト作成
    game_context = ""
    if game_info:
        if game_info.get('has_game_today') and game_info.get('game_result'):
            game_result = game_info['game_result']
            opponent = game_result.get('opponent', '相手チーム')
            result = game_result.get('result', '熱戦')
            score = game_result.get('score', '接戦')
            
            game_context = f"""
今日の試合情報:
- 対戦相手: {opponent}
- 結果: {result}
- スコア: {score}
"""
        
        if game_info.get('player_highlights'):
            highlights = ', '.join(game_info['player_highlights'][:2])
            game_context += f"注目選手: {highlights}\n"
        
        if game_info.get('recent_news'):
            news = game_info['recent_news'][0] if game_info['recent_news'] else ""
            game_context += f"最新情報: {news}\n"

    prompt = f"""あなたは横浜DeNAベイスターズの熱狂的ファンです。
{today_jp}のベイスターズについて、300文字程度でポジティブな応援記事を書いてください。

{game_context}

条件:
- 明るく楽しい文体で書く
- 上記の試合情報や選手情報を活用する
- 具体的な選手名を1-2名含める（牧秀悟、佐野恵太、大和、宮崎敏郎、オースティンなど）
- 「今日も一日頑張ろう！」的な前向きな締めくくり
- Markdown形式で出力（# タイトル から始める）
- 勝敗に関係なく、ポジティブな視点で記事を書く

記事例:
# 今日もベイスターズ最高！

牧選手の打撃センスは本当に素晴らしいですね！..."""

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    return message.content[0].text

