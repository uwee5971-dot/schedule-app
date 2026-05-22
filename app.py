import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, time
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
    return dict(zip(df_members['slack_id'], df_members['name']))

# IDのカンマ区切り文字列を名前のカンマ区切りに変換
def convert_ids_to_names(id_str, name_map):
    if pd.isna(id_str) or id_str == "":
        return ""
    ids = str(id_str).split(",")
    names = [name_map.get(sid.strip(), sid.strip()) for sid in ids if sid.strip()]
    return ", ".join(names)

# 場所にURLリンクを綺麗に埋め込む関数
def format_location(location, url):
    if pd.isna(location) or location == "":
        return ""
    if pd.notna(url) and str(url).strip() != "":
        return f"[{location}]({str(url).strip()})"
    return location

# イベント登録時に出欠アンケートを送信する関数
def send_attendance_poll(event_id, event_name, date_str, time_str, location, location_url):
    if "slack_token" not in st.secrets:
        return None
    token = st.secrets["slack_token"]
    channel = "#random" # 実際の通知先チャンネル名に合わせてください
    
    loc_text = f"<{location_url}|{location}>" if location_url else location
    
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📢 新しいイベントが登録されました"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*イベント名*: {event_name}\n*開催日時*: {date_str} {time_str}\n*場所*: {loc_text}"}},
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
menu = st.sidebar.selectbox("メニューを選択", ["イベント一覧", "イベント登録", "アーカイブ"])

# --- 1. イベント一覧 ---
if menu == "イベント一覧":
    st.header("📋 これからのイベント")
    
    # 過去イベントをアーカイブする機能
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🗑️ 過去イベントをアーカイブ"):
            try:
                df_ev = load_data("events")
                df_hist = load_data("history")
                
                # 今日の日付を取得
                today_str = datetime.now().strftime('%Y-%m-%d')
                
                # 今日の日付より前のものをアーカイブ対象とする
                mask = df_ev['date'].astype(str) < today_str
                past_events = df_ev[mask]
                upcoming_events = df_ev[~mask]
                
                if not past_events.empty:
                    new_history = pd.concat([df_hist, past_events], ignore_index=True)
                    update_data("history", new_history)
                    update_data("events", upcoming_events)
                    st.success(f"{len(past_events)}件のイベントをアーカイブしました！")
                    st.rerun()
                else:
                    st.info("アーカイブする過去のイベントはありません。")
            except Exception as e:
                st.error(f"エラーが発生しました。historyシートが存在するか確認してください: {e}")

    df_ev = load_data("events")
    
    try:
        name_map = get_id_to_name_map()
        display_df = df_ev.copy()
        
        # 出席者・欠席者のIDを名前に変換
        if 'attendees' in display_df.columns:
            display_df['attendees'] = display_df['attendees'].apply(lambda x: convert_ids_to_names(x, name_map))
        if 'absentees' in display_df.columns:
            display_df['absentees'] = display_df['absentees'].apply(lambda x: convert_ids_to_names(x, name_map))
        
        # 場所のURLリンク化
        if 'location' in display_df.columns and 'url' in display_df.columns:
            display_df['location'] = display_df.apply(lambda row: format_location(row['location'], row['url']), axis=1)
        
        rename_dict = {
            "date": "開催日",
            "time": "時間",
            "event_name": "イベント名",
            "location": "場所",
            "status": "ステータス",
            "attendees": "出席者",
            "absentees": "欠席者"
        }
        display_df = display_df.rename(columns=rename_dict)
        
        show_columns = ["開催日", "時間", "イベント名", "場所", "ステータス", "出席者", "欠席者"]
        existing_show_columns = [col for col in show_columns if col in display_df.columns]
        
        st.dataframe(
            display_df[existing_show_columns], 
            use_container_width=True,
            column_config={"場所": st.column_config.LinkColumn("場所")}
        )
        
    except Exception as e:
        st.error(f"表示変換中にエラーが発生しました: {e}")
        st.dataframe(df_ev, use_container_width=True)

# --- 2. イベント登録 ---
elif menu == "イベント登録":
    st.header("📝 新規イベントの作成")
    
    with st.form("event_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("開催日", datetime.now())
            t_start = st.time_input("開始時間", time(10, 0))
            t_end = st.time_input("終了時間", time(11, 30))
            event_name = st.text_input("イベント名", placeholder="例：月例ゼミ")
        with col2:
            location = st.text_input("場所", placeholder="例：第1会議室、Zoom")
            location_url = st.text_input("場所のURLリンク（任意）", placeholder="例：https://zoom.us/j/...")
            status = st.selectbox("ステータス", ["確定", "企画中"])
            
        remind_all = st.checkbox("前日リマインド時に、出欠未回答者への催促も含める", value=True)
        
        if st.form_submit_button("イベントを登録してSlackに通知"):
            if event_name:
                try:
                    df_ev = load_data("events")
                    
                    # historyシートが存在しない場合の初回エラーを防ぐ
                    try:
                        df_hist = load_data("history")
                        hist_len = len(df_hist)
                    except:
                        hist_len = 0
                        
                    new_id = f"e{len(df_ev) + hist_len + 1:03}" 
                    date_str = date.strftime('%Y-%m-%d')
                    time_str = f"{t_start.strftime('%H:%M')} - {t_end.strftime('%H:%M')}"
                    
                    new_row = pd.DataFrame([{
                        "event_id": new_id,
                        "date": date_str,
                        "time": time_str,
                        "event_name": event_name,
                        "location": location,
                        "url": location_url,
                        "status": status,
                        "attendees": "",
                        "absentees": "",
                        "remind_all": "TRUE" if remind_all else "FALSE"
                    }])
                    
                    update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                    
                    slack_res = send_attendance_poll(new_id, event_name, date_str, time_str, location, location_url)
                    
                    if slack_res and slack_res.status_code == 200:
                        st.success(f"「{event_name}」を登録し、Slackに出欠アンケートを送信しました！")
                    else:
                        st.warning("イベントは登録されましたが、Slackへの初期通知に失敗しました。")
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
            else:
                st.error("イベント名を入力してください。")

# --- 3. アーカイブ ---
elif menu == "アーカイブ":
    st.header("📁 過去のイベント履歴")
    try:
        df_hist = load_data("history")
        if df_hist.empty:
            st.info("アーカイブされたイベントはまだありません。")
        else:
            name_map = get_id_to_name_map()
            display_df = df_hist.copy()
            
            if 'attendees' in display_df.columns:
                display_df['attendees'] = display_df['attendees'].apply(lambda x: convert_ids_to_names(x, name_map))
            if 'absentees' in display_df.columns:
                display_df['absentees'] = display_df['absentees'].apply(lambda x: convert_ids_to_names(x, name_map))
            
            if 'location' in display_df.columns and 'url' in display_df.columns:
                display_df['location'] = display_df.apply(lambda row: format_location(row['location'], row['url']), axis=1)
            
            rename_dict = {
                "date": "開催日",
                "time": "時間",
                "event_name": "イベント名",
                "location": "場所",
                "status": "ステータス",
                "attendees": "出席者",
                "absentees": "欠席者"
            }
            display_df = display_df.rename(columns=rename_dict)
            
            show_columns = ["開催日", "時間", "イベント名", "場所", "ステータス", "出席者", "欠席者"]
            existing_show_columns = [col for col in show_columns if col in display_df.columns]
            
            display_df = display_df.sort_values(by="開催日", ascending=False)
            
            st.dataframe(
                display_df[existing_show_columns], 
                use_container_width=True,
                column_config={"場所": st.column_config.LinkColumn("場所")}
            )
    except Exception as e:
        st.error(f"履歴の読み込みに失敗しました。historyシートが存在するか確認してください: {e}")
