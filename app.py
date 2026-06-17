import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, time, timedelta
import requests
import json

# --- アプリ基本設定 ---
st.set_page_config(page_title="📅研究室イベント管理", layout="wide")
st.title("📅 研究室イベント管理 (日程調整版)")

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 共通関数 ---
def load_data(worksheet_name):
    return conn.read(worksheet=worksheet_name, ttl=0)

def update_data(worksheet_name, df):
    conn.update(worksheet=worksheet_name, data=df)

# イベント登録時に出欠アンケートを送信する関数（敬語化済）
def send_multi_candidate_poll(event_id, event_name, candidates):
    if "slack_token" not in st.secrets:
        return None
    token = st.secrets["slack_token"]
    channel = "#random" # 実際の通知先チャンネル名に合わせて変更する
    
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📢 新しいイベントの日程調整"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*イベント名*: {event_name}\n以下の候補から、参加可能な日時を【すべて】お選びください。"}},
    ]
    
    actions_elements = []
    for i, cand in enumerate(candidates):
        actions_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": cand},
            "value": f"{event_id}:{i}"
        })
    
    if actions_elements:
        blocks.append({"type": "actions", "elements": actions_elements})
    
    return requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "blocks": blocks}
    )

# --- サイドバーメニュー ---
menu = st.sidebar.selectbox("メニューを選択", ["イベント登録", "イベント状況・確定"])

# --- 1. イベント登録 ---
if menu == "イベント登録":
    st.header("📝 新規イベントの日程調整")
    
    col_a, col_b = st.columns(2)
    with col_a:
        event_name = st.text_input("イベント名", placeholder="例：月例ゼミ")
    with col_b:
        target_votes = st.number_input("自動確定の目標票数", min_value=1, value=5, step=1, help="この票数に達した候補日が自動的に確定される。")
    
    st.subheader("候補日時の追加")
    
    if "candidates" not in st.session_state:
        st.session_state.candidates = [{"date": datetime.now().date(), "time": time(10, 0)}]
    
    for i, cand in enumerate(st.session_state.candidates):
        col1, col2 = st.columns(2)
        cand["date"] = col1.date_input(f"候補 {i+1} の日付", cand["date"], key=f"date_{i}")
        cand["time"] = col2.time_input(f"候補 {i+1} の時間", cand["time"], key=f"time_{i}")
    
    if st.button("➕ 候補日を追加する"):
        if len(st.session_state.candidates) < 5:
            st.session_state.candidates.append({"date": datetime.now().date(), "time": time(10, 0)})
            st.rerun()
        else:
            st.warning("Slackの仕様上、一度に送信できる候補は5つまでである。")
    
    st.markdown("---")
    
    if st.button("日程調整アンケートをSlackに送信"):
        if not event_name:
            st.error("イベント名を入力してほしい。")
        else:
            try:
                # 期限の自動計算ロジック
                cand_dates = [c['date'] for c in st.session_state.candidates]
                min_date = min(cand_dates)
                today = datetime.now().date()
                diff_days = (min_date - today).days
                
                if diff_days >= 7:
                    deadline_date = min_date - timedelta(days=7)
                elif diff_days >= 3:
                    deadline_date = min_date - timedelta(days=3)
                else:
                    deadline_date = min_date - timedelta(days=1)
                
                # 計算された期限が過去になってしまう場合は、今日を期限とする
                if deadline_date < today:
                    deadline_date = today
                
                df_ev = load_data("events")
                new_id = f"e{len(df_ev) + 1:03}"
                
                cand_strs = [f"{c['date'].strftime('%Y-%m-%d')} {c['time'].strftime('%H:%M')}" for c in st.session_state.candidates]
                
                new_row = pd.DataFrame([{
                    "event_id": new_id,
                    "event_name": event_name,
                    "candidates": json.dumps(cand_strs),
                    "votes": "{}",
                    "status": "VOTING",
                    "final_choice": "",
                    "target_votes": int(target_votes),
                    "deadline": deadline_date.strftime('%Y-%m-%d')
                }])
                
                update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                slack_res = send_multi_candidate_poll(new_id, event_name, cand_strs)
                
                if slack_res and slack_res.status_code == 200:
                    st.success(f"「{event_name}」の候補を登録し、Slackにアンケートを送信した！ (自動確定期限: {deadline_date.strftime('%Y-%m-%d')})")
                    st.session_state.candidates = [{"date": datetime.now().date(), "time": time(10, 0)}]
                else:
                    st.warning("登録は完了したが、Slackへの送信に失敗した。")
            except Exception as e:
                st.error(f"エラーが発生した: {e}")

# --- 2. イベント状況・確定 ---
elif menu == "イベント状況・確定":
    st.header("📋 現在の投票状況と日程確定")
    
    try:
        df_ev = load_data("events")
        
        if df_ev.empty:
            st.info("現在登録されているイベントはない。")
        else:
            for index, row in df_ev.iterrows():
                candidates = json.loads(row['candidates']) if pd.notna(row['candidates']) else []
                
                votes_str = row['votes']
                votes = {}
                if pd.notna(votes_str) and str(votes_str).strip() != "":
                    try:
                        votes = json.loads(votes_str)
                    except:
                        pass
                
                status_mark = "🟢 投票中" if row['status'] == "VOTING" else "🔴 確定済"
                st.subheader(f"{status_mark} : {row['event_name']}")
                
                if row['status'] == "VOTING":
                    st.write(f"自動確定の目標: **{row['target_votes']}票** / 期限: **{row['deadline']}**")
                
                st.markdown("**【得票状況】**")
                for i, cand in enumerate(candidates):
                    voters = votes.get(str(i), [])
                    st.markdown(f"* **{cand}** : {len(voters)} 票")
                
                if row['status'] == "VOTING":
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        selected_idx = st.selectbox(
                            "どの日程で確定するか選択", 
                            range(len(candidates)), 
                            format_func=lambda x: candidates[x], 
                            key=f"sel_{row['event_id']}"
                        )
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button("手動で確定する", key=f"btn_{row['event_id']}"):
                            df_ev.at[index, 'status'] = 'FIXED'
                            df_ev.at[index, 'final_choice'] = selected_idx
                            update_data("events", df_ev)
                            st.success(f"「{candidates[selected_idx]}」で日程を確定した！")
                            st.rerun()
                elif row['status'] == "FIXED":
                    final_idx = int(row['final_choice']) if pd.notna(row['final_choice']) and str(row['final_choice']).isdigit() else -1
                    if final_idx >= 0 and final_idx < len(candidates):
                        st.info(f"最終決定日時： **{candidates[final_idx]}**")
                
                st.markdown("---")
                
    except Exception as e:
        st.error(f"データの読み込み中にエラーが発生した: {e}")
