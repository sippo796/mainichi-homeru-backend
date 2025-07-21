import json
import boto3
import os
import re
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")
    
    # CORS preflight request handling
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
                'Access-Control-Max-Age': '86400'
            },
            'body': ''
        }

    try:
        # パスパラメータから日付を取得
        path_parameters = event.get('pathParameters', {})
        if not path_parameters or 'date' not in path_parameters:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Date parameter is required'})
            }

        date = path_parameters['date']

        # 日付バリデーション (YYYY-MM-DD format)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Invalid date format. Use YYYY-MM-DD'})
            }

        bucket_name = os.environ.get('S3_BUCKET_NAME', 'test-bucket')
        logger.info(f"Using bucket: {bucket_name}")
        
        # ローカルテスト用：test-bucketの場合はモックデータを返す
        if bucket_name == 'test-bucket':
            logger.info("Local test mode - returning mock article")
            if date == '2024-07-20':
                mock_content = """# テスト記事：今日もベイスターズ最高！

牧選手の打撃が本当に素晴らしいですね！今日も元気にベイスターズを応援していきましょう！

今日も一日頑張ろう！ 💪"""
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'date': date,
                        'content': mock_content,
                        'lastModified': '2024-07-20T12:00:00Z'
                    }, ensure_ascii=False)
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Article not found'})
                }

        # S3から記事を取得
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key=f'articles/{date}.md'
        )

        content = response['Body'].read().decode('utf-8')

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'public, max-age=3600'
            },
            'body': json.dumps({
                'date': date,
                'content': content,
                'lastModified': response['LastModified'].isoformat()
            }, ensure_ascii=False)
        }

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Article not found'})
            }
        else:
            logger.error(f"S3 Error: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Failed to fetch article',
                    'message': str(e)
                })
            }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Failed to fetch article',
                'message': str(e)
            })
        }