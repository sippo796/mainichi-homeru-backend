import json
import boto3
import os
import re
import time
import hashlib
from datetime import datetime, timedelta
import pytz
import logging
from typing import Dict, List, Any
import asyncio
import urllib.request
import urllib.error
from urllib.parse import urljoin, urlparse, quote
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')

class BaystarsRSSNewsCollector:
    """Google News RSS経由でベイスターズニュースを取得する高速スクレイパー"""
    
    def __init__(self):
        import urllib.request
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 重複チェック用のハッシュ保存（Lambda環境では一時的）
        self.seen_articles = set()
        
        # 推し選手リスト（個別検索用）
        self.featured_players = []
        
        # 全体検索クエリ
        self.general_queries = [
            "横浜DeNAベイスターズ",
            "横浜DeNAベイスターズ 試合"
        ]
        
        # 旧システム互換性のため
        self.search_queries = self.general_queries
        
        # ベイスターズ関連キーワード（強化版）
        self.baystars_keywords = [
            'ベイスターズ', 'DeNA', '横浜', 'baystars', 'dena', 'yokohama',
            '佐野', '牧', '宮崎', '森', '関根', '桑原', '大和', '三浦',
            '今永', '大貫', '東', '上茶谷', '平良', '入江', '伊勢', '山崎',
            '戸柱', '益子', '蝦名', '京田', '松尾', '石川',
            '藤浪', 'ビシエド', '橋本達弥'
        ]

    def _generate_article_hash(self, url, title):
        """記事の一意ハッシュを生成"""
        content = f"{url}#{title}".encode('utf-8')
        return hashlib.md5(content).hexdigest()

    def _is_baystars_related(self, text):
        """テキストがベイスターズ関連かチェック"""
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.baystars_keywords)

    def fetch_rss_feed(self, query):
        """Google News RSSフィードを取得"""
        try:
            # Google News RSS URL構築
            encoded_query = quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
            
            logger.info(f"📡 RSS取得中: {query}")
            
            # feedparserがない場合は urllib で代替実装
            try:
                import feedparser
                feed = feedparser.parse(rss_url)
                if feed.bozo:
                    logger.warning(f"⚠️  RSS解析警告: {feed.bozo_exception}")
                return feed
            except ImportError:
                # feedparserがない場合の代替実装
                logger.warning("feedparser not available, using fallback RSS parsing")
                return self._parse_rss_manually(rss_url)
            
        except Exception as e:
            logger.error(f"❌ RSS取得エラー ({query}): {e}")
            return None

    def _parse_rss_manually(self, rss_url):
        """feedparserが使用できない場合の手動RSS解析"""
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            
            req = urllib.request.Request(rss_url, headers=self.session_headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_content = response.read().decode('utf-8')
            
            # 簡単なXML解析
            root = ET.fromstring(xml_content)
            
            # RSS エントリを抽出
            entries = []
            for item in root.findall('.//item'):
                entry = {}
                title_elem = item.find('title')
                link_elem = item.find('link')
                desc_elem = item.find('description')
                pub_elem = item.find('pubDate')
                
                if title_elem is not None:
                    entry['title'] = title_elem.text
                if link_elem is not None:
                    entry['link'] = link_elem.text
                if desc_elem is not None:
                    entry['summary'] = desc_elem.text
                if pub_elem is not None:
                    entry['published'] = pub_elem.text
                    
                # ソース情報を抽出（可能であれば）
                source_elem = item.find('.//{http://search.yahoo.com/mrss/}credit')
                if source_elem is not None:
                    entry['source'] = {'title': source_elem.text}
                else:
                    entry['source'] = {'title': 'Google News'}
                
                entries.append(entry)
            
            # feedparserライクなオブジェクトを作成
            class FeedLike:
                def __init__(self, entries):
                    self.entries = entries
                    self.bozo = False
            
            return FeedLike(entries)
            
        except Exception as e:
            logger.error(f"Manual RSS parsing failed: {e}")
            return None

    def extract_article_from_rss_item(self, item):
        """RSS itemから記事情報を抽出"""
        try:
            # 基本情報をRSSから取得
            article_data = {
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'summary': item.get('summary', ''),
                'publish_date': item.get('published', ''),
                'source': item.get('source', {}).get('title', 'Google News'),
                'scraped_at': datetime.now().isoformat(),
                'content': '',
                'images': [],
                'is_baystars_related': False,
                'baystars_keywords_found': [],
                'collection_method': 'google_news_rss',
                'player_relevance_score': 0,
                'is_player_focused': False
            }
            
            # HTMLタグを除去して純粋なテキストを取得
            if article_data['summary']:
                # 簡単なHTMLタグ除去
                import re
                article_data['summary'] = re.sub(r'<[^>]*>', '', article_data['summary']).strip()
            
            # ベイスターズ関連判定
            full_text = f"{article_data['title']} {article_data['summary']}"
            article_data['is_baystars_related'] = self._is_baystars_related(full_text)
            
            # 見つかったキーワード記録
            found_keywords = []
            for keyword in self.baystars_keywords:
                if keyword.lower() in full_text.lower():
                    found_keywords.append(keyword)
            article_data['baystars_keywords_found'] = found_keywords
            
            # 選手関連度の判定を追加
            player_score, is_player_focused = self._assess_player_relevance(full_text)
            article_data['player_relevance_score'] = player_score
            article_data['is_player_focused'] = is_player_focused
            
            return article_data
            
        except Exception as e:
            logger.error(f"❌ RSS記事抽出エラー: {e}")
            return None

    def _assess_player_relevance(self, text):
        """記事の選手関連度を評価"""
        
        # 選手名リスト（より包括的）
        player_names = [
            # 現役選手名（苗字のみでも検出）
            '佐野', '牧', '宮崎', '京田', '松尾', '戸柱', '桑原', '神里', '関根', '蝦名',
            '東', '大貫', 'バウアー', 'ジャクソン', '伊勢', '山崎', '入江', '森原', '石田',
            '柴田', '井上', 'フォード', '林', '石上',
            # フルネーム
            '佐野恵太', '牧秀悟', '宮崎敏郎', '京田陽太', '松尾汐恩', '戸柱恭孝',
            '桑原将志', '神里和毅', '関根大気', '蝦名達夫',
            '東克樹', '大貫晋一', '伊勢大夢', '山崎康晃'
        ]
        
        # 選手関連キーワード
        player_keywords = [
            '活躍', '打撃', '投球', '守備', '好調', '不調', '復活', 'ホームラン', 'ヒット',
            '先発', '登板', '勝利', '敗戦', '好投', '完投', '救援', 'セーブ', '奪三振',
            '打点', '得点', '盗塁', '併殺', 'エラー', '好守', '送球', 'キャッチング',
            '調子', '成績', '打率', '防御率', '勝率', 'OPS', 'ERA',
            '練習', 'トレーニング', 'コンディション', '怪我', '復帰', '離脱',
            '移籍', 'トレード', '契約', '年俸', 'FA', '残留', '獲得', '放出'
        ]
        
        # 非選手関連キーワード（これらがあると減点）
        non_player_keywords = [
            'スポンサー', '協賛', '企業', '契約', '提携', 'パートナーシップ',
            'イベント', 'グッズ', '商品', 'キャンペーン', '販売', '価格',
            'ファンクラブ', 'チケット', '入場', '観客', '動員', '売上',
            '球団', '経営', '運営', '社長', '監督人事', 'コーチ', 'スタッフ',
            '施設', 'スタジアム', '改修', '工事', '建設', 'アクセス'
        ]
        
        score = 0
        text_lower = text.lower()
        
        # 選手名の検出（高配点）
        for player in player_names:
            if player in text:
                score += 3  # 選手名は高得点
        
        # 選手関連キーワードの検出
        for keyword in player_keywords:
            if keyword in text:
                score += 1
        
        # 非選手関連キーワードの検出（減点）
        for keyword in non_player_keywords:
            if keyword in text:
                score -= 2
        
        # 試合関連かどうかの判定（選手と関連しやすい）
        game_keywords = ['試合', '対戦', '勝利', '敗戦', '勝負', '戦い', 'vs', '戦']
        for keyword in game_keywords:
            if keyword in text:
                score += 1
        
        # 選手重視判定
        is_player_focused = score >= 3  # 3点以上で選手関連とみなす
        
        return max(0, score), is_player_focused

    def set_featured_players(self, players):
        """推し選手を設定"""
        self.featured_players = players
        logger.info(f"🎯 推し選手設定: {', '.join(players)}")

    def collect_player_specific_news(self, player_name, max_articles=5):
        """特定選手の個別ニュース収集"""
        logger.info(f"🔍 {player_name} 選手の個別ニュース検索開始...")
        
        # 選手名での検索クエリ生成
        player_queries = [
            f"{player_name} 横浜DeNA",
            f"{player_name} ベイスターズ",
            f"{player_name}"
        ]
        
        player_articles = []
        
        for query in player_queries:
            logger.info(f"   📋 クエリ: {query}")
            
            feed = self.fetch_rss_feed(query)
            if not feed or not hasattr(feed, 'entries'):
                continue
            
            logger.info(f"   📊 RSS記事数: {len(feed.entries)} 件")
            
            for i, item in enumerate(feed.entries[:max_articles], 1):
                title = item.get('title', '')
                url = item.get('link', '')
                
                # 重複チェック
                article_hash = self._generate_article_hash(url, title)
                if article_hash in self.seen_articles:
                    logger.info(f"   [{i:2d}] ⏭️  スキップ (既処理): {title[:40]}...")
                    continue
                
                # ベイスターズ関連 + 対象選手言及チェック
                article_data = self.extract_article_from_rss_item(item)
                if article_data and self._is_player_mentioned(article_data, player_name):
                    self.seen_articles.add(article_hash)
                    article_data['hash'] = article_hash
                    article_data['query_used'] = query
                    article_data['target_player'] = player_name
                    article_data['search_type'] = 'player_specific'
                    
                    player_articles.append(article_data)
                    
                    logger.info(f"   [{i:2d}] ✅ {player_name}選手関連記事を収集")
                    logger.info(f"        📰 {title[:50]}...")
                    logger.info(f"        🏷️  キーワード: {', '.join(article_data['baystars_keywords_found'][:3])}")
                    
                    # 選手個別検索では少数精鋭で
                    if len(player_articles) >= 3:
                        break
            
            # 十分な記事が見つかったら次のクエリはスキップ
            if len(player_articles) >= 3:
                break
            
            time.sleep(1)  # レート制限
        
        logger.info(f"   📊 {player_name}選手の記事: {len(player_articles)} 件収集")
        return player_articles

    def _is_player_mentioned(self, article_data, player_name):
        """記事に特定選手が言及されているかチェック"""
        if not article_data['is_baystars_related']:
            return False
        
        full_text = f"{article_data['title']} {article_data['summary']}"
        
        # 選手名の様々なパターンをチェック
        name_patterns = [
            player_name,  # フルネーム
            player_name.split()[0] if ' ' in player_name else player_name,  # 苗字のみ
        ]
        
        # 苗字だけの場合も追加
        if len(player_name) > 2:
            name_patterns.append(player_name[:2])  # 最初の2文字（苗字）
        
        for pattern in name_patterns:
            if pattern in full_text:
                return True
        
        return False

    def collect_general_baystars_news(self, max_articles=5):
        """ベイスターズ全体のニュース収集"""
        logger.info(f"🔄 ベイスターズ全体ニュース収集開始...")
        
        general_articles = []
        
        for query in self.general_queries:
            logger.info(f"📋 全体クエリ: {query}")
            
            feed = self.fetch_rss_feed(query)
            if not feed or not hasattr(feed, 'entries'):
                continue
            
            logger.info(f"   📊 RSS記事数: {len(feed.entries)} 件")
            
            for i, item in enumerate(feed.entries[:max_articles], 1):
                title = item.get('title', '')
                url = item.get('link', '')
                
                # 重複チェック
                article_hash = self._generate_article_hash(url, title)
                if article_hash in self.seen_articles:
                    continue
                
                article_data = self.extract_article_from_rss_item(item)
                if article_data and article_data['is_baystars_related']:
                    self.seen_articles.add(article_hash)
                    article_data['hash'] = article_hash
                    article_data['query_used'] = query
                    article_data['search_type'] = 'general_team'
                    
                    general_articles.append(article_data)
                    
                    logger.info(f"   [{i:2d}] ✅ 全体ニュースを収集")
                    logger.info(f"        📰 {title[:50]}...")
            
            time.sleep(1)
        
        logger.info(f"📊 全体ニュース: {len(general_articles)} 件収集")
        return general_articles

    def collect_comprehensive_news(self, featured_players, max_per_player=3, max_general=5):
        """推し選手 + 全体ニュースの包括的収集"""
        logger.info(f"🎯 包括的ニュース収集開始 (推し選手: {len(featured_players)}名, 全体ニュース: {max_general}件)")
        
        self.set_featured_players(featured_players)
        
        all_articles = []
        player_articles_by_name = {}
        
        # 1. 推し選手個別検索
        for player in featured_players:
            player_articles = self.collect_player_specific_news(player, max_per_player)
            player_articles_by_name[player] = player_articles
            all_articles.extend(player_articles)
        
        # 2. ベイスターズ全体検索
        general_articles = self.collect_general_baystars_news(max_general)
        all_articles.extend(general_articles)
        
        # 結果をログ出力
        logger.info(f"\n📊 包括的収集結果:")
        logger.info(f"   🎯 推し選手記事: {sum(len(articles) for articles in player_articles_by_name.values())} 件")
        for player, articles in player_articles_by_name.items():
            logger.info(f"     - {player}: {len(articles)} 件")
        logger.info(f"   📰 全体記事: {len(general_articles)} 件")
        logger.info(f"   📊 合計: {len(all_articles)} 件")
        
        return {
            'all_articles': all_articles,
            'player_articles': player_articles_by_name,
            'general_articles': general_articles,
            'summary': {
                'total_articles': len(all_articles),
                'player_articles_count': sum(len(articles) for articles in player_articles_by_name.values()),
                'general_articles_count': len(general_articles),
                'featured_players': featured_players
            }
        }

    def collect_news_from_multiple_queries(self, max_articles_per_query=10):
        """複数のクエリでニュースを収集"""
        logger.info(f"🔄 {len(self.search_queries)} 種類のクエリでRSSニュース収集開始...")
        
        all_articles = []
        new_articles_count = 0
        
        for i, query in enumerate(self.search_queries, 1):
            logger.info(f"📋 クエリ {i}/{len(self.search_queries)}: {query}")
            
            # RSSフィード取得
            feed = self.fetch_rss_feed(query)
            if not feed or not hasattr(feed, 'entries'):
                logger.info(f"   ❌ フィード取得失敗")
                continue
            
            logger.info(f"   📊 RSS記事数: {len(feed.entries)} 件")
            
            query_articles = []
            
            for j, item in enumerate(feed.entries[:max_articles_per_query], 1):
                title = item.get('title', '')
                url = item.get('link', '')
                
                # 重複チェック
                article_hash = self._generate_article_hash(url, title)
                if article_hash in self.seen_articles:
                    logger.info(f"   [{j:2d}] ⏭️  スキップ (既処理): {title[:40]}...")
                    continue
                
                logger.info(f"   [{j:2d}] 🆕 処理中: {title[:40]}...")
                
                # RSS記事データ抽出
                article_data = self.extract_article_from_rss_item(item)
                
                if article_data and article_data['is_baystars_related']:
                    # 新しい記事として記録
                    self.seen_articles.add(article_hash)
                    article_data['hash'] = article_hash
                    article_data['query_used'] = query
                    
                    query_articles.append(article_data)
                    all_articles.append(article_data)
                    new_articles_count += 1
                    
                    # 選手関連度によるログ表示
                    player_status = "🏆 選手中心" if article_data['is_player_focused'] else "📰 一般"
                    logger.info(f"        ✅ ベイスターズ関連記事として収集 ({player_status})")
                    logger.info(f"        🏷️  キーワード: {', '.join(article_data['baystars_keywords_found'][:3])}")
                    logger.info(f"        📊 選手関連度: {article_data['player_relevance_score']}点")
                    logger.info(f"        📰 ソース: {article_data['source']}")
                    
                else:
                    logger.info(f"        ⏭️  ベイスターズ関連ではないためスキップ")
            
            logger.info(f"   📊 クエリ結果: {len(query_articles)} 件の新記事")
            
            # レート制限（Google News APIに優しく）
            time.sleep(1)
        
        logger.info(f"📊 RSS収集完了: {new_articles_count} 件の新しいベイスターズ記事を取得")
        return all_articles

    def generate_summary_report(self, articles):
        """収集結果のサマリーレポートを生成"""
        if not articles:
            return "📭 新しい記事は見つかりませんでした"
        
        # 統計情報
        total_articles = len(articles)
        sources = {}
        keywords_count = {}
        
        for article in articles:
            # ソース別統計
            source = article.get('source', 'Unknown')
            sources[source] = sources.get(source, 0) + 1
            
            # キーワード別統計
            for keyword in article.get('baystars_keywords_found', []):
                keywords_count[keyword] = keywords_count.get(keyword, 0) + 1
        
        # レポート生成
        report = [
            f"📊 ベイスターズRSSニュース収集レポート",
            f"🎯 新規記事数: {total_articles} 件",
            f"📰 情報ソース数: {len(sources)} サイト",
        ]
        
        # ソース別表示（上位5つ）
        if sources:
            report.append("📈 主要ソース:")
            sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)
            for source, count in sorted_sources[:5]:
                report.append(f"   {source}: {count} 件")
        
        # キーワード別表示（上位5個）
        if keywords_count:
            report.append("🏷️  頻出キーワード:")
            sorted_keywords = sorted(keywords_count.items(), key=lambda x: x[1], reverse=True)
            for keyword, count in sorted_keywords[:5]:
                report.append(f"   {keyword}: {count} 回")
        
        return "\n".join(report)

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
        
        # 時間帯を判定
        jst = pytz.timezone('Asia/Tokyo')
        now_jst = datetime.now(jst)
        time_period = "morning" if 6 <= now_jst.hour <= 12 else "evening"
        
        # 1. 試合情報収集
        game_info = await self._fetch_game_info()
        
        # 2. 選手情報更新（時間帯別）
        player_info = await self._fetch_current_players(time_period)
        
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
        """Yahoo!スポーツスクレイピングでベイスターズ関連の最新ニュースを検索・分析"""
        
        try:
            # Yahoo!スポーツスクレイピングで最新のベイスターズニュースを収集
            news_info = await self._search_baystars_news()
            
            return news_info
            
        except Exception as e:
            self.logger.error(f"Error fetching recent news: {e}")
            return self._get_fallback_game_info()
    
    async def _fetch_current_players(self, time_period: str = None) -> Dict[str, Any]:
        """現在の選手情報を取得（2025年実際のロスター）"""
        
        # 2025年シーズンの実際の一軍登録選手
        current_players = {
            'pitchers': ['東克樹', '伊勢大夢', '大貫晋一', 'バウアー', 'ジャクソン', '宮城滝太', '坂本裕哉', '森原康平', '颯', '石田裕太郎', '中川虎大', '松本凌人', '若松尚輝', '入江大生', 'ケイ', 'ウィック'],
            'catchers': ['松尾汐恩', '戸柱恭孝', '山本祐大'],
            'infielders': ['牧秀悟', '宮﨑敏郎', '京田陽太', '井上絢登', 'フォード', '柴田竜拓', '林琢真', '石上泰輝'],
            'outfielders': ['佐野恵太', '桑原将志', '神里和毅', '関根大気', '蝦名達夫', '筒香嘉智']
        }
        
        # スマート選手選択（時間帯別対応）
        selected_players = self._select_featured_players(current_players, time_period)
        
        return {
            'roster': current_players,
            'featured_players': selected_players,
            'last_updated': datetime.now().isoformat()
        }
    
    def _select_featured_players(self, roster: Dict[str, List[str]], time_period: str = None) -> List[str]:
        """今日注目する選手をスマートに選択（3名、時間帯別対応）"""
        
        import random
        from datetime import datetime
        
        # 日本時間で現在の時刻を取得
        jst = pytz.timezone('Asia/Tokyo')
        now_jst = datetime.now(jst)
        
        # 時間帯を判定（引数で指定されていない場合）
        if not time_period:
            time_period = "morning" if 6 <= now_jst.hour <= 12 else "evening"
        
        # 時間帯別のシード値を生成
        base_seed = now_jst.day + now_jst.month + now_jst.year
        time_factor = 100 if time_period == "morning" else 200  # 朝・夜で大きく異なる値
        weather_factor = (now_jst.day * 7) % 13  # 天気っぽいランダム要素
        season_factor = (now_jst.month - 1) // 3  # 季節要素（0-3）
        lunar_cycle = now_jst.day % 28  # 月齢っぽいサイクル
        
        # 時間帯を含む複合シード
        random.seed(base_seed + time_factor + weather_factor + season_factor + lunar_cycle)
        
        self.logger.info(f"🎯 選手選択 - 時間帯: {time_period}, シード: {base_seed + time_factor}")
        
        # 時間帯別の選手選択傾向
        time_based_focus = {
            'morning': {
                'primary_boost': 'pitchers',    # 朝は投手陣に注目
                'secondary_boost': 'catchers'   # バッテリー重視
            },
            'evening': {
                'primary_boost': 'outfielders', # 夜は野手陣に注目
                'secondary_boost': 'infielders' # 内野手も重視
            }
        }
        
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
        
        # 時間帯による選手選択の影響
        time_focus = time_based_focus.get(time_period, {'primary_boost': 'pitchers', 'secondary_boost': 'catchers'})
        
        # 1人目：時間帯重視 + 曜日傾向の組み合わせ
        weekday_position = weekday_focus[now_jst.weekday()]
        time_boost_position = time_focus['primary_boost']
        
        # 40%の確率で時間帯重視、60%の確率で曜日重視
        if random.random() < 0.4:
            primary_position = time_boost_position
            self.logger.info(f"   🌅 時間帯重視選択: {time_boost_position}")
        else:
            primary_position = weekday_position
            self.logger.info(f"   📅 曜日重視選択: {weekday_position}")
        
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
            self.logger.info(f"   🔀 順番シャッフル実行")
        
        self.logger.info(f"✅ 推し選手決定: {', '.join(selected_players)} ({time_period})")
        
        return selected_players
    
    async def _fetch_news(self) -> List[str]:
        """RSS経由でベイスターズニュースを取得"""
        
        try:
            # RSS ニュース収集を実行
            rss_collector = BaystarsRSSNewsCollector()
            articles = rss_collector.collect_news_from_multiple_queries(max_articles_per_query=10)
            
            # 記事タイトルをリストとして返す
            news_titles = [article.get('title', '') for article in articles[:5]]
            
            if news_titles:
                self.logger.info(f"RSS収集成功: {len(news_titles)}件のニュースを取得")
                return news_titles
            else:
                self.logger.warning("RSS収集: 新しい記事が見つかりませんでした")
                return self._get_fallback_news()
                
        except Exception as e:
            self.logger.error(f"RSS収集エラー: {e}")
            return self._get_fallback_news()
    
    def _get_fallback_news(self) -> List[str]:
        """フォールバック用のニュース"""
        return [
            "チーム一丸となって今シーズンも頑張っています",
            "若手選手の成長が著しく、期待が高まります",
            "ファンの皆様の熱い声援がチームの力になっています",
            "練習に励む選手たちの姿が輝いています"
        ][:2]
    
    def _get_news_api_key(self) -> str:
        """News API Keyを取得"""
        
        try:
            ssm_client = boto3.client('ssm')
            parameter_name = os.environ.get('OPENAI_API_KEY_PARAMETER', '/mainichi-homeru/openai-api-key')
            response = ssm_client.get_parameter(
                Name=parameter_name,
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except Exception as e:
            self.logger.error(f"Failed to get News API key: {e}")
            return os.environ.get('NEWS_API_KEY', 'test-key')
    
    async def _search_baystars_news(self, api_key: str = None) -> Dict[str, Any]:
        """Google News RSS経由で推し選手個別 + ベイスターズ全体ニュースを収集"""
        
        try:
            self.logger.info("Starting comprehensive RSS collection for featured players + team news...")
            
            # 時間帯を判定
            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.now(jst)
            time_period = "morning" if 6 <= now_jst.hour <= 12 else "evening"
            
            # 推し選手を取得（時間帯別選手情報から）
            player_info = await self._fetch_current_players(time_period)
            featured_players = player_info.get('featured_players', ['佐野恵太', '牧秀悟', '松尾汐恩'])
            
            # 推し選手個別 + 全体ニュース収集
            rss_collector = BaystarsRSSNewsCollector()
            comprehensive_result = rss_collector.collect_comprehensive_news(
                featured_players=featured_players,
                max_per_player=3,
                max_general=5
            )
            
            articles = comprehensive_result['all_articles']
            player_articles = comprehensive_result['player_articles']
            general_articles = comprehensive_result['general_articles']
            
            if articles:
                # 記事生成用の形式に変換（推し選手別に整理）
                recent_news = []
                trending_players = featured_players  # 推し選手を優先
                positive_highlights = []
                
                # 推し選手別の記事整理
                player_news_summary = {}
                for player, player_arts in player_articles.items():
                    if player_arts:
                        player_news_summary[player] = []
                        for article in player_arts:
                            news_item = {
                                'headline': article.get('title', ''),
                                'category': f'野球・{player}選手',
                                'key_facts': [article.get('summary', '')],
                                'mentioned_players': [player],
                                'date': article.get('publish_date', datetime.now().strftime('%Y-%m-%d')),
                                'source': article.get('source', 'Google News'),
                                'query_used': article.get('query_used', ''),
                                'search_type': 'player_specific',
                                'target_player': player
                            }
                            player_news_summary[player].append(news_item)
                            recent_news.append(news_item)
                            
                            # ポジティブな話題を抽出
                            title = article.get('title', '')
                            if any(word in title for word in ['勝利', '活躍', '好調', 'ホームラン', '優勝', 'ヒット', '快勝', '先発', '好投', '復活']):
                                positive_highlights.append(f"{player}: {title}")
                
                # 全体記事も追加
                for article in general_articles:
                    news_item = {
                        'headline': article.get('title', ''),
                        'category': '野球・ベイスターズ',
                        'key_facts': [article.get('summary', '')],
                        'mentioned_players': article.get('baystars_keywords_found', []),
                        'date': article.get('publish_date', datetime.now().strftime('%Y-%m-%d')),
                        'source': article.get('source', 'Google News'),
                        'query_used': article.get('query_used', ''),
                        'search_type': 'general_team'
                    }
                    recent_news.append(news_item)
                    
                    # ポジティブな話題を抽出
                    title = article.get('title', '')
                    if any(word in title for word in ['勝利', '活躍', '好調', 'ホームラン', '優勝', 'ヒット', '快勝', '先発']):
                        positive_highlights.append(title)
                
                game_info = {
                    'has_recent_news': True,
                    'recent_news': recent_news,
                    'trending_players': trending_players,
                    'team_situation': f"推し選手個別検索({len(player_articles)}名) + 全体検索で合計{len(articles)}件の記事を収集",
                    'positive_highlights': positive_highlights,
                    'data_source': 'comprehensive_rss',
                    'collection_summary': comprehensive_result['summary'],
                    'player_specific_news': player_news_summary,
                    'general_news': [{'headline': g.get('title', ''), 'source': g.get('source', '')} for g in general_articles],
                    'featured_players': featured_players
                }
                
                self.logger.info(f"Comprehensive RSS collection successful: {len(recent_news)} news items")
                
                # 収集結果の詳細ログ出力
                self.logger.info(f"🎯 推し選手個別検索結果:")
                for player, player_arts in player_articles.items():
                    self.logger.info(f"  {player}: {len(player_arts)} 件")
                    for i, article in enumerate(player_arts, 1):
                        self.logger.info(f"    [{i}] {article['title'][:50]}... (ソース: {article['source']})")
                
                self.logger.info(f"📰 全体検索結果: {len(general_articles)} 件")
                for i, article in enumerate(general_articles[:2], 1):
                    self.logger.info(f"  [{i}] {article['title'][:50]}... (ソース: {article['source']})")
                
                return game_info
            else:
                self.logger.warning("No Baystars news found from RSS, using enhanced fallback")
                return self._get_enhanced_fallback_game_info()
            
        except Exception as e:
            self.logger.error(f"Google News RSS collection failed: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return self._get_fallback_game_info()
    
    
    def _extract_player_names(self, text: str) -> List[str]:
        """テキストから選手名を抽出"""
        
        players = ['牧秀悟', '佐野恵太', '三浦大輔', '宮崎敏郎', '今永昇太', '石田裕太郎', '山本拓実']
        found_players = []
        
        for player in players:
            if player in text:
                found_players.append(player)
        
        return found_players
    
    def _extract_trending_players(self, text: str) -> List[str]:
        """テキストからトレンド選手を抽出"""
        
        player_count = {}
        players = ['牧', '佐野', '三浦', '宮崎', '今永', '石田', '山本']
        
        for player in players:
            count = text.count(player)
            if count > 0:
                player_count[player] = count
        
        # 出現回数でソート
        return [player for player, count in sorted(player_count.items(), key=lambda x: x[1], reverse=True)[:3]]
    
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
    
    def _get_enhanced_fallback_game_info(self) -> Dict[str, Any]:
        """強化版フォールバック用の試合情報（リアルなベイスターズニュース）"""
        
        # 実際のベイスターズに関する最新トピック（2025年シーズン想定）
        sample_news = [
            {
                'title': '牧秀悟キャプテンが連日の猛練習でチームを牽引',
                'source': 'Yahoo!スポーツ(sample)',
                'pattern': 'captain_leadership'
            },
            {
                'title': '戸柱恭孝ベテラン捕手が若手投手陣の指導に熱心',
                'source': 'Yahoo!スポーツ(sample)', 
                'pattern': 'veteran_guidance'
            },
            {
                'title': '京田陽太の華麗な守備がファンの話題に',
                'source': 'Yahoo!スポーツ(sample)',
                'pattern': 'defensive_play'
            },
            {
                'title': '三浦監督「選手たちの成長を感じている」とコメント',
                'source': 'Yahoo!スポーツ(sample)',
                'pattern': 'manager_comment'
            },
            {
                'title': 'ハマスタでの練習で選手たちが汗を流す',
                'source': 'Yahoo!スポーツ(sample)',
                'pattern': 'practice_scene'
            }
        ]
        
        # 注目選手（実在選手）
        trending_players = ['牧秀悟', '戸柱恭孝', '京田陽太']
        
        # ポジティブハイライト
        positive_highlights = [
            'キャプテン牧の統率力',
            'ベテラン戸柱の経験',
            '京田の守備力',
            'チーム一丸の取り組み',
            'ファンとの絆'
        ]
        
        return {
            'recent_news': sample_news,
            'trending_players': trending_players,
            'team_situation': f"最新のベイスターズ情報{len(sample_news)}件を収集（サンプルデータ）",
            'positive_highlights': positive_highlights,
            'data_source': 'yahoo_sports_scraping'
        }

class ContentGenerationAgent(MCPAgent):
    """コンテンツ生成エージェント"""
    
    def __init__(self):
        super().__init__("ContentGeneration")
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """記事コンテンツを生成"""
        
        self.logger.info("Starting content generation...")
        
        collected_data = context.get('collected_data', {})
        
        # 日本時間で現在の時刻と時間帯を取得
        jst = pytz.timezone('Asia/Tokyo')
        now_jst = datetime.now(jst)
        today_jp = now_jst.strftime('%Y年%m月%d日')
        current_hour = now_jst.hour
        
        # 時間帯を判定（9時頃なら朝、21時頃なら夜）
        if 6 <= current_hour <= 12:
            time_period = "morning"
            time_greeting = "おはようございます"
        else:
            time_period = "evening"  
            time_greeting = "お疲れ様です"
        
        self.logger.info(f"Current JST time: {now_jst.strftime('%H:%M')}, Period: {time_period}")
        
        # 1. コンテキスト分析（時間帯情報を追加）
        content_context = self._analyze_context(collected_data, time_period, time_greeting)
        
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
    
    def _analyze_context(self, collected_data: Dict[str, Any], time_period: str, time_greeting: str) -> Dict[str, Any]:
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
            'generation_style': 'player_focused_positive',  # 選手中心のポジティブ記事
            'game_context': game_info,  # GPT-4oからの情報を追加
            'time_period': time_period,  # 朝/夜の時間帯情報
            'time_greeting': time_greeting  # 時間帯に応じた挨拶
        }
    
    async def _generate_article(self, today_jp: str, context: Dict[str, Any]) -> str:
        """Claude APIを使用して記事を生成"""
        
        try:
            api_key = self._get_claude_api_key()
            self.logger.info(f"Claude API key retrieved: {api_key[:10]}..." if api_key else "No API key")
            
            if api_key == 'test-key' or not api_key:
                self.logger.warning("Using mock article due to missing/invalid API key")
                return self._generate_mock_article(today_jp, context)
            
            # Anthropicライブラリの代わりに直接HTTP APIを呼び出し
            import json
            import urllib.request
            import urllib.parse
            
            prompt = self._build_advanced_prompt(today_jp, context)
            self.logger.info(f"Prompt length: {len(prompt)} characters")
            
            # Claude API直接呼び出し
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            
            data = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=headers
            )
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                
            generated_content = result['content'][0]['text']
            self.logger.info(f"Claude generated article: {len(generated_content)} characters")
            return generated_content
            
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
        
        # GPT-4oから収集した最新ニュース情報を統合
        news_context = ""
        recent_news_context = ""
        
        if game_context.get('data_source') == 'gpt4o_news_search':
            # GPT-4oからの情報を使用
            recent_news = game_context.get('recent_news', [])
            team_situation = game_context.get('team_situation', '')
            positive_highlights = game_context.get('positive_highlights', [])
            
            if recent_news:
                news_items = []
                for news_item in recent_news[:3]:  # 最新3件
                    headline = news_item.get('headline', '')
                    key_facts = ', '.join(news_item.get('key_facts', []))
                    mentioned_players = ', '.join(news_item.get('mentioned_players', []))
                    news_items.append(f"・{headline}（{key_facts}）{mentioned_players}")
                
                recent_news_context = f"""
最近のベイスターズニュース:
{chr(10).join(news_items)}

チーム状況: {team_situation}
注目ポイント: {', '.join(positive_highlights)}"""
        
        elif game_context.get('data_source') == 'comprehensive_rss':
            # 推し選手個別検索 + 全体検索の情報を使用
            recent_news = game_context.get('recent_news', [])
            team_situation = game_context.get('team_situation', '')
            positive_highlights = game_context.get('positive_highlights', [])
            trending_players = game_context.get('trending_players', [])
            collection_summary = game_context.get('collection_summary', {})
            player_specific_news = game_context.get('player_specific_news', {})
            general_news = game_context.get('general_news', [])
            featured_players = game_context.get('featured_players', [])
            
            if recent_news:
                # 推し選手別ニュースを整理
                player_news_sections = []
                for player in featured_players:
                    player_articles = player_specific_news.get(player, [])
                    if player_articles:
                        player_section = f"""
【{player}選手の最新ニュース】:"""
                        for i, article in enumerate(player_articles[:3], 1):
                            headline = article.get('headline', '')
                            source = article.get('source', '')
                            player_section += f"""
{i}. {headline}（{source}）"""
                        player_news_sections.append(player_section)
                
                # 全体ニュース
                general_section = ""
                if general_news:
                    general_section = f"""
【ベイスターズ全体ニュース】:"""
                    for i, news in enumerate(general_news[:3], 1):
                        headline = news.get('headline', '')
                        source = news.get('source', '')
                        general_section += f"""
{i}. {headline}（{source}）"""
                
                recent_news_context = f"""
🎯 推し選手個別検索 + ベイスターズ全体検索結果:
{chr(10).join(player_news_sections)}
{general_section}

📊 収集サマリー:
- 推し選手記事: {collection_summary.get('player_articles_count', 0)} 件
- 全体記事: {collection_summary.get('general_articles_count', 0)} 件
- 合計: {collection_summary.get('total_articles', 0)} 件

チーム状況: {team_situation}
注目選手: {', '.join(featured_players)}
注目ポイント: {', '.join(positive_highlights)}"""
        
        elif game_context.get('data_source') == 'google_news_rss':
            # 旧システム対応（後方互換性）
            recent_news = game_context.get('recent_news', [])
            team_situation = game_context.get('team_situation', '')
            positive_highlights = game_context.get('positive_highlights', [])
            trending_players = game_context.get('trending_players', [])
            collection_summary = game_context.get('collection_summary', '')
            
            if recent_news:
                news_items = []
                for news_item in recent_news[:5]:
                    headline = news_item.get('headline', '')
                    source = news_item.get('source', '')
                    if headline and len(headline) > 10:
                        news_items.append(f"・{headline}（{source}）")
                
                recent_news_context = f"""
Google News RSSから収集した最新ベイスターズ情報:
{chr(10).join(news_items)}

チーム状況: {team_situation}
注目選手・キーワード: {', '.join(trending_players)}
注目ポイント: {', '.join(positive_highlights)}

{collection_summary}"""
        
        elif game_context.get('data_source') == 'yahoo_sports_scraping':
            # Yahoo!スポーツスクレイピングからの情報を使用（旧システム対応）
            recent_news = game_context.get('recent_news', [])
            team_situation = game_context.get('team_situation', '')
            positive_highlights = game_context.get('positive_highlights', [])
            trending_players = game_context.get('trending_players', [])
            
            if recent_news:
                news_items = []
                for news_item in recent_news[:5]:  # 最新5件
                    title = news_item.get('title', '')
                    source = news_item.get('source', '')
                    if title and len(title) > 10:
                        news_items.append(f"・{title}（{source}）")
                
                recent_news_context = f"""
Yahoo!スポーツから収集した最新ベイスターズ情報:
{chr(10).join(news_items)}

チーム状況: {team_situation}
注目選手: {', '.join(trending_players)}
注目ポイント: {', '.join(positive_highlights)}"""
        
        # 従来のニュース情報もバックアップとして使用
        if news and not recent_news_context:
            news_context = f"最近のチーム状況: {news[0]}"
        
        # 時間帯情報を取得
        time_period = context.get('time_period', 'morning')
        time_greeting = context.get('time_greeting', 'おはようございます')
        
        # 時間帯に応じた記事の導入を調整
        time_context = {
            'morning': '新しい一日の始まりと共に、ベイスターズの話題をお届けします',
            'evening': '今日一日の締めくくりに、ベイスターズの最新情報をお楽しみください'
        }.get(time_period, '今日もベイスターズの話題をお届けします')
        
        prompt = f"""あなたは横浜DeNAベイスターズの知識豊富で情熱的なファンライターです。
{time_greeting}！{today_jp}のベイスターズについて、{theme_instruction}1000-1200文字の高品質な記事を書いてください。
{time_context}。

コンテキスト情報:
{player_context}
{recent_news_context if recent_news_context else news_context}

記事の要件:
- Markdown形式（# タイトルから開始）
- ベテランスポーツライター級の文章力で執筆
- **最新ニュース情報を記事の主軸にして構成してください**
- 収集された各ニュース項目について具体的に言及し、詳しく解説
- ニュースに関連する選手や出来事を中心に記事を展開
- 話題になっているトピック（スポンサー契約、トレード、試合情報など）を詳しく紹介
- ニュースの背景や意義、ファンへの影響を分析的に解説
- 注目選手については、ニュースと関連付けて自然に紹介
- ベイスターズファンが知りたい最新情報を網羅的にカバー
- 臨場感のある描写（球場の雰囲気、ファンの反応など）
- ハマスタの特別感やファンの熱気も表現
- 読み応えのある内容で、最新情報に基づいた価値ある記事

文体の特徴:
- プロのスポーツライター風の知的で洗練された表現
- 適度な専門用語（野球用語）を自然に織り込む
- ファンの心を掴む感動的なフレーズ
- ニュース解説と応援記事のバランス

重要な指示: 
- **【最優先】推し選手3名を中心とした記事にしてください**
- 各推し選手について収集された最新ニュースを詳しく解説してください
- 推し選手の活躍、成長、努力、魅力を具体的に褒めてください
- 推し選手に関するニュースが最も重要で、必ず全員について言及してください
- ベイスターズ全体のニュースも補完的に使用してください
- 選手個人のエピソード、プレースタイル、人柄を詳しく紹介
- 選手の最新の状況や話題を正確に反映してください
- ファンが推し選手について新しい情報を得られる記事にしてください
- 具体的な試合結果、スコア、勝敗には触れないでください
- 推し選手3名全員が記事に反映されていない場合は失格です"""
        
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
            score += 1.5  # タイトルあり
        
        # 文字数による評価（より高品質な記事を期待）
        if 800 <= len(content) <= 1500:
            score += 2.5  # 理想的な長さ
        elif 500 <= len(content) < 800:
            score += 1.5  # 最低限の長さ
        elif len(content) >= 1500:
            score += 2.0  # 長い記事も評価
        
        if 'ベイスターズ' in content:
            score += 1.0  # チーム名言及
        
        # 選手名の幅広いチェック（2025年ロスター）
        player_mentions = sum(1 for player in ['佐野', '牧', '宮崎', '松尾', '森', '関根', '神里', '桑原', '細川', 
                                             '大田', '知野', '林', '上茶', '蛯名', '東', '今永', '大貫', 'ジャクソン', 
                                             'バウアー', '石田', '平良', '入江', '伊勢', '山崎', 'ウェンデルケン'] 
                             if player in content)
        score += min(player_mentions * 0.8, 2.0)  # 選手言及（複数でボーナス）
        
        if content.endswith(('！', '。', '💪', '⚾')):
            score += 0.5  # 適切な終わり方
        
        # ポジティブ表現の幅広いチェック
        positive_words = ['頑張', '応援', '最高', '素晴らしい', '期待', '魅力', '輝', '活躍', '努力', '情熱']
        positive_count = sum(1 for word in positive_words if word in content)
        score += min(positive_count * 0.3, 2.0)
        
        # プロフェッショナルな表現
        if any(phrase in content for phrase in ['ハマスタ', 'プレースタイル', 'チーム一丸', '球場', '打席']):
            score += 1.0  # 専門的な表現
        
        # 段落構成（改行による）
        paragraphs = len([p for p in content.split('\n\n') if p.strip()])
        if paragraphs >= 3:
            score += 1.0  # 良い構成
        
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
            # S3に記事を保存（時間帯別ファイル名）
            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.now(jst)
            today = now_jst.strftime('%Y-%m-%d')
            time_suffix = "morning" if 6 <= now_jst.hour <= 12 else "evening"
            
            bucket_name = os.environ['S3_BUCKET_NAME']
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'articles/{today}-{time_suffix}.md',
                Body=result['final_article'].encode('utf-8'),
                ContentType='text/markdown',
                Metadata={
                    'generated-by': 'mcp-orchestrator',
                    'quality-score': str(result['quality_score']),
                    'generation-time': result['pipeline_execution_time'],
                    'time-period': time_suffix
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