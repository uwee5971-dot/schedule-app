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

# Slack IDを名前に変換するためのマッピングを作成
def get_id_to_name_map():
    df_members = load_data("members")
    # {SlackID: 名前} の辞書を作る
    return dict(zip(df_members['slack_id'], df_members['name']))

# IDのカンマ区切り文字列を名前のカンマ区切りに変換
def convert_ids_to_names(id_str, name_map):
    if pd.isna(id_str) or id_str == "":
        return ""
    ids = str(id_str).split(",")
    names = [name_map.get(sid.strip(), sid.strip()) for sid in ids if sid.strip()]
    return ", ".join(names)

# イベント登録時に出欠アンケートを送信する関数
def send_attendance_poll(event_id, event_name, date_str):
    if "slack_token" not in st.secrets:
        return None
    token = st.secrets["slack_token"]
    channel = "#random" # 通知を飛ばす実際のチャンネル名に合わせてください
    
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📢 新しいイベントが登録されました"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*イベント名*: {event_name}\n*開催日*: {date_str}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "出欠を回答してください。ボタンを押すと自動で集計されます。"}},
        {
            "type": "actions",
            "elements": [
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
# 💡「メンバー管理」をメニューから削除しました！
menu = st.sidebar.selectbox("メニューを選択", ["イベント一覧", "イベント登録"])

# --- 1. イベント一覧 ---
if menu == "イベント一覧":
    st.header("📋 登録済みイベント")
    df_ev = load_data("events")
    
    # IDを名前に変換する処理
    try:
        name_map = get_id_to_name_map()
        display_df = df_ev.copy()
        
        # 列が存在すればIDを名前に変換
        if 'attendees' in display_df.columns:
            display_df['attendees'] = display_df['attendees'].apply(lambda x: convert_ids_to_names(x, name_map))
        if 'absentees' in display_df.columns:
            display_df['absentees'] = display_df['absentees'].apply(lambda x: convert_ids_to_names(x, name_map))
        
        # 💡 日本語の分かりやすい列名に変更
        rename_dict = {
            "date": "開催日",
            "event_name": "イベント名",
            "location": "場所",
            "status": "ステータス",
            "attendees": "出席者",
            "absentees": "欠席者"
        }
        display_df = display_df.rename(columns=rename_dict)
        
        # 💡 ユーザーに見せる必要のない内部用ID（event_id）や、催促フラグ（remind_all）を画面上だけ非表示に！
        show_columns = ["開催日", "イベント名", "場所", "ステータス", "出席者", "欠席者"]
        # スプレッドシート側の列が足りない場合のエラーを防ぎつつ、存在する列だけを絞り込む
        existing_show_columns = [col for col in show_columns if col in display_df.columns]
        
        st.dataframe(display_df[existing_show_columns], use_container_width=True)
        
    except Exception as e:
        st.error(f"表示変換中にエラーが発生しました。スプレッドシートの項目を確認してください: {e}")
        st.dataframe(df_ev, use_container_width=True)

# --- 2. イベント登録 ---
elif menu == "イベント登録":
    st.header("📝 新規イベントの作成")
    
    with st.form("event_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("開催日", datetime.now())
            event_name = st.text_input("イベント名", placeholder="例：月例ゼミ")
        with col2:
            location = st.text_input("場所", placeholder="例：第1会議室")
            status = st.selectbox("ステータス", ["確定", "企画中"])
            
        # 前日リマインド時に催促メッセージをオン/オフするチェックボックス
        remind_all = st.checkbox("前日リマインド時に、出欠未回答者への催促も含める", value=True)
        
        if st.form_submit_button("イベントを登録してSlackに通知"):
            if event_name:
                try:
                    df_ev = load_data("events")
                    new_id = f"e{len(df_ev) + 1:03}"
                    date_str = date.strftime('%Y-%m-%d')
                    
                    # 新規行作成（スプシの裏側には、これまで通りevent_idやremind_allをしっかり保存）
                    new_row = pd.DataFrame([{
                        "event_id": new_id,
                        "date": date_str,
                        "event_name": event_name,
                        "location": location,
                        "status": status,
                        "attendees": "",
                        "absentees": "",
                        "remind_all": "TRUE" if remind_all else "FALSE"
                    }])
                    
                    update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                    
                    # 出欠確認用のボタン付き通知をSlackへ送信
                    slack_res = send_attendance_poll(new_id, event_name, date_str)
                    
                    if slack_res and slack_res.status_code == 200:
                        st.success(f"「{event_name}」を登録し、Slackに出欠アンケートを送信しました！")
                    else:
                        st.warning("イベントは登録されましたが、Slackへの初期通知に失敗しました。")
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
            else:
                st.error("イベント名を入力してください。")
