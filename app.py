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
# [0] AI 현장심사 대응 지식베이스 (초정밀 팩트 데이터)
# ==========================================
KNOWLEDGE_BASE = {
    # 1. 작업장 및 환경 관리 기준
    "조도기준": "조도 측정은 바닥에서 80cm 높이에서 분기별 1회 실시합니다. 기준치는 검사실/계량실 540 Lux 이상, 제조실/포장실 220 Lux 이상, 창고 및 냉장고 등 기타 구역은 110 Lux 이상입니다.",
    "온습도기준": "작업장 온습도는 월 1회 측정합니다. 청결구역 온도는 15~35℃, 준청결구역 1~40℃, 일반구역 1~35℃이며, 모든 구역의 습도 기준은 0~70% 이하로 관리됩니다.",
    "방충방서": "해충 모니터링은 주간 포획량에 따라 3단계로 관리됩니다. 청결구역 기준 비래해충(파리/나방 등)은 1단계 6마리, 2단계 10마리, 3단계 20마리이며, 3단계 이탈 시 배수로 청소 등 2단계 이탈 조치를 실행합니다. 방역은 월 2회 이상 실시합니다.",
    "식품보안": "식품보안 위험성 평가는 심각성과 발생가능성 점수의 합이 4 이상일 때 중요관리점(CCP)으로 지정합니다. 저수조, 화학제, 원료창고 등 주요 보안 구역은 1일 1회 순회 점검 및 CCTV 관찰, 시건장치 점검을 실시합니다.",

    # 2. 개인 위생 및 복장 규정
    "작업자건강": "액상 유출(상처) 사고 발생 시 부문장 보고 후 방수 밴드를 착용하고 식품 직접 접촉 업무에서 배제합니다. 설사, 구토 등 식중독 의심 환자는 완치(48시간 이상 무증상) 시까지 작업장 출입이 통제됩니다.",
    "복장기준": "기본 복장은 구역에 따라 청결구역은 위생작업복, 준청결구역은 위생가운, 정비작업 시에는 정비작업복을 착용합니다. 작업장 온도에 따라 하절기 반팔/조끼, 동절기 점퍼 등의 추가 복장이 허용됩니다.",
    "위생소독": "손 소독은 70% 알코올을 사용하며, 위생화 소독은 포미(살균소독제)를 물과 250배(200ppm) 희석한 발판 소독조에서 실시합니다.",
    "전자기기": "휴대폰은 원칙적으로 현장 반입 금지이나, 허가된 당직자/공정관리자 등은 사무실 내에서 사용 가능합니다. 현장 내 업무용/소통용 테블릿 및 LTE 무전기는 상시 알코올 소독 조건으로 반입이 허용됩니다.",

    # 3. 장갑 및 이물 관리 기준
    "장갑구분": "식품 접촉/청소 구역에 따라 장갑을 엄격히 구분합니다. 세척/소독 시에는 적색/노란색 고무장갑을 사용하며, 원자재 투입 시에는 라텍스/니트릴(흰색) 고무장갑을 사용합니다. 설비 정비 시에는 반코팅 목장갑을 사용하며, 부자재 투입 시에는 면장갑을 착용한 후 1회 사용 뒤 정비용으로 재활용합니다.",
    "이물예방_조치": "스냅형 칼(커터칼), 스테이플러, 압정, 핀, 클립, 철수세미의 작업장 반입을 전면 금지합니다. 이물 발견 시 즉시 생산을 중단하고 격리 보관하며, 원인 분석 후 부적합보고서 또는 시정조치요구대책서를 발행합니다.",

    # 4. 설비 세척/소독 (CIP) 및 용수 관리
    "CIP세제온도": "라인별 CIP 세제(가성소다, 질산) 온도는 우유가공/발효유 45~70℃, 포장 65~75℃, 상온제품 70~80℃, 원유이송차량 45~65℃입니다. 열수 살균 온도는 95~100℃(상온제품은 125℃ 이상)로 관리됩니다.",
    "수질_저수조관리": "제품수(음용수) 및 지하수는 연 2회(반기별 1회) 공인검사기관에 검사를 의뢰하며, 자체 용수 검사는 월 1회(관능, pH, 대장균 등) 실시합니다. 저수조는 연 2회(6개월마다) 청소 및 소독을 실시해야 합니다.",

    # 5. 제품 회수 및 보관/운반 관리
    "회수조치_추적성": "위해식품 발생 시, 1등급은 24시간, 2등급은 48시간, 3등급은 72시간 이내에 영업자에게 회수명령 공문을 전달합니다. 생산 및 판매 관련 서류는 2년간 보관하여 추적성을 확보합니다.",
    "보관_운반온도": "일반 원/부자재는 실온(1~35℃), 냉장 제품은 0~10℃(원유 0~4℃), 냉동 제품은 -18℃ 이하에서 보관합니다. 차량 운송 시 상차 전 냉동기를 가동하여 냉장은 0~10℃, 냉동은 -18℃ 이하를 유지해야 합니다.",
    "해동관리": "냉동원료는 냉장 조건(0~10℃)에서 14일 이내, 실온 조건(1~35℃)에서 2일 이내에 지정된 실내 장소에서 포장을 유지한 채 해동해야 합니다.",
    "포장기라인정체": "별도 냉각 장치가 없는 포장기에서 제품이 정체될 경우, 2시간 이내에는 품질 검사 후 생산 여부를 판단하고, 2시간을 초과한 제품은 전량 폐기 조치합니다.",

    # 6. 품목별 세부 제조공정 및 CCP 한계기준 (핵심)
    "원유저장_집유장CCP1B": "원유저장(CCP-1B) 한계기준은 저장온도 0~7℃입니다. 2시간 간격으로 온도를 모니터링하며, 이탈 시 냉각수 온도(6℃ 이하) 확인 후, 알콜/산도/pH/관능검사 등을 통해 출고/폐기 여부를 결정합니다.",
    "여과_CCP2P": "포장 타입별로 우유류 카톤포장 100Mesh, 병포장 120Mesh, 유크림 80Mesh, 호상발효유 60Mesh, 카톤발효유 50Mesh 여과망을 사용합니다. 가공두유 및 액상차 등은 1.0Φ 타공망(또는 30Mesh)을 사용합니다. 파손 시 해당 생산분은 전량 폐기합니다.",
    "유액멸균_두유CCP1B": "간접살균은 135~150℃에서 30~45초간(원액두유는 100~130℃, 3초 이상), 직접살균은 143~153℃에서 3.6~4.4초간 멸균합니다. 135℃ 미만 시 자동 생산 중단, 30초 미만 살균 시 전량 폐기합니다.",
    "유액멸균_우유음료CCP1B": "가공유류는 135~150℃에서 30~37초간, 우유/강화유는 135~150℃에서 10~14초간(HTST의 경우 72~75℃에서 15초 이상) 멸균합니다. 유크림은 92~100℃에서 30초 이상 살균합니다. 커피 및 음료류는 135~150℃에서 10~14초(또는 30~37초)간 관리합니다.",
    "배양액살균_발효유CCP1B": "배양액 살균(CCP-1B) 한계기준은 95~110℃에서 4분 15초 이상(유량 7,000 L/hr 미만)입니다. 이탈 시 설비 분해 정비 후 재 CIP 및 살균합니다.",
    "포장지멸균_CCP3B": "테트라팩은 과산화수소 농도 32~50% 또는 eBeam 전류값 95~105%로, 콤비블럭은 과산화수소 온도 250~290℃, 분사량 350~450μl/s(140mL 이하는 150~250μl/s)로 포장지를 멸균하며 이탈 시 즉시 폐기합니다.",
    "금속검출기_발효유CCP3P": "호상발효유 및 병포장 라인의 금속검출기 한계기준은 Fe 1.5mm, SUS 2.5mm 이상 불검출입니다.",
    "환자용식품가공": "마쇄는 1차 1,700 rpm, 2차 85℃ 열수 투입 후 5,800 rpm으로 실시하며, 간접살균은 135~150℃에서 30~37초간, 직접살균은 143~153℃에서 3.6~8.8초간 진행합니다."
}

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
# [2] 보안 설정 및 검증된 모델 선언
# ==========================================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error("🚨 [시스템 오류] st.secrets에서 필수 키를 찾을 수 없습니다.")
    st.stop()

# 담당자님 환경에서 정상 작동하는 플래시 모델로 픽스
MODEL_NAME = "gemini-1.5-flash"
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
    manual_query = st.text_input("서류명 입력:", placeholder="예: 수질검사 성적서, 살균온도", label_visibility="collapsed")
    manual_submit = st.button("AI 브리핑 및 문서검색 🚀", use_container_width=True)

# ==========================================
# [4] 속도 최적화 구글 드라이브 다중 검색 코어
# ==========================================
def get_drive_service():
    creds = get_credentials()
    if creds:
        return build('drive', 'v3', credentials=creds)
    return None

def search_multiple_drive_files(service, keyword):
    try:
        query = f"fullText contains '{keyword}' and trashed = false"
        res = service.files().list(q=query, spaces='drive', fields='files(id, name, webViewLink, mimeType)', pageSize=10).execute()
        files = res.get('files', [])
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

    with st.spinner("AI: 심사관 의도 정밀 분석 중..."):
        intent_prompt = """
        사용자 요청에서 구글 드라이브 검색을 위한 가장 핵심적인 단어 1개만 추출하세요. 
        만약 구체적인 수치(예: 살균온도, 여과망 크기)를 묻는 질문이라면 핵심 키워드로 '기준서'를 도출하세요.
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
            question = intent_data.get("specific_question", query_text)
        except:
            keyword = query_text.replace("보여줘", "").strip()
            question = query_text

        st.info(f"🔍 AI 추출 키워드: **{keyword}** / 📝 추가 질문: **{question if question else '단순 열람'}**")

    # 드라이브 다중 검색 실행
    found_files = search_multiple_drive_files(service, keyword)

    if not found_files:
        st.warning(f"⚠️ '{keyword}' 관련 서류를 찾지 못했습니다. 지식베이스를 기반으로만 답변합니다.")
        found_files = [] # 빈 리스트로 처리하여 문서를 띄우지 않고 답변만 생성

    final_briefing = ""
    preview_url = ""
    view_url = ""
    gemini_file = None
    tmp_doc_path = ""

    # 문서가 발견되었을 경우의 처리
    if found_files:
        st.success(f"✅ 총 **{len(found_files)}개**의 관련 문서를 찾았습니다! (소요시간: {time.time() - t_start:.1f}초)")
        
        file_options = {f['name']: f for f in found_files}
        
        if len(found_files) > 1:
            selected_file_name = st.selectbox("📂 조회할 문서를 선택하세요:", list(file_options.keys()))
        else:
            selected_file_name = list(file_options.keys())[0]

        top_file = file_options[selected_file_name]
        file_id, file_name, view_url = top_file['id'], top_file['name'], top_file['webViewLink']
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview"

        with st.spinner(f"📥 '{file_name}' PDF 문서를 다운로드 및 AI 분석 장전 중..."):
            try:
                # 파일을 바이트로 다운로드 후 Gemini File API에 업로드하여 텍스트 인식률 100% 확보
                file_bytes = download_file_bytes(service, file_id)
                file_ext = ".pdf" if "pdf" in top_file.get('mimeType', '').lower() else ".txt"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_doc:
                    tmp_doc.write(file_bytes)
                    tmp_doc_path = tmp_doc.name
                
                gemini_file = genai.upload_file(path=tmp_doc_path)
            except Exception as e:
                st.error(f"파일 처리 중 오류: {e}")

    # AI 답변 생성 (지식베이스 + 업로드된 문서)
    with st.spinner("🤖 AI가 규정 지식베이스와 문서를 종합하여 브리핑을 작성 중입니다..."):
        kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
        analysis_prompt = f"""
        당신은 연세유업 아산공장 스마트 해썹(HACCP) 심사 대응 전문 AI입니다.
        아래의 [사내 규정 초정밀 지식베이스]와 첨부된 [문서 내용(있을경우)]을 종합하여 심사관의 질문에 즉각 답변하세요.
        
        [사내 규정 초정밀 지식베이스]
        {kb_str}
        
        [심사관 요청/질문]
        {question if question else query_text}
        
        [행동 지침]
        1. 질문이 살균 온도/시간, 여과망 사이즈, 과산화수소 농도 등 구체적인 수치를 묻는다면, 지식베이스의 팩트 데이터를 최우선으로 인용하여 **명확한 숫자**로 즉시 대답하세요. (추정 금지)
        2. 문서가 첨부되었다면, 문서의 내용 중 심사관의 질문에 부합하는 요약 브리핑을 3문장 이내로 덧붙이세요.
        3. 정중하고 전문적인 현장 심사 담당자의 톤앤매너를 유지하세요.
        """
        try:
            inputs = [gemini_file, analysis_prompt] if gemini_file else [analysis_prompt]
            response = model.generate_content(inputs)
            final_briefing = response.text
        except Exception as e:
            final_briefing = f"AI 분석 중 오류가 발생했습니다: {str(e)}"
        finally:
            # File API 리소스 정리
            if gemini_file:
                genai.delete_file(gemini_file.name)
                os.remove(tmp_doc_path)

    # UI 렌더링
    if preview_url:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"🔗 **[원본 새창에서 열기]({view_url})**")
            st.components.v1.iframe(preview_url, height=600, scrolling=True)
        with col2:
            st.write("🤖 **AI 브리핑 결과:**")
            st.success(final_briefing)
    else:
        st.write("🤖 **AI 브리핑 결과:**")
        st.success(final_briefing)
        
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
    warning_docs = len(df_validity[df_validity["상태"] == "⚠ 갱신 임박 (30일 이내)"])

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
