import json
import boto3
import os
from datetime import datetime
import logging
from typing import Dict, List, Any
import asyncio

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')

class MCPAgent:
    """MCPエージェントの基底クラス"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"MCP.{name}")
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """エージェントの実行メソッド（サブクラスで実装）"""
        raise NotImplementedError

class DataCollectionAgent(MCPAgent):
    """データ収集エージェント"""
    
    def __init__(self):
        super().__init__("DataCollection")
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """試合情報とニュースを収集"""
        
        self.logger.info("Starting data collection...")
        
        # 1. 試合情報収集
        game_info = await self._fetch_game_info()
        
        # 2. 選手情報更新
        player_info = await self._fetch_current_players()
        
        # 3. ニュース情報収集
        news_info = await self._fetch_news()
        
        collected_data = {
            'game_info': game_info,
            'player_info': player_info,
            'news_info': news_info,
            'collection_timestamp': datetime.now().isoformat()
        }
        
        self.logger.info(f"Data collection completed: {len(collected_data)} items")
        
        return {
            'status': 'success',
            'data': collected_data,
            'agent': self.name
        }
    
    async def _fetch_game_info(self) -> Dict[str, Any]:
        """試合情報を取得（FetchGameInfo Lambda呼び出し）"""
        
        try:
            # FetchGameInfo関数を呼び出し
            function_name = self._find_function_by_name('FetchGameInfo')
            
            if function_name:
                response = lambda_client.invoke(
                    FunctionName=function_name,
                    InvocationType='RequestResponse',
                    Payload=json.dumps({})
                )
                
                payload = json.loads(response['Payload'].read())
                if payload.get('statusCode') == 200:
                    body = json.loads(payload['body'])
                    return body.get('game_info', {})
            
            return self._get_fallback_game_info()
            
        except Exception as e:
            self.logger.error(f"Error fetching game info: {e}")
            return self._get_fallback_game_info()
    
    async def _fetch_current_players(self) -> Dict[str, Any]:
        """現在の選手情報を取得（2025年実際のロスター）"""
        
        # 2025年シーズンの実際の一軍登録選手
        current_players = {
            'pitchers': ['東克樹', '伊勢大夢', '大貫晋一', 'バウアー', 'ジャクソン', '宮城滝太', '坂本裕哉', '森原康平', '颯', '石田裕太郎', '中川虎大', '松本凌人', '若松尚輝'],
            'catchers': ['松尾汐恩', '戸柱恭孝', '山本祐大'],
            'infielders': ['牧秀悟', '宮﨑敏郎', '京田陽太', '井上絢登', 'フォード', '柴田竜拓', '林琢真', '石上泰輝'],
            'outfielders': ['佐野恵太', '桑原将志', '神里和毅', '関根大気', '蝦名達夫', '筒香嘉智']
        }
        
        # スマート選手選択（日付ベースのローテーション + ランダム要素）
        selected_players = self._select_featured_players(current_players)
        
        return {
            'roster': current_players,
            'featured_players': selected_players,
            'last_updated': datetime.now().isoformat()
        }
    
    def _select_featured_players(self, roster: Dict[str, List[str]]) -> List[str]:
        """今日注目する選手をスマートに選択（3名、複数ランダム要素）"""
        
        import random
        from datetime import datetime
        
        today = datetime.now()
        
        # 複数のランダム要素を組み合わせてシードを作成
        base_seed = today.day + today.month + today.year
        weather_factor = (today.day * 7) % 13  # 天気っぽいランダム要素
        season_factor = (today.month - 1) // 3  # 季節要素（0-3）
        lunar_cycle = today.day % 28  # 月齢っぽいサイクル
        
        random.seed(base_seed + weather_factor + season_factor + lunar_cycle)
        
        # 曜日別の選手選択傾向
        weekday_focus = {
            0: 'pitchers',    # 月曜日は投手陣
            1: 'infielders',  # 火曜日は内野手
            2: 'outfielders', # 水曜日は外野手
            3: 'catchers',    # 木曜日は捕手陣
            4: 'pitchers',    # 金曜日は投手陣
            5: 'infielders',  # 土曜日は内野手
            6: 'outfielders'  # 日曜日は外野手
        }
        
        # 季節による重み調整（春は新人、夏はベテラン、秋は主力など）
        season_weights = {
            0: {'pitchers': 1.2, 'infielders': 1.0, 'outfielders': 1.0, 'catchers': 0.8},  # 春
            1: {'pitchers': 1.0, 'infielders': 1.2, 'outfielders': 1.1, 'catchers': 1.0},  # 夏  
            2: {'pitchers': 1.1, 'infielders': 1.1, 'outfielders': 1.2, 'catchers': 1.0},  # 秋
            3: {'pitchers': 1.3, 'infielders': 0.9, 'outfielders': 0.9, 'catchers': 1.1}   # 冬
        }
        
        selected_players = []
        used_positions = []
        
        # 1人目：メインの注目選手（曜日ベース）
        primary_position = weekday_focus[today.weekday()]
        main_player = random.choice(roster[primary_position])
        selected_players.append(main_player)
        used_positions.append(primary_position)
        
        # 2人目：別ポジションから選択
        available_positions = [pos for pos in roster.keys() if pos != primary_position]
        second_position = random.choice(available_positions)
        
        # そのポジションの選手から除外（同じ選手が選ばれないように）
        available_players = [p for p in roster[second_position] if p != main_player]
        second_player = random.choice(available_players)
        selected_players.append(second_player)
        used_positions.append(second_position)
        
        # 3人目：残りのポジションから選択（季節重み付き）
        remaining_positions = [pos for pos in roster.keys() if pos not in used_positions]
        
        # 季節重みを適用してポジション選択
        if remaining_positions:
            weights = [season_weights[season_factor].get(pos, 1.0) for pos in remaining_positions]
            third_position = random.choices(remaining_positions, weights=weights, k=1)[0]
        else:
            # 全てのポジションから選び直し
            third_position = random.choice(list(roster.keys()))
        
        # 既に選ばれた選手を除外
        available_players = [p for p in roster[third_position] if p not in selected_players]
        if available_players:
            third_player = random.choice(available_players)
        else:
            # 全選手から選び直し
            all_players = [p for players in roster.values() for p in players if p not in selected_players]
            third_player = random.choice(all_players)
        
        selected_players.append(third_player)
        
        # 追加のランダム要素：稀に順番をシャッフル
        if random.random() < 0.2:  # 20%の確率で順番シャッフル
            random.shuffle(selected_players)
        
        return selected_players
    
    async def _fetch_news(self) -> List[str]:
        """ニュース情報を取得"""
        
        # 実際のニュースAPIまたはスクレイピングの代わりに
        # 季節や状況に応じたポジティブニュースを生成
        season_news = [
            "チーム一丸となって今シーズンも頑張っています",
            "若手選手の成長が著しく、期待が高まります",
            "ファンの皆様の熱い声援がチームの力になっています",
            "練習に励む選手たちの姿が輝いています"
        ]
        
        return season_news[:2]  # 最新2件
    
    def _find_function_by_name(self, partial_name: str) -> str:
        """関数名の部分一致で Lambda 関数を検索"""
        
        try:
            functions = lambda_client.list_functions()
            for func in functions['Functions']:
                if partial_name in func['FunctionName']:
                    return func['FunctionName']
        except Exception as e:
            self.logger.error(f"Error listing functions: {e}")
        
        return None
    
    def _get_fallback_game_info(self) -> Dict[str, Any]:
        """フォールバック用の試合情報"""
        
        return {
            'has_game_today': True,
            'game_result': {
                'opponent': 'セリーグライバル',
                'result': '熱戦',
                'score': '好ゲーム'
            },
            'recent_news': ['チーム一丸となって頑張っています'],
            'player_highlights': ['佐野選手', '牧選手', '松尾選手']
        }

class ContentGenerationAgent(MCPAgent):
    """コンテンツ生成エージェント"""
    
    def __init__(self):
        super().__init__("ContentGeneration")
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """記事コンテンツを生成"""
        
        self.logger.info("Starting content generation...")
        
        collected_data = context.get('collected_data', {})
        today_jp = datetime.now().strftime('%Y年%m月%d日')
        
        # 1. コンテキスト分析
        content_context = self._analyze_context(collected_data)
        
        # 2. 記事生成
        article_content = await self._generate_article(today_jp, content_context)
        
        # 3. メタデータ生成
        metadata = self._generate_metadata(article_content, content_context)
        
        self.logger.info("Content generation completed")
        
        return {
            'status': 'success',
            'data': {
                'article_content': article_content,
                'metadata': metadata,
                'context_used': content_context
            },
            'agent': self.name
        }
    
    def _analyze_context(self, collected_data: Dict[str, Any]) -> Dict[str, Any]:
        """収集されたデータを分析してコンテキストを構築"""
        
        game_info = collected_data.get('game_info', {})
        player_info = collected_data.get('player_info', {})
        news_info = collected_data.get('news_info', [])
        
        # 記事の方向性を決定（選手応援記事にフォーカス）
        article_theme = "player_spotlight"  # 選手にスポットライトを当てた記事
        
        # 使用する選手を選定（3名に拡張）
        featured_players = player_info.get('featured_players', ['佐野恵太', '牧秀悟', '松尾汐恩'])
        
        return {
            'theme': article_theme,
            'featured_players': featured_players[:3],  # 最大3名に拡張
            'news_highlights': news_info[:1],  # 最新1件
            'generation_style': 'player_focused_positive'  # 選手中心のポジティブ記事
        }
    
    async def _generate_article(self, today_jp: str, context: Dict[str, Any]) -> str:
        """Claude APIを使用して記事を生成"""
        
        try:
            api_key = self._get_claude_api_key()
            
            if api_key == 'test-key':
                return self._generate_mock_article(today_jp, context)
            
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            
            prompt = self._build_advanced_prompt(today_jp, context)
            
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1500,  # 記事が完全に生成されるように増やす
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            return message.content[0].text
            
        except Exception as e:
            self.logger.error(f"Error generating article: {e}")
            return self._generate_mock_article(today_jp, context)
    
    def _build_advanced_prompt(self, today_jp: str, context: Dict[str, Any]) -> str:
        """高度なプロンプトを構築"""
        
        theme = context.get('theme', 'general_positive')
        players = context.get('featured_players', ['佐野選手', '牧選手'])
        game_context = context.get('game_context', {})
        news = context.get('news_highlights', [])
        
        # 選手情報の整理（ポジション付き）
        player_context = self._get_player_context(players, game_context)
        
        # テーマ別のプロンプト調整（選手中心）
        theme_instruction = {
            'player_spotlight': '選手たちの魅力や頑張りを褒め称える応援記事として',
            'general_positive': '日常的な応援メッセージとして'
        }.get(theme, '選手たちを応援する気持ちを込めて')
        
        # 試合結果は使わず、選手の情報のみに集中
        
        # ニュース情報の統合
        news_context = ""
        if news:
            news_context = f"最近のチーム状況: {news[0]}"
        
        prompt = f"""あなたは横浜DeNAベイスターズの熱狂的ファンライターです。
{today_jp}のベイスターズについて、{theme_instruction}700-800文字の記事を書いてください。

コンテキスト情報:
{player_context}
{news_context}

記事の要件:
- Markdown形式（# タイトルから開始）
- 明るく楽しい文体
- 指定された3名の選手全員を自然に含める
- 各選手のポジション（野手・投手）と特徴を正確に反映
- 選手それぞれの魅力、プレースタイル、頑張りを具体的に描写
- 練習風景、選手の人柄、技術的な特徴などに言及
- ファンの気持ちに寄り添う内容
- 「今日も頑張ろう！」的な前向きな締め
- 応援の気持ちを込めたポジティブな内容

記事のトーン: エネルギッシュで親しみやすく、読んだ人が元気になるような文章

重要: 
- 野手選手を投手として、投手選手を野手として書かないよう注意してください
- 3名の選手それぞれに言及し、バランスよく紹介してください
- 具体的な試合結果、スコア、勝敗には触れないでください
- 選手の日頃の努力や魅力に焦点を当ててください"""
        
        return prompt
    
    def _get_player_context(self, players: List[str], game_context: Dict[str, Any]) -> str:
        """選手の詳細情報を取得して文脈を構築"""
        
        # 2025年シーズンの実際の選手情報（一軍登録選手）
        player_positions = {
            # 投手陣
            '東克樹': '投手（11番・先発エース）',
            '伊勢大夢': '投手（13番・抑え）',
            '大貫晋一': '投手（16番・先発）',
            '坂本裕哉': '投手（20番・中継ぎ）',
            '松本凌人': '投手（34番・中継ぎ）',
            '若松尚輝': '投手（39番）',
            'ジャクソン': '投手（42番・先発）',
            '森原康平': '投手（45番・中継ぎ）',
            '颯': '投手（53番）',
            '石田裕太郎': '投手（54番）',
            '中川虎大': '投手（64番）',
            '宮城滝太': '投手（65番・先発）',
            'ケイ': '投手（69番）',
            'バウアー': '投手（96番・先発）',
            
            # 捕手陣
            '松尾汐恩': '捕手（5番・正捕手）',
            '戸柱恭孝': '捕手（10番・ベテラン）',
            '山本祐大': '捕手（50番）',
            
            # 内野手陣
            '林琢真': '内野手（00番）',
            '牧秀悟': '内野手（2番・キャプテン・二塁手）',
            '京田陽太': '内野手（9番・遊撃手）',
            '三森大貴': '内野手（26番）',
            '柴田竜拓': '内野手（31番・ユーティリティ）',
            '石上泰輝': '内野手（44番）',
            '宮﨑敏郎': '内野手（51番・三塁手・ベテラン）',
            '井上絢登': '内野手（55番・一塁手）',
            'フォード': '内野手（99番・一塁手）',
            
            # 外野手陣
            '桑原将志': '外野手（1番・中堅手）',
            '佐野恵太': '外野手（7番・左翼手）',
            '神里和毅': '外野手（8番）',
            '蝦名達夫': '外野手（61番）',
            '関根大気': '外野手（63番）'
        }
        
        # プレイヤーハイライト情報から詳細を抽出
        player_details = []
        highlights = game_context.get('player_highlights', [])
        
        for player_name in players:
            # 選手名の正規化（「選手」を除去）
            clean_name = player_name.replace('選手', '')
            position = player_positions.get(clean_name, '選手')
            
            # ハイライト情報から詳細を取得
            highlight_info = ""
            for highlight in highlights:
                if clean_name in highlight:
                    if '（野手）' in highlight:
                        highlight_info = "打撃で活躍"
                    elif '（投手）' in highlight:
                        highlight_info = "投球で活躍"
                    break
            
            player_details.append(f"{clean_name}選手（{position}）{f' - {highlight_info}' if highlight_info else ''}")
        
        return f"注目選手: {', '.join(player_details)}"
    
    def _generate_mock_article(self, today_jp: str, context: Dict[str, Any]) -> str:
        """テスト環境用のモック記事"""
        
        players = ', '.join(context.get('featured_players', ['佐野選手', '牧選手']))
        
        return f"""# 今日もベイスターズ最高！({today_jp})

MCPエージェント実装版での記事生成です！

{players}の活躍に期待が高まりますね。チーム一丸となって、今日も素晴らしいプレーを見せてくれることでしょう。

ベイスターズファンとして、今日も一日頑張りましょう！ 💪"""
    
    def _get_claude_api_key(self) -> str:
        """Claude API Keyを取得"""
        
        try:
            ssm_client = boto3.client('ssm')
            parameter_name = os.environ.get('CLAUDE_API_KEY_PARAMETER', '/mainichi-homeru/claude-api-key')
            response = ssm_client.get_parameter(
                Name=parameter_name,
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except Exception as e:
            self.logger.error(f"Failed to get Claude API key: {e}")
            return os.environ.get('CLAUDE_API_KEY', 'test-key')
    
    def _generate_metadata(self, article_content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """記事のメタデータを生成"""
        
        # タイトル抽出
        title = "今日もベイスターズ最高！"
        if article_content.startswith('#'):
            title = article_content.split('\n')[0].replace('#', '').strip()
        
        return {
            'title': title,
            'word_count': len(article_content),
            'featured_players': context.get('featured_players', []),
            'theme': context.get('theme', 'general_positive'),
            'generated_at': datetime.now().isoformat()
        }

class QualityAssuranceAgent(MCPAgent):
    """品質管理エージェント"""
    
    def __init__(self):
        super().__init__("QualityAssurance")
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """記事の品質をチェック・改善"""
        
        self.logger.info("Starting quality assurance...")
        
        generated_content = context.get('generated_content', {})
        article_content = generated_content.get('article_content', '')
        
        # 1. 品質チェック
        quality_score = self._assess_quality(article_content)
        
        # 2. 改善提案
        improvements = self._suggest_improvements(article_content, quality_score)
        
        # 3. 最終版生成
        final_content = self._apply_improvements(article_content, improvements)
        
        self.logger.info(f"Quality assurance completed. Score: {quality_score}/10")
        
        return {
            'status': 'success',
            'data': {
                'final_content': final_content,
                'quality_score': quality_score,
                'improvements_applied': improvements,
                'original_length': len(article_content),
                'final_length': len(final_content)
            },
            'agent': self.name
        }
    
    def _assess_quality(self, content: str) -> float:
        """記事の品質を評価（0-10のスコア）"""
        
        score = 0.0
        
        # 基本チェック項目
        if content.startswith('#'):
            score += 2.0  # タイトルあり
        
        if 150 <= len(content) <= 500:
            score += 2.0  # 適切な長さ
        
        if 'ベイスターズ' in content:
            score += 1.5  # チーム名言及
        
        if any(player in content for player in ['佐野', '牧', '宮崎', '松尾']):
            score += 1.5  # 選手名言及
        
        if content.endswith(('！', '。', '💪')):
            score += 1.0  # 適切な終わり方
        
        if '頑張' in content or '応援' in content:
            score += 1.0  # ポジティブな表現
        
        # 文字数による調整
        if len(content) > 50:
            score += 1.0  # 最低限の長さ
        
        return min(score, 10.0)
    
    def _suggest_improvements(self, content: str, score: float) -> List[str]:
        """改善提案を生成"""
        
        improvements = []
        
        if score < 5.0:
            improvements.append("overall_enhancement")
        
        if not content.startswith('#'):
            improvements.append("add_title")
        
        if len(content) < 150:
            improvements.append("expand_content")
        
        if 'ベイスターズ' not in content:
            improvements.append("add_team_reference")
        
        return improvements
    
    def _apply_improvements(self, content: str, improvements: List[str]) -> str:
        """改善を適用"""
        
        improved_content = content
        
        if "add_title" in improvements and not content.startswith('#'):
            improved_content = "# 今日もベイスターズ最高！\n\n" + improved_content
        
        if "add_team_reference" in improvements and 'ベイスターズ' not in content:
            improved_content = improved_content.replace('チーム', 'ベイスターズ', 1)
        
        if "expand_content" in improvements and len(improved_content) < 150:
            improved_content += "\n\n今日も一日、ベイスターズと共に頑張りましょう！"
        
        return improved_content

class MCPOrchestrator:
    """MCPエージェントのオーケストレーター"""
    
    def __init__(self):
        self.logger = logging.getLogger("MCP.Orchestrator")
        self.agents = {
            'data_collection': DataCollectionAgent(),
            'content_generation': ContentGenerationAgent(),
            'quality_assurance': QualityAssuranceAgent()
        }
    
    async def execute_pipeline(self) -> Dict[str, Any]:
        """MCPパイプラインを実行"""
        
        self.logger.info("Starting MCP pipeline execution...")
        
        try:
            # Phase 1: データ収集
            self.logger.info("Phase 1: Data Collection")
            data_result = await self.agents['data_collection'].execute({})
            
            if data_result['status'] != 'success':
                raise Exception("Data collection failed")
            
            # Phase 2: コンテンツ生成
            self.logger.info("Phase 2: Content Generation")
            content_context = {'collected_data': data_result['data']}
            content_result = await self.agents['content_generation'].execute(content_context)
            
            if content_result['status'] != 'success':
                raise Exception("Content generation failed")
            
            # Phase 3: 品質管理
            self.logger.info("Phase 3: Quality Assurance")
            qa_context = {'generated_content': content_result['data']}
            qa_result = await self.agents['quality_assurance'].execute(qa_context)
            
            if qa_result['status'] != 'success':
                raise Exception("Quality assurance failed")
            
            # 最終結果
            final_result = {
                'status': 'success',
                'pipeline_execution_time': datetime.now().isoformat(),
                'phases': {
                    'data_collection': data_result,
                    'content_generation': content_result,
                    'quality_assurance': qa_result
                },
                'final_article': qa_result['data']['final_content'],
                'quality_score': qa_result['data']['quality_score']
            }
            
            self.logger.info(f"MCP pipeline completed successfully. Quality score: {qa_result['data']['quality_score']}")
            
            return final_result
            
        except Exception as e:
            self.logger.error(f"MCP pipeline failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

def lambda_handler(event, context):
    """Lambda エントリーポイント"""
    
    logger.info(f"MCP Orchestrator Event: {json.dumps(event)}")
    
    try:
        # MCPオーケストレーターを実行
        orchestrator = MCPOrchestrator()
        
        # 非同期実行をラップ
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(orchestrator.execute_pipeline())
        
        if result['status'] == 'success':
            # S3に記事を保存
            today = datetime.now().strftime('%Y-%m-%d')
            bucket_name = os.environ['S3_BUCKET_NAME']
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'articles/{today}.md',
                Body=result['final_article'].encode('utf-8'),
                ContentType='text/markdown',
                Metadata={
                    'generated-by': 'mcp-orchestrator',
                    'quality-score': str(result['quality_score']),
                    'generation-time': result['pipeline_execution_time']
                }
            )
            
            logger.info(f"MCP article saved to S3: {today}")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'MCP article generated successfully',
                    'date': today,
                    'quality_score': result['quality_score'],
                    'preview': result['final_article'][:100] + '...'
                }, ensure_ascii=False)
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'MCP pipeline failed',
                    'details': result.get('error', 'Unknown error')
                })
            }
    
    except Exception as e:
        logger.error(f"MCP Orchestrator error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'MCP orchestrator failed',
                'message': str(e)
            })
        }