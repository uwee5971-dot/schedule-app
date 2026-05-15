import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import requests

# --- アプリ基本設定 ---
st.set_page_config(page_title="📅研究室イベント管理", layout="wide")
st.title("📅 研究室イベント管理")

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 共通関数 ---
def load_data(worksheet_name):
    return conn.read(worksheet=worksheet_name, ttl=0)

def update_data(worksheet_name, df):
    conn.update(worksheet=worksheet_name, data=df)

def send_attendance_poll(event_id, event_name, date_str): # event_idを追加
    token = st.secrets["slack_token"]
    channel = "#general"
    
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📢 新しいイベントが登録されました"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*イベント名*: {event_name}\n*開催日*: {date_str}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "出欠を回答してください。ボタンを押すと自動で集計されます。"}},
        {
            "type": "actions",
            "elements": [
                # value の中に event_id を埋め込む
                {"type": "button", "text": {"type": "plain_text", "text": "出席"}, "style": "primary", "value": f"{event_id}:attend", "action_id": "attend_btn"},
                {"type": "button", "text": {"type": "plain_text", "text": "欠席"}, "style": "danger", "value": f"{event_id}:absent", "action_id": "absent_btn"}
            ]
        }
    ]
    
    return requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "blocks": blocks}
    )

# --- サイドバーメニュー ---
menu = st.sidebar.selectbox("メニューを選択", ["イベント一覧", "イベント登録", "メンバー管理"])

# --- 1. イベント一覧 ---
if menu == "イベント一覧":
    st.header("📋 登録済みイベント")
    df_ev = load_data("events")
    st.dataframe(df_ev, use_container_width=True)

# --- 2. イベント登録 ---
elif menu == "イベント登録":
    st.header("📝 新規イベントの作成")
    
    with st.form("event_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("開催日", datetime.now())
            event_name = st.text_input("イベント名", placeholder="例：月例ゼミ、打ち上げ")
        with col2:
            location = st.text_input("場所", placeholder="例：第1会議室")
            status = st.selectbox("ステータス", ["確定", "企画中"])
        
        if st.form_submit_button("イベントを登録してSlackに通知"):
            if event_name:
                # データ読み込みとID生成
                df_ev = load_data("events")
                new_id = f"e{len(df_ev) + 1:03}"
                date_str = date.strftime('%Y-%m-%d')
                
                # 新規行作成
                new_row = pd.DataFrame([{
                    "event_id": new_id,
                    "date": date_str,
                    "event_name": event_name,
                    "location": location,
                    "status": status,
                    "attendees": "",
                    "absentees": ""
                }])
                
                # スプレッドシート更新
                update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                
                # Slack通知送信
                slack_res = send_attendance_poll(new_id, event_name, date_str)
                
                if slack_res and slack_res.status_code == 200:
                    st.success(f"「{event_name}」を登録し、Slackに出欠アンケートを送信しました！")
                else:
                    st.warning("イベントは登録されましたが、Slack通知に失敗しました。")
            else:
                st.error("イベント名を入力してください。")

# --- 3. メンバー管理 ---
elif menu == "メンバー管理":
    st.header("⚙️ メンバー管理")
    st.write("研究室メンバーのSlack IDを登録してください。リマインド時のメンションに使用します。")
    
    df_members = load_data("members")
    
    # 編集可能なテーブルを表示
    edited_df = st.data_editor(df_members, num_rows="dynamic", use_container_width=True)
    
    if st.button("メンバーリストを保存"):
        update_data("members", edited_df)
        st.success("メンバーリストを更新しました！")
        st.rerun()

    with st.expander("💡 Slack IDの調べ方"):
        st.write("1. Slackで対象者のプロフィールを表示\n2. 「もっと見る」から「メンバーIDをコピー」を選択\n3. `U`から始まる英数字がIDです。")
