import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import requests

def send_attendance_poll(event_name, date_str):
    token = st.secrets["slack_token"]
    channel = "#general"  # 実際にアプリを招待したチャンネル名に合わせてください
    
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"📢 *新イベントのお知らせ*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"📅 *イベント名*: {event_name}\n🗓 *日付*: {date_str}\n\n出欠を教えてください！"}},
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "出席"}, "value": "attend", "style": "primary", "action_id": "attend_btn"},
                {"type": "button", "text": {"type": "plain_text", "text": "欠席"}, "value": "absent", "style": "danger", "action_id": "absent_btn"}
            ]
        }
    ]
    
    res = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "blocks": blocks}
    )
    return res

# --- アプリ基本設定 ---
st.set_page_config(page_title="📅研究室イベント管理", layout="wide")
st.title("📅 研究室イベント管理")

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name):
    return conn.read(worksheet=worksheet_name, ttl=0)

def update_data(worksheet_name, df):
    conn.update(worksheet=worksheet_name, data=df)

# --- メニュー構成 ---
menu = st.sidebar.selectbox("メニューを選択", ["イベント登録", "イベント一覧", "メンバー管理"])

# --- 1. イベント登録 ---
if menu == "イベント登録":
    st.header("📝 新規イベントの作成")
    
    with st.form("event_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("開催日", datetime.now())
            event_name = st.text_input("イベント名", placeholder="例：月例ゼミ、打ち上げ")
        with col2:
            location = st.text_input("場所", placeholder="例：第1会議室、Zoom")
            status = st.selectbox("ステータス", ["企画中", "確定"])
        
        description = st.text_area("備考", placeholder="持ち物や詳細など")

        if st.form_submit_button("イベントを登録する"):
            if event_name:
                df_ev = load_data("events")
                new_id = f"e{len(df_ev) + 1:03}"
                date_str = date.strftime('%Y-%m-%d')
                
                new_row = pd.DataFrame([{
                    "event_id": new_id,
                    "date": date_str,
                    "event_name": event_name,
                    "location": location,
                    "status": status,
                    "attendees": "",
                    "absentees": ""
                }])
                
                # 1. スプレッドシート更新
                update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                
                # 2. Slackへ通知を飛ばす（ここを追加しました！）
                slack_res = send_attendance_poll(event_name, date_str)
                
                if slack_res.status_code == 200:
                    st.success(f"イベント「{event_name}」を登録し、Slackに通知しました！")
                else:
                    st.warning("イベントは登録されましたが、Slack通知に失敗しました。トークンやチャンネル名を確認してください。")
            else:
                st.error("イベント名を入力してください。")

elif menu == "イベント一覧":
    st.header("📋 登録済みイベント")
    df_ev = load_data("events")
    st.dataframe(df_ev, use_container_width=True)

else:
    st.header("⚙️ メンバー管理")
    st.info("精算ツールのメンバーリストと同期するか、新しく登録する機能をここに追加します。")