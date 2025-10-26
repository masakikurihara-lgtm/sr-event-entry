import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import re
import datetime 

# ==============================================================================
# ----------------- 設定 -----------------
# ==============================================================================

try:
    # 既存のオーガナイザーCookieを使用
    AUTH_COOKIE_STRING = st.secrets["showroom"]["auth_cookie_string"]
except KeyError:
    #st.error("🚨 SecretsにオーガナイザーのCookieが設定されていません。")
    st.error("🚨 認証設定がされていません。")
    st.stop()

BASE_URL = "https://www.showroom-live.com"
ORGANIZER_ADMIN_URL = f"{BASE_URL}/event/admin_organizer" 
APPROVE_ENDPOINT = f"{BASE_URL}/event/organizer_approve"
# JSTタイムゾーン定義
JST = datetime.timezone(datetime.timedelta(hours=9), 'JST') 

# ==============================================================================
# ----------------- セッション構築関数 -----------------
# ==============================================================================

def create_authenticated_session(cookie_string):
    """手動で取得したCookie文字列から認証済みRequestsセッションを構築する"""
    session = requests.Session()
    try:
        cookies_dict = {}
        for item in cookie_string.split(';'):
            item = item.strip()
            if '=' in item:
                name, value = item.split('=', 1)
                cookies_dict[name.strip()] = value.strip()
        cookies_dict['i18n_redirected'] = 'ja'
        session.cookies.update(cookies_dict)
        return session
    except Exception as e:
        st.error(f"認証セッション解析中にエラーが発生しました: {e}")
        return None

# ==============================================================================
# ----------------- 承認関数 -----------------
# ==============================================================================

def approve_entry(session, approval_data):
    """個別のイベント参加申請を承認します。"""
    payload = {
        'csrf_token': approval_data['csrf_token'],
        'room_id': approval_data['room_id'],
        'event_id': approval_data['event_id'],
    }
    
    headers = {
        'Referer': ORGANIZER_ADMIN_URL, 
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest', 
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8', 
    }
    
    st.info(f"承認リクエスト送信中: ルーム名: {approval_data['room_name']}")
    
    try:
        r = session.post(APPROVE_ENDPOINT, data=payload, headers=headers, allow_redirects=True)
        r.raise_for_status()

        if ORGANIZER_ADMIN_URL in r.url or APPROVE_ENDPOINT in r.url:
             st.success(f"✅ 承認成功: ルームID {approval_data['room_id']} / イベントID {approval_data['event_id']}")
             return True
        else:
            st.error(f"承認リクエストは成功しましたが、リダイレクト先が予期しないページでした: {r.url}")
            return False

    except requests.exceptions.RequestException as e:
        st.error(f"承認リクエスト中にエラーが発生しました: {e}")
        return False

# ==============================================================================
# ----------------- 未承認イベント検索関数 (イベント名取得を追加) -----------------
# ==============================================================================

def find_pending_approvals_filtered(session, target_room_id):
    """特定のルームIDに一致する未承認のイベント参加申請のみを抽出する"""
    
    try:
        r = session.get(ORGANIZER_ADMIN_URL, headers={}) 
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        #st.error(f"管理ページへのアクセスに失敗しました: {e}")
        st.error(f"該当ページへのアクセスに失敗しました: {e}")
        return [], None

    soup = BeautifulSoup(r.text, 'html.parser')
    pending_approvals = []
    csrf_token = None

    # CSRFトークンの取得 (必須)
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    if csrf_input:
        csrf_token = csrf_input['value']
    
    if not csrf_token:
        st.error("🚨 CSRFトークンを取得できませんでした。認証セッションが有効か確認してください。")
        return [], None

    approval_forms = soup.find_all('form', {'action': '/event/organizer_approve'})
    
    if not approval_forms:
        return [], csrf_token

    for form in approval_forms:
        try:
            room_id_str = form.find('input', {'name': 'room_id'})['value']
            event_id = form.find('input', {'name': 'event_id'})['value']
            
            # 🚨 フィルタリング: 対象ルームIDに一致する場合のみ処理
            if room_id_str == str(target_room_id):
                tr_tag = form.find_parent('tr')
                room_name_tag = tr_tag.find('a', href=re.compile(r'/room/profile\?room_id='))
                # 🚨 修正: イベント名タグの取得
                event_name_tag = tr_tag.find('a', href=re.compile(r'/event/')) 

                room_name = room_name_tag.text.strip() if room_name_tag else "不明なルーム"
                # 🚨 修正: イベント名を取得
                event_name = event_name_tag.text.strip() if event_name_tag else "不明なイベント" 

                pending_approvals.append({
                    'csrf_token': csrf_token, 
                    'room_id': room_id_str,
                    'event_id': event_id,
                    'room_name': room_name,
                    'event_name': event_name # 🚨 追加
                })
        except Exception as e:
            continue

    return pending_approvals, csrf_token

# ==============================================================================
# ----------------- メイン関数 -----------------
# ==============================================================================

def main():
    # ページ設定
    st.set_page_config(
        page_title="SHOWROOM イベント緊急手動承認",
        #page_icon="🚨",
        page_icon="🚨"
        #layout="wide"
    )
    st.markdown(
        "<h1 style='font-size:28px; text-align:center; color:#1f2937;'>🚨 SHOWROOM イベント緊急手動承認ツール</h1>",
        unsafe_allow_html=True
    )
    #st.title("🚨 SHOWROOM イベント緊急手動承認ツール")
    st.markdown("<p style='text-align: center;'>⚠️ <b>注意</b>: このツールは、<b>管理者が認証セッションを許可している場合のみ</b>動作します。</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    # セッション状態の初期化
    if 'search_button_clicked' not in st.session_state:
        st.session_state.search_button_clicked = False

    # 1. ルームIDの入力とボタン制御 (修正項目①)
    default_room_id = st.query_params.get("room_id", "")
    
    with st.form("room_search_form"):
        target_room_id = st.text_input(
            "ルームIDを入力してください:", 
            value=default_room_id, 
            help="このルームIDの未承認申請のみが表示されます。"
        )
        # フォームの送信ボタン
        if st.form_submit_button("リストを表示 / 再検索"):
            # ボタンが押されたことを記録
            if target_room_id and target_room_id.isdigit():
                 st.session_state.search_button_clicked = True
            else:
                 st.session_state.search_button_clicked = False
    
    # ボタンが押されていない、またはIDが不正な場合はここで処理を終了
    if not st.session_state.search_button_clicked or not target_room_id.isdigit():
        if st.session_state.search_button_clicked and not target_room_id.isdigit():
             st.error("⚠️ 有効なルームID（数字）を入力してください。")
        elif not st.session_state.search_button_clicked:
             st.warning("⚠️ ルームIDを入力して「リストを表示 / 再検索」ボタンを押してください。")
        return

    # 2. 検索実行ブロック
    session = create_authenticated_session(AUTH_COOKIE_STRING)
    if not session:
        return

    st.info(f"現在の時刻（JST）: {datetime.datetime.now(JST).strftime('%Y/%m/%d %H:%M:%S')}")
    st.markdown(f"**対象ルーム**: ルームID `{target_room_id}`")

    # 3. 未承認イベントの検索とフィルタリング
    pending_entries, csrf_token = find_pending_approvals_filtered(session, target_room_id)
    
    if not pending_entries:
        st.success(f"✅ ルームID `{target_room_id}` の未承認イベント申請は見つかりませんでした。")
        return

    num_pending = len(pending_entries)
    st.warning(f"🚨 {num_pending} 件の未承認申請が見つかりました。")
    
    st.markdown("---")
    st.header("承認が必要な申請リスト")

    # 4. 承認処理の表示と実行
    approved_count = 0
    
    for i, entry in enumerate(pending_entries):
        with st.container(border=True):
            st.markdown(f"**ルーム名**: {entry['room_name']}")
            # 🚨 修正項目②: イベント名を表示
            st.markdown(f"**イベント名**: **{entry['event_name']}**")
            
            if st.button(f"🚀 {entry['event_name']} を承認する", key=f"approve_{entry['room_id']}_{entry['event_id']}"):
                entry['csrf_token'] = csrf_token 
                
                if approve_entry(session, entry):
                    approved_count += 1
                    time.sleep(1) 
                    # 承認成功後、画面をリロードしてリストを更新
                    st.rerun() 

    if approved_count == 0:
        st.info("↑ 上記のボタンを押して手動で承認してください。")

if __name__ == "__main__":
    main()