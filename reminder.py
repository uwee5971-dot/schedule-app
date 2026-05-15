import pandas as pd
import requests
from datetime import datetime, timedelta
import os

# GitHub Actionsで実行するため、環境変数からシークレットを取得
SLACK_TOKEN = os.environ["SLACK_TOKEN"]
SPREADSHEET_URL = os.environ["SPREADSHEET_URL"]

def load_data_from_url(worksheet_name):
    # CSVエクスポート形式のURLに変換して読み込む
    base_url = SPREADSHEET_URL.replace("/edit?usp=sharing", "/export?format=csv")
    # シート名(タブ名)によってgidを指定（eventsシートを一番左と想定）
    # 実際の設定に合わせて調整が必要な場合があります
    url = f"{base_url}&sheet={worksheet_name}"
    return pd.read_csv(url)

def send_reminder():
    # 明日の日付を取得
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    try:
        df_ev = load_data_from_url("events")
        # 明日のイベントを検索
        upcoming_events = df_ev[df_ev['date'] == tomorrow]
        
        if upcoming_events.empty:
            print(f"No events found for {tomorrow}")
            return

        for _, event in upcoming_events.iterrows():
            mentions = []
            if pd.notna(event['attendees']) and event['attendees'] != "":
                mentions = [f"<@{sid.strip()}>" for sid in str(event['attendees']).split(',')]
            
            mention_text = " ".join(mentions) if mentions else "参加予定の皆さん"
            
            message = (
                f"🌙 *明日開催のイベントリマインド*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📅 *イベント*: {event['event_name']}\n"
                f"📍 *場所*: {event['location']}\n"
                f"👤 *対象*: {mention_text}\n\n"
                f"明日の21時になりました。準備は大丈夫ですか？"
            )
            
            requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
                json={"channel": "#general", "text": message}
            )
            print(f"Sent reminder for: {event['event_name']}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    send_reminder()