import streamlit as st
import google.generativeai as genai
from gtts import gTTS
import os
import tempfile
import base64
import json
import io
import time
import pandas as pd
import datetime
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# [1] 시스템 기본 설정 및 엔터프라이즈 UI CSS
# ==========================================
st.set_page_config(page_title="AI 현장심사 포털", page_icon="🛡️", layout="wide")

custom_theme_css = """
<style>
@media screen {
    html, body, [class*="css"] {
        color: #1e293b !important;
        font-family: 'Pretendard', -apple-system, sans-serif !important;
    }
    [data-testid="stSidebar"] {
        background-color: #0b2545 !important;
        border-right: 1px solid #000000 !important;
    }
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] input {
        color: #000000 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        border-bottom: 2px solid #e2e8f0 !important;
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        border-bottom: 3px solid transparent !important;
        padding: 12px 16px !important;
        color: #64748b !important;
        font-weight: 600 !important;
    }
    .stTabs [aria-selected="true"] {
        border-bottom: 3px solid #0b2545 !important;
        color: #0b2545 !important;
    }
    table {
        border: 2px solid #0b2545 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    }
    thead tr {
        background-color: #f8fafc !important;
        border-bottom: 2px solid #0b2545 !important;
    }
}
</style>
"""
st.markdown(custom_theme_css, unsafe_allow_html=True)

# ==========================================
# [2] 보안 설정 및 Pro 모델 선언
# ==========================================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error("🚨 [시스템 오류] st.secrets에서 필수 키를 찾을 수 없습니다.")
    st.stop()

# 💡 속도와 정확도를 모두 잡기 위해 Pro 모델 재도입
MODEL_NAME = "gemini-3.6-pro"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_credentials():
    try:
        return Credentials(
            token=None,
            refresh_token=st.secrets["google_oauth"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google_oauth"]["client_id"],
            client_secret=st.secrets["google_oauth"]["client_secret"]
        )
    except Exception as e:
        st.error(f"[오류] 인증 실패: {e}")
        return None

# ==========================================
# [3] 사이드바 설정
# ==========================================
with st.sidebar:
    st.markdown("## 🥛 YONSEI DAIRY")
    st.markdown("#### 스마트 해썹(HACCP) 심사포털")
    st.markdown("---")
    use_voice_mode = st.toggle("🎙️ 음성 모드 (스피커 출력)", value=False)
    
    if use_voice_mode:
        st.success("상태: **음성 모드 ON**")
    else:
        st.info("상태: **정숙 모드 ON**")
        
    st.markdown("---")
    st.markdown("### ⌨️ 보조 텍스트 검색")
    manual_query = st.text_input("서류명 입력:", placeholder="예: 수질검사 성적서", label_visibility="collapsed")
    manual_submit = st.button("문서 검색 🚀", use_container_width=True)

# ==========================================
# [4] 속도 최적화 구글 드라이브 다중 검색 코어
# ==========================================
def get_drive_service():
    creds = get_credentials()
    if creds:
        return build('drive', 'v3', credentials=creds)
    return None

def search_multiple_drive_files(service, keyword):
    """
    최상위 폴더 및 하위 폴더를 모두 포함하여 키워드에 해당하는 '모든' 파일을 가져옵니다.
    최대 10개까지 검색하여 사용자에게 선택권을 제공합니다.
    """
    try:
        # fullText를 활용해 드라이브 내 관련 문서를 광속으로 최대 10개까지 스캔
        query = f"fullText contains '{keyword}' and trashed = false"
        res = service.files().list(q=query, spaces='drive', fields='files(id, name, webViewLink, mimeType)', pageSize=10).execute()
        files = res.get('files', [])
        
        # 폴더 제외, 실제 문서(PDF, 이미지, 시트 등)만 필터링
        valid_files = [f for f in files if f['mimeType'] != 'application/vnd.google-apps.folder']
        return valid_files
    except Exception as e:
        st.error(f"검색 중 오류 발생: {e}")
        return []

def download_file_bytes(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

def autoplay_audio(text):
    tts = gTTS(text=text, lang='ko', slow=False)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        temp_filename = fp.name
        tts.save(temp_filename)
    with open(temp_filename, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)
    os.remove(temp_filename)

def process_audit_query(query_text=None, audio_bytes=None, is_voice_active=False):
    service = get_drive_service()
    if not service: return

    t_start = time.time()
    model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config={"temperature": 0.0})
    
    with st.spinner("Pro 모델: 심사관 의도 정밀 분석 중..."):
        # 💡 프롬프트를 극도로 경량화하여 추론 속도를 높임
        intent_prompt = """
        사용자 요청에서 구글 드라이브 검색을 위한 가장 핵심적인 단어 1개만 추출하세요. 
        예: '수질검사 성적서 줘' -> '수질검사', '보건증 보여줘' -> '보건증'
        응답형식(JSON): {"search_keyword": "핵심단어", "specific_question": "문서내용 질문(없으면 빈칸)"}
        """
        
        if audio_bytes:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
                tmp_audio.write(audio_bytes)
                tmp_audio_path = tmp_audio.name
            audio_file = genai.upload_file(path=tmp_audio_path)
            intent_res = model.generate_content([audio_file, intent_prompt])
            os.remove(tmp_audio_path)
            genai.delete_file(audio_file.name)
        else:
            intent_res = model.generate_content([f"요청: {query_text}", intent_prompt])

        try:
            intent_data = json.loads(intent_res.text.strip().replace("```json", "").replace("```", ""))
            keyword = intent_data.get("search_keyword", query_text[:5])
            question = intent_data.get("specific_question", "")
        except:
            keyword = query_text.replace("보여줘", "").strip()
            question = ""

        st.info(f"🔍 Pro 추출 키워드: **{keyword}** / 📝 추가 질문: **{question if question else '단순 열람'}**")

    # 드라이브 다중 검색 실행
    found_files = search_multiple_drive_files(service, keyword)
    
    if not found_files:
        st.warning(f"⚠️ '{keyword}' 관련 서류를 찾지 못했습니다.")
        if is_voice_active:
            autoplay_audio("해당 서류를 찾지 못했습니다.")
        return

    st.success(f"✅ 총 **{len(found_files)}개**의 관련 문서를 찾았습니다! (소요시간: {time.time() - t_start:.1f}초)")

    # 💡 검색된 파일이 여러 개일 경우 선택할 수 있는 UI 제공
    file_options = {f['name']: f for f in found_files}
    
    if len(found_files) > 1:
        selected_file_name = st.selectbox("📂 조회할 문서를 선택하세요 (최신순 등):", list(file_options.keys()))
    else:
        selected_file_name = list(file_options.keys())[0]
        
    top_file = file_options[selected_file_name]
    file_id, file_name, view_url = top_file['id'], top_file['name'], top_file['webViewLink']

    # 특정 질문이 있을 경우에만 Pro 모델로 원본 문서 심층 분석(Pre-calc) 수행
    if question:
        with st.spinner("Pro 모델: 문서 정밀 분석 및 정답 추출 중..."):
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_download = executor.submit(download_file_bytes, service, file_id)
                file_bytes = future_download.result()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_doc:
                tmp_doc.write(file_bytes)
                tmp_doc_path = tmp_doc.name
            
            gemini_doc = genai.upload_file(path=tmp_doc_path)

            qa_prompt = f"""
            첨부된 문서는 현장 심사 서류입니다. 심사관 질문: "{question}"
            팩트에 기반하여 정확한 수치나 텍스트를 추출하고, 심사관에게 보고할 1~2문장짜리 간결한 브리핑 스크립트만 작성하세요.
            """
            ans_res = model.generate_content([gemini_doc, qa_prompt])
            final_briefing = ans_res.text.strip()
            
            genai.delete_file(gemini_doc.name)
            os.remove(tmp_doc_path)
    else:
        final_briefing = f"요청하신 {file_name} 원본 서류입니다."

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"🔗 **[원본 파일 열기 (사진 촬영용 뷰어)]({view_url})**")
        st.components.v1.iframe(view_url, height=600, scrolling=True)
    with col2:
        st.write("🤖 **AI 브리핑 결과:**")
        st.success(f'"{final_briefing}"')
        
    if is_voice_active:
        autoplay_audio(final_briefing)

# ==========================================
# [5] 메인 UI 탭 구성
# ==========================================
st.markdown("## 🛡️ AI 현장심사 대응 통합 포털")
tab1, tab2, tab3 = st.tabs(["🤖 통합 검색 (AI)", "📁 수동 탐색기", "🚨 유효기간 대시보드"])

with tab1:
    if use_voice_mode:
        st.markdown("### 🎙️ 음성 기반 AI 검색")
        audio_value = st.audio_input("여기를 눌러 심사관의 요청을 녹음하세요")
        if audio_value:
            process_audit_query(audio_bytes=audio_value.getvalue(), is_voice_active=True)
    else:
        st.markdown("### ⌨️ 텍스트 기반 AI 검색 (정숙 모드)")
        st.info("사이드바의 '보조 텍스트 검색' 창에 검색어를 입력하고 엔터를 누르세요.")

    if manual_submit and manual_query:
        process_audit_query(query_text=manual_query, is_voice_active=use_voice_mode)

with tab2:
    st.markdown("### 📁 공장 심사 서류 다이렉트 탐색기")
    # 기존 FOLDER_DB 구조 유지
    FOLDER_DB = {
        "1. 인허가 및 인증 서류": {
            "인허가 서류": "folder_id_1a",
            "인증서": "folder_id_1b",
            "PL보험가입증서": "folder_id_1c"
        },
        "2. 위생 및 환경 관리": {
            "수질검사": "1gPfqV7K2bs29fvR0fSjSFYx_gtObyzKh", 
            "물탱크청소": "folder_id_2b",
            "방충방서 관련 서류": "folder_id_2c"
        },
        "3. 공장 운영 및 이력": {
            "설비이력": "folder_id_3a",
            "교육수료증": "folder_id_3b",
            "생산실적보고": "folder_id_3c"
        }
    }
    
    col_major, col_minor = st.columns(2)
    with col_major:
        selected_major = st.selectbox("📂 대분류 선택", list(FOLDER_DB.keys()))
    with col_minor:
        selected_minor = st.selectbox("📂 소분류 선택", list(FOLDER_DB[selected_major].keys()))
        
    target_folder_id = FOLDER_DB[selected_major][selected_minor]
    
    if st.button(f"'{selected_minor}' 전체 문서 호출", type="primary"):
        drive_service = get_drive_service()
        if drive_service:
            with st.spinner("폴더 인덱스 스캔 중..."):
                try:
                    query = f"'{target_folder_id}' in parents and trashed = false"
                    results = drive_service.files().list(
                        q=query, spaces='drive', fields='files(id, name, webViewLink, createdTime)', orderBy='createdTime desc', pageSize=50
                    ).execute()
                    
                    files = results.get('files', [])
                    if not files:
                        st.warning("등록된 문서가 없습니다.")
                    else:
                        display_data = []
                        for idx, f in enumerate(files, 1):
                            raw_date = f.get('createdTime', '')
                            clean_date = raw_date.split('T')[0] if raw_date else '날짜 없음'
                            link_md = f"[뷰어 열기]({f.get('webViewLink')})"
                            display_data.append({"No": idx, "파일명": f.get('name'), "생성일자": clean_date, "서류 열람": link_md})
                        st.dataframe(display_data, hide_index=True, use_container_width=True, column_config={"서류 열람": st.column_config.LinkColumn()})
                except Exception as e:
                    st.error(f"오류: {e}")

with tab3:
    st.markdown("### 🚨 법적 의무 서류 모니터링")
    
    validity_db = [
        {"분류": "인증/허가", "서류명": "식품제조가공업 영업등록증", "최근발급일": "2015-05-20", "법정주기(개월)": 0},
        {"분류": "인증/허가", "서류명": "품목제조보고서", "최근발급일": "2024-01-10", "법정주기(개월)": 0},
        {"분류": "현장검사", "서류명": "지하수 수질검사 성적서", "최근발급일": "2026-03-01", "법정주기(개월)": 6},
        {"분류": "작업자", "서류명": "종사자 건강진단서(보건증)", "최근발급일": "2025-10-15", "법정주기(개월)": 12},
        {"분류": "현장검사", "서류명": "살균기 검교정 성적서", "최근발급일": "2025-11-20", "법정주기(개월)": 12}
    ]
    
    df_validity = pd.DataFrame(validity_db)
    today = datetime.date.today()
    
    status_list, expire_dates, d_days = [], [], []
    
    for idx, row in df_validity.iterrows():
        issue_date = pd.to_datetime(row["최근발급일"]).date()
        period_months = row["법정주기(개월)"]
        
        if period_months == 0:
            expire_dates.append("영구")
            d_days.append("-")
            status_list.append("✅ 영구 (갱신 불필요)")
        else:
            expire_date = issue_date + pd.DateOffset(months=period_months)
            expire_date = expire_date.date()
            d_day = (expire_date - today).days
            
            expire_dates.append(expire_date.strftime("%Y-%m-%d"))
            d_days.append(d_day)
            
            if d_day < 0: status_list.append("🚨 기간 경과 (즉시 갱신)")
            elif d_day <= 30: status_list.append("⚠️ 갱신 임박 (30일 이내)")
            else: status_list.append("🟢 정상")
                
    df_validity["만료 예정일"] = expire_dates
    df_validity["D-Day"] = d_days
    df_validity["상태"] = status_list
    
    expired_docs = len(df_validity[df_validity["상태"] == "🚨 기간 경과 (즉시 갱신)"])
    warning_docs = len(df_validity[df_validity["상태"] == "⚠️ 갱신 임박 (30일 이내)"])
    
    if expired_docs > 0:
        st.error(f"🚨 [긴급 경고] 유효기간이 만료된 법정 서류가 {expired_docs}건 있습니다!")
    elif warning_docs > 0:
        st.warning(f"⚠️ [갱신 안내] 30일 이내에 만료되는 서류가 {warning_docs}건 있습니다.")
        
    def color_status(val):
        if "기간 경과" in str(val): return 'color: white; background-color: #ef4444; font-weight: bold'
        elif "갱신 임박" in str(val): return 'color: black; background-color: #fbbf24; font-weight: bold'
        elif "정상" in str(val): return 'color: white; background-color: #22c55e'
        elif "영구" in str(val): return 'color: white; background-color: #3b82f6'
        return ''

    styled_df = df_validity.style.map(color_status, subset=['상태'])
    
    st.dataframe(
        styled_df,
        hide_index=True,
        use_container_width=True,
        column_config={"법정주기(개월)": st.column_config.NumberColumn(format="%d 개월")}
    )
