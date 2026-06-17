import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, time
import requests
import json  # JSONのパース用に必要

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

# イベント登録時に出欠アンケート（複数候補）を送信する関数
def send_multi_candidate_poll(event_id, event_name, candidates):
    if "slack_token" not in st.secrets:
        return None
    token = st.secrets["slack_token"]
    channel = "#random" # 実際の通知先チャンネル名に合わせて変更する
    
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📢 新しいイベントの日程調整"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*イベント名*: {event_name}\n以下の候補から、参加可能な日時を【すべて】お選びください。"}},
    ]
    
    # 候補日をボタン化する（Slackの制約上、1つのactionsブロックには最大5つまで配置可能）
    actions_elements = []
    for i, cand in enumerate(candidates):
        actions_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": cand},
            "value": f"{event_id}:{i}" # GASで「どのイベントの何番目の候補か」を識別するための値
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
    
    event_name = st.text_input("イベント名", placeholder="例：月例ゼミ")
    
    st.subheader("候補日時の追加")
    
    # 動的に入力欄を増やすためのSession State
    if "candidates" not in st.session_state:
        st.session_state.candidates = [{"date": datetime.now(), "time": time(10, 0)}]
    
    # 現在の候補入力欄を表示
    for i, cand in enumerate(st.session_state.candidates):
        col1, col2 = st.columns(2)
        cand["date"] = col1.date_input(f"候補 {i+1} の日付", cand["date"], key=f"date_{i}")
        cand["time"] = col2.time_input(f"候補 {i+1} の時間", cand["time"], key=f"time_{i}")
    
    # 候補追加ボタン
    if st.button("➕ 候補日を追加する"):
        if len(st.session_state.candidates) < 5: # Slackのボタン上限が5個のため制限
            st.session_state.candidates.append({"date": datetime.now(), "time": time(10, 0)})
            st.rerun()
        else:
            st.warning("Slackの仕様上、一度に送信できる候補は5つまでである。")
    
    st.markdown("---")
    
    # 送信ボタン
    if st.button("日程調整アンケートをSlackに送信"):
        if not event_name:
            st.error("イベント名を入力してほしい。")
        else:
            try:
                df_ev = load_data("events")
                new_id = f"e{len(df_ev) + 1:03}"
                
                # 入力された日付と時間を文字列に結合
                cand_strs = [f"{c['date'].strftime('%Y-%m-%d')} {c['time'].strftime('%H:%M')}" for c in st.session_state.candidates]
                
                # 新しい行のデータ
                new_row = pd.DataFrame([{
                    "event_id": new_id,
                    "event_name": event_name,
                    "candidates": json.dumps(cand_strs), # リストをJSON文字列化
                    "votes": "{}",                       # 初期投票状態は空のJSON
                    "status": "VOTING",
                    "final_choice": ""
                }])
                
                # スプレッドシート更新
                update_data("events", pd.concat([df_ev, new_row], ignore_index=True))
                
                # Slackへ送信
                slack_res = send_multi_candidate_poll(new_id, event_name, cand_strs)
                
                if slack_res and slack_res.status_code == 200:
                    st.success(f"「{event_name}」の候補を登録し、Slackにアンケートを送信した！")
                    st.session_state.candidates = [{"date": datetime.now(), "time": time(10, 0)}] # フォームのリセット
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
            # 登録されているイベントを1つずつ表示
            for index, row in df_ev.iterrows():
                # JSON文字列からPythonのデータ形式に戻す
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
                
                # 投票状況の箇条書き表示
                st.markdown("**【得票状況】**")
                for i, cand in enumerate(candidates):
                    # その候補のインデックス番号に対応する投票者リストを取得
                    voters = votes.get(str(i), [])
                    st.markdown(f"* **{cand}** : {len(voters)} 票")
                
                # 投票中のイベントのみ、確定用UIを表示する
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
                        st.write("") # 高さ合わせ
                        st.write("")
                        if st.button("この日程で確定する", key=f"btn_{row['event_id']}"):
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
