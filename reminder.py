import pandas as pd
import requests
from datetime import datetime, timedelta
import os

# GitHub ActionsのSecretsから取得
SLACK_TOKEN = os.environ["SLACK_TOKEN"]
SPREADSHEET_URL = os.environ["SPREADSHEET_URL"]

def load_sheet_as_csv(worksheet_name):
    # スプレッドシートをCSV形式で取得するためのURL変換
    file_id = SPREADSHEET_URL.split("/d/")[1].split("/")[0]
    
    # eventsは最初のタブ(gid=0)、membersは確認した実際のIDを指定
    gid_map = {"events": "0", "members": "1994409943"} 
    
    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={gid_map.get(worksheet_name, '0')}"
    return pd.read_csv(url)

def send_reminder():
    # 日本時間で翌日の日付を取得
    tomorrow = (datetime.now() + timedelta(hours=9) + timedelta(days=1)).strftime('%Y-%m-%d')
    
    try:
        # データの読み込み
        df_ev = load_sheet_as_csv("events")
        df_members = load_sheet_as_csv("members")
        
        # 明日の予定を抽出（日付フォーマットを統一）
        df_ev['date'] = pd.to_datetime(df_ev['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        upcoming_events = df_ev[df_ev['date'] == tomorrow]
        
        if upcoming_events.empty:
            print(f"No events found for {tomorrow}")
            return

        for _, event in upcoming_events.iterrows():
            # 出席者のリスト化
            attendees_raw = str(event['attendees']) if pd.notna(event['attendees']) else ""
            attendee_ids = [sid.strip() for sid in attendees_raw.split(",") if sid.strip()]
            
            # 欠席者のリスト化
            absentees_raw = str(event['absentees']) if pd.notna(event['absentees']) else ""
            absentee_ids = [sid.strip() for sid in absentees_raw.split(",") if sid.strip()]
            
            # 💡【ここを修正！】スプシで「1」や「1.0」や「TRUE」になっていても、確実にオン(True)と判定する
            remind_val = str(event.get('remind_all', 'TRUE')).upper()
            is_remind_all = remind_val in ['TRUE', '1', '1.0']

            # メッセージの土台構築
            msg_blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": "⏰ 明日のイベントリマインド"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*イベント名*: {event['event_name']}\n*場所*: {event['location']}"}}
            ]

            # 1. 出席予定者への最終確認（これは常に送る）
            if attendee_ids:
                mentions = " ".join([f"<@{sid}>" for sid in attendee_ids])
                msg_blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"✅ *出席予定の皆様*\n{mentions}\n明日はよろしくお願い致します！"}
                })

            # 2. 未回答者への催促（is_remind_all が True の場合のみ実行）
            if is_remind_all:
                all_member_ids = df_members['slack_id'].astype(str).tolist()
                no_response_ids = [mid for mid in all_member_ids if mid not in attendee_ids and mid not in absentee_ids]
                
                if no_response_ids:
                    unresponded_mentions = " ".join([f"<@{sid}>" for sid in no_response_ids])
                    msg_blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"❓ *出欠未回答の皆様*\n{unresponded_mentions}\nまだ回答がありません。回答をお願い致します！"}
                    })

            # Slack送信
            res = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
                json={"channel": "#random", "blocks": msg_blocks}
            )
            print(f"Slack API Response: {res.json()}") 
            print(f"Reminder sent for {event['event_name']} (Remind All: {is_remind_all})")

    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    send_reminder()
