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

def load_data(worksheet_name):
    # SecretsからURLを取得し、末尾をエクスポート形式に強制変換して読み込む
    base_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    # URLに /export が含まれていない場合は変換
    if "/edit" in base_url:
        url = base_url.split("/edit")[0] + f"/gviz/tq?tqx=out:csv&sheet={worksheet_name}"
    else:
        url = base_url
    return pd.read_csv(url)

def update_data(worksheet_name, df):
    # 更新時は標準のコネクションを使用
    conn.update(worksheet=worksheet_name, data=df)

def send_attendance_poll(event_name, date_str):
    token = st.secrets["slack_token"]
    channel = "#general" 
    
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

# --- メニュー構成 ---
menu = st.sidebar.selectbox("メニューを選択", ["イベント登録", "イベント一覧", "メンバー管理"])

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
        
        if st.form_submit_button("イベントを登録する"):
            if event_name:
                try:
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
                    
                    update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                    slack_res = send_attendance_poll(event_name, date_str)
                    st.success(f"イベント「{event_name}」を登録しました！")
                except Exception as e:
                    st.error(f"接続エラーが発生しました。スプレッドシートの共有設定が『編集者』になっているか確認してください: {e}")
            else:
                st.error("イベント名を入力してください。")

elif menu == "イベント一覧":
    st.header("📋 登録済みイベント")
    try:
        df_ev = load_data("events")
        st.dataframe(df_ev, use_container_width=True)
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")

else:
    st.header("⚙️ メンバー管理")
    st.info("メンバー管理機能（開発中）")
