#!/usr/bin/env python3
"""
選手選択ロジックの単体テスト用スクリプト
"""

import sys
import os
import random
from datetime import datetime
import pytz

# 2025年シーズンの実際の一軍登録選手
current_players = {
    'pitchers': ['東克樹', '伊勢大夢', '大貫晋一', 'バウアー', 'ジャクソン', '宮城滝太', '坂本裕哉', '森原康平', '颯', '石田裕太郎', '中川虎大', '松本凌人', '若松尚輝', '入江大生', 'ケイ', 'ウィック'],
    'catchers': ['松尾汐恩', '戸柱恭孝', '山本祐大'],
    'infielders': ['牧秀悟', '宮﨑敏郎', '京田陽太', '井上絢登', 'フォード', '柴田竜拓', '林琢真', '石上泰輝'],
    'outfielders': ['佐野恵太', '桑原将志', '神里和毅', '関根大気', '蝦名達夫', '筒香嘉智']
}

def select_featured_players(roster, mock_hour=None, time_period=None):
    """今日注目する選手をスマートに選択（3名、時間帯別対応）"""
    
    # 日本時間で現在の時刻を取得（モック時間対応）
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    
    # モック時間の適用
    if mock_hour is not None:
        print(f"🕐 モック時間を使用: {mock_hour}時")
        current_hour = mock_hour
    else:
        current_hour = now_jst.hour
    
    # 時間帯を判定（引数で指定されていない場合）
    if not time_period:
        time_period = "morning" if 6 <= current_hour <= 12 else "evening"
    
    # 時間帯別のシード値を生成（時間の影響を強力に）
    base_seed = now_jst.day + now_jst.month + now_jst.year
    
    # 時間帯による強力な分離（朝と夜で完全に異なる選手群）
    if time_period == "morning":
        time_factor = current_hour * 17  # 朝の時間を強力に反映
    else:
        time_factor = current_hour * 29  # 夜の時間を強力に反映（異なる係数）
    
    weather_factor = (now_jst.day * 7) % 13  # 天気っぽいランダム要素
    season_factor = (now_jst.month - 1) // 3  # 季節要素（0-3）
    lunar_cycle = now_jst.day % 28  # 月齢っぽいサイクル
    
    # 時間帯を含む複合シード（時間要素を最重要視）
    final_seed = base_seed + time_factor + weather_factor + season_factor + lunar_cycle
    random.seed(final_seed)
    
    print(f"🎯 選手選択 - 時間帯: {time_period} ({current_hour}時), 最終シード: {final_seed}")
    print(f"   📊 シード計算: base={base_seed} + time={time_factor} + weather={weather_factor} + season={season_factor} + lunar={lunar_cycle}")
    
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
        print(f"   🌅 時間帯重視選択: {time_boost_position}")
    else:
        primary_position = weekday_position
        print(f"   📅 曜日重視選択: {weekday_position}")
    
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
        print(f"   🔀 順番シャッフル実行")
    
    print(f"✅ 推し選手決定: {', '.join(selected_players)} ({time_period})")
    
    return selected_players

def main():
    print("🎲 ベイスターズ選手選択テスト")
    print("=" * 50)
    
    # 複数の時間でテスト
    test_hours = [6, 10, 12, 13, 15, 18, 21, 23]
    
    for hour in test_hours:
        print(f"\n⏰ {hour}時のテスト:")
        players = select_featured_players(current_players, mock_hour=hour)
    
    print("\n" + "=" * 50)
    print("🔄 同じ時間で複数回実行（再現性確認）:")
    
    for i in range(3):
        print(f"\n🔁 10時 - 実行 {i+1}:")
        players = select_featured_players(current_players, mock_hour=10)
    
    for i in range(3):
        print(f"\n🔁 21時 - 実行 {i+1}:")
        players = select_featured_players(current_players, mock_hour=21)

if __name__ == "__main__":
    main()