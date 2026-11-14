import streamlit as st
import google.generativeai as genai
try:
    from gtts import gTTS
except ImportError:
    gTTS = None
import os
import tempfile
import base64
import json
import io
import time
import pandas as pd
import datetime
import urllib.parse
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ==========================================
# [0] 시스템 기본 설정 및 타임아웃 방어막
# ==========================================
st.set_page_config(page_title="식품안전·HACCP 통합 증빙 시스템", page_icon="🛡️", layout="wide")
socket.setdefaulttimeout(600)

try:
    import fitz  # PyMuPDF
    PYMUPDF_INSTALLED = True
except ImportError:
    PYMUPDF_INSTALLED = False

CACHE_META_FILE = "haccp_agent_cache.json"

MAIN_TABS = [
    "📄 심사 증빙 열람",
    "🗂️ 문서 보관함 · 등록",
    "📊 법정 기한 현황",
    "⚙️ 마스터 DB 관리",
    "⚖️ 규정 · 법규 검증"
]

# ==========================================
# [0-0] AI 현장심사 대응 지식베이스
# ==========================================
KNOWLEDGE_BASE = {
    "공장현재인증현황": """[아산공장 전체 HACCP 인증 보유 현황]
    1. 유가공업(우유, 발효유 등) 및 식품제조가공업(가공두유, 원액두유, 음료 등) 등 다수의 품목별 HACCP 인증을 보유 중임.
    2. [기인증 공정 범위 팩트 - 품목별 엄격 구분]:
       - 원액두유: 여과(CCP-1P) 및 살균(CCP-2B) 공정에 한하여 인증 완료. (멸균 및 무균포장 공정은 인증 범위에 미포함되어 있으므로, 현행 인증만으로는 완제품 포장 출하가 불가하며 공정 추가 변경인증 필수)
       - 가공두유/과채음료 등: 살균 및 무균 포장(포장지 멸균) 공정까지 전체 라인 인증 완료.
       - 유제품 살균 라인(CCP-1B 살균): 일반우유, 가공유, 유크림 품목에 한정하여 인증됨. (유당분해우유는 살균 라인 인증 없음)
       - 유제품 멸균 라인(CCP-1B 멸균): 유당분해우유 포함 멸균 제품군 전체 인증됨.""",

    "조도기준": "조도 측정은 바닥에서 80cm 높이에서 분기별 1회 실시합니다. 기준치는 검사실/계량실 540 Lux 이상, 제조실/포장실 220 Lux 이상, 창고 및 냉장고 등 기타 구역은 110 Lux 이상입니다.",
    "온습도기준": "작업장 온습도는 월 1회 측정합니다. 청결구역 온도는 15~35℃, 준청결구역 1~40℃, 일반구역 1~35℃이며, 모든 구역의 습도 기준은 0~70% 이하로 관리됩니다.",
    "방충방서": "해충 모니터링은 주간 포획량에 따라 3단계로 관리됩니다. 청결구역 기준 비래해충(파리/나방 등)은 1단계 6마리, 2단계 10마리, 3단계 20마리이며, 3단계 이탈 시 배수로 청소 등 2단계 이탈 조치를 실행합니다. 방역은 월 2회 이상 실시합니다.",
    "식품보안": "식품보안 위험성 평가는 심각성과 발생가능성 점수의 합이 4 이상일 때 중요관리점(CCP)으로 지정합니다. 저수조, 화학제, 원료창고 등 주요 보안 구역은 1일 1회 순회 점검 및 CCTV 관찰, 시건장치 점검을 실시합니다.",
    "작업자건강": "액상 유출(상처) 사고 발생 시 부문장 보고 후 방수 밴드를 착용하고 식품 직접 접촉 업무에서 배제합니다. 설사, 구토 등 식중독 의심 환자는 완치(48시간 이상 무증상) 시까지 작업장 출입이 통제됩니다.",
    "복장기준": "기본 복장은 구역에 따라 청결구역은 위생작업복, 준청결구역은 위생가운, 정비작업 시에는 정비작업복을 착용합니다. 작업장 온도에 따라 하절기 반팔/조끼, 동절기 점퍼 등의 추가 복장이 허용됩니다.",
    "위생소독": "손 소독은 70% 알코올을 사용하며, 위생화 소독은 포미(살균소독제)를 물과 250배(200ppm) 희석한 발판 소독조에서 실시합니다.",
    "전자기기": "휴대폰은 원칙적으로 현장 반입 금지이나, 허가된 당직자/공정관리자 등은 사무실 내에서 사용 가능합니다. 현장 내 업무용/소통용 테블릿 및 LTE 무전기는 상시 알코올 소독 조건으로 반입이 허용됩니다.",
    "장갑구분": "식품 접촉/청소 구역에 따라 장갑을 엄격히 구분합니다. 세척/소독 시에는 적색/노란색 고무장갑을 사용하며, 원자재 투입 시에는 라텍스/니트릴(흰색) 고무장갑을 사용합니다. 설비 정비 시에는 반코팅 목장갑을 사용하며, 부자재 투입 시에는 면장갑을 착용한 후 1회 사용 뒤 정비용으로 재활용합니다.",
    "장갑위생": "장갑을 맨손으로 사용할 경우 사용 전 70% 알코올로 소독해야 합니다. 사용 후 청소용 고무장갑은 세척 후 자외선 살균소독기나 건조대에 보관하며, 원자재 투입용 장갑은 중성세제와 70% 알코올로 세척/소독하여 보관합니다.",
    "이물예방": "유리, 플라스틱, 목재, 금속 등 이물질 혼입을 방지하기 위해 스냅형 칼(커터칼), 스테이플러, 압정, 핀, 클립, 철수세미의 작업장 반입을 전면 금지합니다. 유리 제품은 가능한 다른 재질로 대체하거나 보호 처리해야 합니다. 테이프는 포장실 등 지정된 장소에서만 사용 가능합니다.",
    "이물발생조치": "생산 중 이물 발견 시 즉시 생산을 중단하고 과(팀)장에게 보고합니다. 이물 및 선별된 원료는 격리 보관하며, 원인 분석 후 '부적합보고서' 또는 '시정조치요구대책서'를 발행하여 개선합니다.",
    "이물보관": "소비자로부터 클레임 접수된 이물 신고 내용은 2년간 보관합니다. 소비자가 제시한 이물 실물과 증거품(사진 등)은 6개월간 보관하는 것이 원칙이나, 부패·변질 우려가 있는 경우 2개월간 보관할 수 있습니다.",
    "칼가위관리": "생산 구역에서 사용되는 칼과 가위는 회사가 지급, 식별, 등록한(번호 부여) 물품만 사용해야 합니다. 개인 사물함이나 칼집에 보관해서는 안 되며 임시 보관만 가능합니다. 시작 및 종료 시 상태 점검을 실시해야 합니다.",
    "알러겐분류": "알러겐 함유 원료(우유, 대두, 땅콩, 호두, 토마토, 밀 등)는 자재 창고에서부터 별도 구분 및 식별(색상 라벨링)하여 보관합니다.",
    "알러겐취급": "알러겐 원·부자재의 계량, 배합에 사용되는 작업 도구는 전용으로 구분하고 식별 표시를 부착하여 교차오염을 방지합니다.",
    "알러겐검증": "CIP 후 알러겐 물질 잔류 여부는 연 1회 이상 검증(Reveal 3D 등 키트 활용)하며, 양성 판정 시 CIP 효과성 증대 방안을 검토합니다.",
    "해동장소": "냉동원료는 냉장 창고, 원자재 보관 창고, 작업장 내 임시 보관 공간에서 선반이나 파레트 위에 포장을 유지한 채 해동해야 정석이며, 야외나 비위생적 공간에서의 해동은 금지됩니다.",
    "해동온도및시간": "해동은 냉장 조건(0~10℃)에서 14일 이내, 실온 조건(1~35℃)에서 2일 이내에 완료되어야 합니다.",
    "해동후관리": "해동 중인 원료는 시작/종료 시간 및 온도 조건이 기록된 명찰을 부착하여 관리해야 하며, 해동이 완료된 원료는 즉시 냉장 보관하고 최단 시간 내에 사용해야 합니다.",
    "기기검교정": "온도계 및 비중계의 사내 교정 주기는 1회/6개월이며, 외부 공인 검사는 1회/년 실시합니다. 저울의 사내 교정은 1회/6개월, 공인 검사는 1회/2년입니다.",
    "병원성미생물검사": "중국 수출용 우유 및 원부자재는 황색포도상구균, 살모넬라 등 병원성 미생물에 대해 PCR(중합효소연쇄반응) 분석을 실시합니다.",
    "검사자숙련도": "미생물, 산도, 조지방 등의 검사자는 연 1회 이상 내부 숙련도 평가를 받으며, 평가 결과 '불만족' 시 재교육 및 재평가를 통과할 때까지 해당 검사에서 배제됩니다.",
    "CIP세제온도": "라인별 CIP 세제(가성소다, 질산) 온도는 우유가공/발효유 45~70℃, 포장 65~75℃, 상온제품 70~80℃, 원유이송차량 45~65℃입니다. 열수 살균 온도는 95~100℃(상온제품은 125℃ 이상)로 관리됩니다.",
    "CIP검증": "CIP 완료 후에는 pH Paper를 이용하여 세제 잔류 검사를 100% 실시하며, 세척 효과성 검증은 연 1회 주기로 유기물(알러겐 키트) 및 무기물(필터링 육안 점검) 검사를 실시합니다.",
    "수세미구분": "제조 설비(식품 접촉면) 청소용 수세미와 작업장 바닥 청소용 수세미는 색상을 엄격히 구분하여 보관 및 관리합니다.",
    "설비시운전": "신규 설비 도입 시 시운전은 3단계로 진행됩니다. 1단계(전기/유압 작동 확인), 2단계(연속 사이클 부대설비 연계), 3단계(생산 제품 적합성 확인)를 거쳐 승인됩니다.",
    "설비폐기": "노후 설비 폐기는 부문장이 설비폐기 품의서를 작성하고, 총무부문장, 생산본부장 및 사장의 검토를 거쳐 최종적으로 법인본부장의 승인을 득한 후 폐기합니다.",
    "수질검사": "아산공장은 상수도(먹는물)와 지하수를 병행 사용합니다. 먹는물(상수도) 및 지하수(제품수)는 공인검사기관에 정기 수질검사(연 2회/반기별 1회 등 법정 주기) 및 노로바이러스 검사를 의뢰하여 성적서를 구비하며, 자체 용수 검사는 월 1회(관능, pH, 대장균 등) 실시합니다.",
    "저수조관리": "저수조는 연 2회(6개월마다) 청소 및 소독을 실시해야 합니다.",
    "필터교체주기": "용수 처리 시설의 마이크로 필터는 3개월(또는 6개월)마다, 활성탄(카본) 필터 및 이온교환수지는 2년마다 교체 또는 재생해야 합니다.",
    "회수등급별조치": "위해식품 발생 시, 1등급은 24시간 이내, 2등급은 48시간 이내, 3등급은 72시간 이내에 영업자에게 회수명령 공문을 전달해야 합니다. 회수명령을 받은 영업자는 1등급은 1일 이내, 2~3등급은 2일 이내에 관할 기관에 회수계획서를 보고해야 합니다.",
    "회수교육및훈련": "회수 업무와 관련하여 1회/년 이상 식품안전팀원 대상 교육을 실시하며, 2회/년 이상 모의회수(추적성) 훈련을 주관합니다. 모의회수 훈련 시 원인 파악 및 추적 시간은 1시간 이내, 회수율은 100%를 목표로 합니다.",
    "추적성관리": "원부자재 입고부터 제품 출하까지 생산/작업/거래/검사 기록을 철저히 관리하여 추적성을 확보하며, 생산 및 판매 관련 서류는 2년간 보관합니다.",
    "보관온도": "일반 원/부자재는 실온(1~35℃), 냉장 제품은 0~10℃(원유 0~4℃), 냉동 제품은 -18℃ 이하에서 보관합니다.",
    "운반온도관리": "차량 운송 시 상차 전 냉동기를 가동(10분 이상 예비냉각)하여 냉장은 0~10℃, 냉동은 -18℃ 이하를 유지해야 합니다.",
    "포장기라인정체제품": "별도 냉각 장치가 없는 포장기에서 제품이 정체될 경우, 2시간 이내에는 품질 검사 후 생산 여부를 판단하고, 2시간을 초과한 제품은 전량 폐기 조치합니다.",
    "대두가공공정": "대두는 110~140℃(국산콩 220℃ 이상)에서 5분 이상 Heating하여 반할두로 제조하며, 70~90℃ 열수로 2분 이상 침지합니다. 1차 마쇄는 1,700rpm, 2차 마쇄는 85℃ 열수 투입 후 5,800rpm으로 진행합니다. 원심분리는 4,800rpm으로 작동합니다.",
    "CCP1B유액멸균_두유": "간접살균은 135~150℃에서 30~45초간 멸균하며, 직접살균은 143~153℃에서 3.6~4.4초간 멸균합니다. 135℃ 미만 시 자동 생산 중단, 30초 미만 살균 시 전량 폐기, 45초 초과 시 관능/이화학 검사 후 출고를 결정합니다.",
    "CCP2P여과_두유": "여과망 사이즈는 1.0Φ를 사용하며, 생산 시작 전/종료 후 여과망 사이즈 및 파손 여부를 점검합니다. 파손 확인 시 해당 생산분은 전량 폐기합니다.",
    "CCP3B포장지멸균_테트라팩": "테트라팩은 32~50% 농도의 과산화수소 침지 또는 eBeam 전류값 95~105%로 조사하여 멸균합니다. 설비(호기)별 과산화수소 Bath 통과(침지) 시간은 B호기(미드) 2.812초, C호기(프리즈마) 5.96초, D호기(미드) 2.812초입니다. 이탈 시 해당 제품은 폐기합니다.",
    "CCP3B포장지멸균_콤비팩": "콤비팩은 과산화수소 온도 250~290℃, 분사량 350~450μl/s 조건으로 분사하여 멸균합니다. 온도 및 분사량 이탈 시 생산 중단 후 점검하며 이탈된 제품은 폐기합니다.",
    "포장속도및탱크": "무균포장기 속도는 설비별로 6,000~40,000 pak/h로 다양하며, Aseptic Tank는 1.0~2.0 cm²/Hg 압력을 유지합니다.",
    "자석봉관리": "이물 제거를 위해 정선/석발 및 여과 공정에서 10,000 가우스 이상의 영구자석을 이용합니다.",
    "원유수유및여과": "0~4℃ 원유는 60 mesh(A2원유는 1차 40 mesh, 2차 100 mesh 타공) 여과망으로 이물을 제거하며, 1일 2회 분해 점검을 실시합니다. 원심 청정기는 5,300~6,000 rpm으로 작동합니다.",
    "유당분해우유공정": "유당분해 효소를 접종하여 4~6℃에서 24~27시간 배양하며, 튜블러 멸균 공정에서 135~150℃, 3.8초 이상 멸균합니다.",
    "저지방표준화공정": "탈지유와 원유를 혼합하여 유지방 함량을 0.8~1.2%(저지방), 3.1~3.5%(표준화)로 맞추며, 10,000 rpm의 크림분리기를 사용합니다.",
    "멸균유CCP1B_가공유": "가공유류(UHT) 유액멸균 한계기준은 멸균온도 135~150℃, 멸균시간 30~37초간입니다.",
    "멸균유CCP1B_우유강화유": "우유, 강화유, 가공유 일부제품의 UHT 한계기준은 멸균온도 135~150℃, 멸균시간 10~14초간입니다. HTST의 경우 72~75℃에서 15초 이상 멸균합니다.",
    "멸균유CCP1B_유크림": "유크림의 살균 한계기준은 92~100℃에서 30초 이상 살균(유량 500 L/hr 이하)하는 것입니다.",
    "멸균유CCP1B_중국조제유": "중국 수출용 조제유(병우유)의 한계기준은 127~130℃에서 15초 이상 살균하는 것입니다.",
    "멸균유CCP2P_여과": "여과 공정 한계기준은 포장 타입별로 우유류 카톤포장 100Mesh, 병포장 120Mesh, 유크림 80Mesh 여과망을 사용하며, 파손 여부를 확인합니다.",
    "발효유배양공정": "배양탱크(6,000L 등)에서 4종의 유산균과 유당분해효소를 접종하여 38~42℃(여름 38℃, 봄/가을 40℃, 겨울 42℃)에서 6~8시간 배양한 후 10℃ 이하(그릭요거트는 30℃)로 냉각합니다.",
    "발효유CCP1B_배양액살균": "배양액 살균(CCP-1B) 한계기준은 95~110℃에서 4분 15초 이상(유량 7,000 L/hr 미만)입니다. 살균온도가 정상온도로 복귀하지 못할 시 살균을 정지시키고 설비 분해 정비 후 재 CIP 및 살균합니다.",
    "발효유CCP2P_여과": "여과(CCP-2P) 한계기준은 포장 타입별로 병 포장 80Mesh, 호상발효유 60Mesh, 카톤 포장 50Mesh 여과망 사이즈 및 파손 여부입니다. 작업 개시 전/종료 후 1회씩 육안 점검합니다.",
    "발효유CCP3P_금속검출기": "호상발효유 및 병포장 라인의 금속검출기(CCP-3P) 한계기준은 Fe 1.5mm, SUS 2.5mm 이상 불검출입니다. 작업 시작 전/종료 후 및 2시간 간격으로 시편을 통과시켜 모니터링합니다.",
    "원액두유CCP1P_여과": "원액두유 여과(CCP-1P) 한계기준은 여과망 사이즈 30Mesh 및 파손 여부입니다. 작업 개시 전/종료 후 육안 점검을 실시하며 파손 시 생산분을 전량 폐기합니다.",
    "원액두유CCP2B_두유액살균": "원액두유 살균(CCP-2B) 한계기준은 살균온도 100~130℃, 살균시간 3초 이상(유량 4,500 L/hr 이하)입니다. 3초 미만으로 살균된 유액은 폐기합니다.",
    "음료균질": "균질 시 돌(파인, 망고) 및 유산균음료는 150 bar, 스위플(사과, 레드오렌지, 샤인머스캣) 제품은 200 bar의 압력으로 균질합니다.",
    "음료추출공정": "차(Tea) 추출 공정은 70~90℃ 열수로 20~50분간 추출하며, 백 필터(5μm) 및 마이크로 필터(1μm) 파우치 필터를 사용합니다.",
    "음료CCP1B_과채음료류": "과채음료, 과채주스, 혼합음료, 유산균음료, 액상차의 유액멸균(CCP-1B) 한계기준은 90~130℃(또는 135~150℃)에서 30~37초간입니다.",
    "음료CCP1B_혼합음료특정제품": "혼합음료(스위플 레드오렌지, 샤인머스캣, 과일펀치 제외)와 커피의 경우, 멸균 온도 135~150℃, 시간 30~37초간으로 관리하며, A2프로틴 오리지널의 경우 143~153℃, 3.6~4.4초간으로 관리합니다.",
    "음료CCP1B_커피": "커피의 유액멸균(CCP-1B) 한계기준은 135~150℃에서 10~14초간입니다.",
    "음료CCP2P_여과": "음료류 여과(CCP-2P) 한계기준은 여과망 1.0Φ 사용 및 파손 여부 확인입니다.",
    "음료CCP3B_포장지멸균": "테트라팩은 과산화수소 농도 32~50% 또는 eBeam 전류값 95~105%로, 콤블럭은 과산화수소 온도 250~290℃, 분사량 350~450μl/s(150~250μl/s 등 제품별 상이)로 포장지 멸균을 관리합니다.",
    "집유장원유검사": "원유 입고 시 관능, 비중(1.028~1.034), 알콜(70% 음성), 진애(2.0mg 이하), 산도(0.14% 이하), 조지방(3.2% 이상), 세균발육억제물질(음성), 가수/빙점(-508 이하) 등을 검사하며, A2 원유는 A2 단백질 100% 여부를 추가 확인합니다.",
    "집유장원유저장": "원유의 보관 및 유통 온도는 농가 0~4℃, 탱크로리 0~7℃, 저유조 0~7℃로 관리됩니다.",
    "집유장여과및청정": "수유 시 60 mesh 여과망으로 이물을 제거하며(1일 2회 분해 점검), 일반 원유는 5,300~6,000 rpm의 청정기를 거치나 A2 및 무항생제 원유는 청정 공정을 제외합니다.",
    "집유차량세척": "집유 차량은 1일 2회(오전/오후 수유 후) 열수 CIP를 실시하고, 2일에 1회 약품 CIP를 실시합니다.",
    "집유장CCP1B_원유저장": "원유저장(CCP-1B) 한계기준은 저장온도 0~7℃입니다. 2시간 간격으로 온도를 모니터링하며, 한계기준 이탈 시 냉각수 온도(6℃ 이하)를 확인하고, 알콜/산도/pH/관능검사 등을 통해 법적 기준(10℃ 이하) 적합 시 선출고 또는 폐기 여부를 결정합니다.",
    "집유장탱크수량": "집유 및 원유 보관에 운용되는 원유저장탱크는 100,000L 4기, 50,000L 4기, 30,000L 3기, 6,000L 3기로 총 14기입니다.",
    "환자용식품가공공정": "대두 Heating/탈피는 110~140℃에서 5분 이상 실시하며, 침지는 90℃ 열수로 1분 이상 진행합니다(고형분 9% 이상 제품은 예외). 마쇄는 1차 1,700 rpm, 2차 85℃ 열수 투입 후 5,800 rpm으로 실시하고, 3,500 rpm으로 원심분리합니다. 균질 시 압력은 300 bar 이하로 관리됩니다.",
    "환자용식품CCP1B_유액멸균": "간접살균은 135~150℃에서 30~37초간, 직접살균은 143~153℃에서 3.6~8.8초간 멸균합니다. 한계온도 이탈 시 자동 정지 후 CIP 및 장치 멸균을 재실시하며, 30초/3.6초 미만 살균 시 전량 폐기, 한계시간 초과 시 관능 및 이화학 검사 후 출고를 결정합니다.",
    "환자용식품CCP2P_여과": "여과(CCP-2P) 한계기준은 여과망 사이즈 1.0Φ 및 파손 여부이며, 작업 개시 전/종료 후 육안으로 점검하여 이탈 시 해당 생산분을 전량 폐기합니다.",
    "환자용식품CCP3B_포장지멸균": "테트라팩은 과산화수소 농도 32~50% 또는 eBeam 전류값 95~105%로, 콤비블럭은 과산화수소 온도 250~290℃, 분사량 350~450μl/s로 포장지를 멸균하며 이탈된 제품은 즉각 폐기 조치합니다.",
    "작업장동선및레이아웃": "작업장 평면도에 따르면 작업자 이동 경로(녹색), 폐수 이동 경로(청색), 원유 이송 흐름도(분홍색), 탱크로리 CIP 흐름도(보라색)가 명확히 분리되어 교차오염을 방지하고 있습니다. 주요 구역은 수유실, 수유 검사실, 원유취급실, 우유 가공, 발효유 가공 구역 등으로 철저히 구획되어 정밀 통제됩니다."
}

# ==========================================
# [0-1] 구글 드라이브 문서 보관함 매칭 DB
# ==========================================
FLAT_FOLDER_DB = {
    "인허가 서류": "1Y98P8DINsy_9ZheN4n-CCElfcoD4ZVvX",
    "인증서": "1ONXI69skOZGE-vzAyMmL_rMUjX5ZXjiz",
    "기준서": "1NyHIprsIniDHDpW0gXzDoyOx5pG3aJIM",
    "선행요건": "1IZCo0YknOP-AaLqn8akGYu7IlgDG1Qw0",
    "FSSC22000": "15q0E-CZQ5TH4jUwf1_iNqRO9K0EXpbaw",
    "수질검사": "1gPfqV7K2bs29fVr0FSjSFYx_gtObyzKh",
    "물탱크청소": "1csN34omFYOAslyLPzZEHaW57rShAvmbY",
    "방충방서 관련 서류": "19lz-LDZaCDYcCjhWHh4QiN8RDqlceYf7",
    "환경관리팀_폐기물계약서": "1HS_r_itaMkXYitFDoLPuFBIt0oI41fPT",
    "교육수료증": "1MnIlbnXXEr7ITvEGK2tK7LjBf3_iWlU1",
    "모의회수": "11dUf40rpdnWzZvmxp0acFGmAnD67GiL-",
    "생산실적보고": "15cUTYawQPkK9FrUD9mV8rWh1NGtseiW4",
    "설비이력": "11VJcx38MKiC5tjho6bHyobWBgxsltT76",
    "PL보험가입증명서": "1wqa9LnNbmkxwmzO2b0m-tRYL05qKhbII"
}

# ==========================================
# [0-2] 사내 그룹웨어 전자결재 양식 리스트
# ==========================================
GW_DOC_LIST = [
    "측정기기 공인기관 검·교정 결과", "자체 측정기기 검·교정결과", "카톤팩 과산화수소 잔류여부 검증 결과",
    "품질(제품, 원·부자재) 부적합 현황 보고", "자력기기 점검 결과", "상업적 무균테스트 결과 보고서",
    "콤비팩 과산화수소 잔류여부 검증 결과", "유량계 공인기관 교정 결과", "테트라팩 과산화수소 잔류여부 검증 결과",
    "알러겐 및 미생물 검증 결과", "작업자 손 위생검사 결과", "병원성 미생물 배지 수불부", "자가품질검사 검사결과",
    "우유 포장 공정관리 일보", "대리점 클레임 현황", "문제점 개선 대책 결과 보고", "소비자 클레임 현황(제조단계, 공장)",
    "현장 온도센서 공인기관 검·교정 결과", "발효유 포장 공정관리 일보", "중국 수출 우유 제품검사 일보", "음료류 일반검사 일보",
    "부자재 입고 검수서", "압축공기 미생물검사 결과", "표면오염도 검사 결과", "낙하세균 검사 결과", "세척.소독제 농도 검증 결과",
    "용수 검사 성적서", "방역 관리 리포트", "위생교육", "냉장/냉동 창고 온도 모니터링 일지"
]

# ==========================================
# [0-3] 법정주기 및 필수 서류 마스터 리스트
# ==========================================
MASTER_DOC_REQUIREMENTS = {
    "사업자등록": {"표시명": "사업자등록증 (연세유업/생활건강)", "주기": 0},
    "공장등록": {"표시명": "공장등록증명서", "주기": 0},
    "건축물대장": {"표시명": "건축물대장", "주기": 0},
    "식품제조가공업": {"표시명": "식품제조가공업 영업등록증", "주기": 0},
    "축산물가공업": {"표시명": "축산물가공업(유가공업) 허가증", "주기": 0},
    "집유업": {"표시명": "집유업 허가증", "주기": 0},
    "수입식품영업": {"표시명": "수입식품등 수입·판매업 영업등록증", "주기": 0},
    "식품소분업": {"표시명": "식품소분판매업 영업신고증", "주기": 0},
    "축산물판매업": {"표시명": "축산물유통전문판매업 신고필증", "주기": 0},
    "건강기능식품영업": {"표시명": "건강기능식품 영업신고증", "주기": 0},
    "통신판매업": {"표시명": "통신판매업신고증", "주기": 0},
    "방문판매업": {"표시명": "방문판매업신고증", "주기": 0},
    "집단급식소": {"표시명": "집단급식소 설치·운영 신고증", "주기": 0},
    "화장품책임판매": {"표시명": "화장품책임판매업 등록필증", "주기": 0},
    "지하수개발허가": {"표시명": "지하수개발·이용허가서", "주기": 60},
    "HACCP_가공두유": {"표시명": "식약처 HACCP (가공두유)", "주기": 36},
    "HACCP_원액두유": {"표시명": "식약처 HACCP (원액두유)", "주기": 36},
    "HACCP_유가공업": {"표시명": "식약처 HACCP (유가공업)", "주기": 36},
    "HACCP_과채주스": {"표시명": "식약처 HACCP (과채주스)", "주기": 36},
    "HACCP_과채음료": {"표시명": "식약처 HACCP (과채음료)", "주기": 36},
    "HACCP_혼합음료": {"표시명": "식약처 HACCP (혼합음료)", "주기": 36},
    "HACCP_유산균음료": {"표시명": "식약처 HACCP (유산균음료)", "주기": 36},
    "HACCP_커피": {"표시명": "식약처 HACCP (커피)", "주기": 36},
    "HACCP_액상차": {"표시명": "식약처 HACCP (액상차)", "주기": 36},
    "HACCP_환자식": {"표시명": "식약처 HACCP (환자용/당뇨/암환자 등)", "주기": 36},
    "CHINA_HACCP": {"표시명": "중국 수출용 HACCP 인증서", "주기": 36},
    "FSSC22000": {"표시명": "FSSC 22000 인증서", "주기": 36},
    "K-MILK": {"표시명": "국산우유 사용 인증(K-MILK)", "주기": 12},
    "무항생제": {"표시명": "무항생제축산물 인증서", "주기": 12},
    "유기가공식품": {"표시명": "유기가공식품 인증서", "주기": 12},
    "FDA_FFR": {"표시명": "FDA 식품시설등록(FFR)", "주기": 24},
    "FDA_FCE": {"표시명": "FDA 공장등록(FCE)", "주기": 0},
    "수질검사_먹는물": {"표시명": "공인기관 먹는물(상수도) 수질검사 성적서", "주기": 12},
    "수질검사_지하수": {"표시명": "공인기관 지하수 수질검사 성적서 (반기)", "주기": 6},
    "수질검사_노로": {"표시명": "노로바이러스 검사 성적서", "주기": 12},
    "저수조청소": {"표시명": "저수조 청소필증 (상/하반기)", "주기": 6},
    "수질검사_월간": {"표시명": "자체 수질검사 성적서 (월간·그룹웨어)", "주기": 1, "gw": "용수 검사 성적서"},
    "방충방서_월간": {"표시명": "방충방서 점검 리포트 (월간·그룹웨어)", "주기": 1, "gw": "방역 관리 리포트"},
    "책임보험": {"표시명": "영업배상책임보험 / PL보험 증권 (자사)", "주기": 12},
    "모의회수": {"표시명": "모의회수(추적성) 훈련 결과", "주기": 12}
}

# ==========================================
# [0-4] 공식 문서 AI 판독 및 마스터 DB 분류 공통 프롬프트 (단건 등록·일괄 스캔 공용)
# ==========================================
MASTER_SCAN_PROMPT = """본 문서의 핵심 메타데이터를 정밀하게 추출하십시오. (공식 심사 대응용 무결성 데이터)

[검증 및 추출 원칙]
1. 문서의 날짜를 임의로 추정하지 마십시오. 본문 또는 직인 옆에 명시된 날짜만 추출하고, 확인이 불가능할 경우 "미상"으로 기재하십시오.
2. 파일명만으로 분류하지 마시고, 발급 기관, 문서 목적, 하단 직인 유무를 종합 분석하여 해당하는 마스터 키워드를 부여하십시오.
3. 문서 상단 또는 하단에 개정번호(Rev.0, Rev.1 등)가 기재되어 있는 경우 반드시 추출하십시오.

[마스터 키워드 맵핑 규칙 - 엄수]
🚨 아래 지정된 키워드 중 정확히 일치하는 1개로 변환하여 "키워드" 값에 기재하십시오.
- 사업자등록증 -> "사업자등록"
- 공장등록증명서 -> "공장등록"
- 건축물대장 -> "건축물대장"
- 식품제조가공업 관련 영업증/등록증 -> "식품제조가공업"
- 축산물가공업/유가공업 허가증 -> "축산물가공업"
- 집유업 허가증 -> "집유업"
- 수입식품 영업 관련 -> "수입식품영업"
- 식품소분판매업, 일반 영업신고증 -> "식품소분업"
- 축산물유통전문판매업, 우유류판매업 -> "축산물판매업"
- 건강기능식품 영업/신고증 -> "건강기능식품영업"
- 통신판매업신고증 -> "통신판매업"
- 방문판매업신고증 -> "방문판매업"
- 집단급식소 관련 -> "집단급식소"
- 화장품책임판매업 -> "화장품책임판매"
- 지하수개발 이용허가서 -> "지하수개발허가"
- 식약처 HACCP (가공두유) -> "HACCP_가공두유"
- 식약처 HACCP (원액두유) -> "HACCP_원액두유"
- 식약처 HACCP (유가공업) -> "HACCP_유가공업"
- 식약처 HACCP (과채주스) -> "HACCP_과채주스"
- 식약처 HACCP (과채음료) -> "HACCP_과채음료"
- 식약처 HACCP (혼합음료) -> "HACCP_혼합음료"
- 식약처 HACCP (유산균음료) -> "HACCP_유산균음료"
- 식약처 HACCP (커피) -> "HACCP_커피"
- 식약처 HACCP (액상차) -> "HACCP_액상차"
- 식약처 HACCP (일반환자용/당뇨/암환자 등) -> "HACCP_환자식"
- 중국 수출용 HACCP 인증서 (영문/중문 HACCP 인증서) -> "CHINA_HACCP"
- FSSC 22000 -> "FSSC22000"
- K-MILK 인증서 -> "K-MILK"
- 무항생제 인증서 -> "무항생제"
- 유기가공식품 인증서 -> "유기가공식품"
- FDA 식품시설등록(FFR) -> "FDA_FFR"
- FDA 공장등록(FCE) -> "FDA_FCE"
- 먹는물(상수도/수돗물) 공인 수질검사 성적서 -> "수질검사_먹는물"
- 지하수(원수/정수) 공인 수질검사 성적서 -> "수질검사_지하수"
- 노로바이러스 검사 성적서 -> "수질검사_노로"
- 저수조 청소필증 또는 저수조 청소결과 보고서 -> "저수조청소"
- 모의회수 또는 추적성 훈련 결과 보고서 -> "모의회수"
- 연세유업(연세대학교) 자사 책임보험/영업배상/PL보험 -> "책임보험" (주의: 삼양인터내셔날 등 외부 방역업체 보험증권은 "기타"로 분류)
- 사내 규정(YS-규정 등), 품목별 HACCP 기준서/PLAN/공정설명서, 파트별 선행요건 관리기준서 등 지침서는 무조건 -> "매뉴얼"

💡 [교육 수료증 분류 규칙] 💡
- 기존영업자 대상 식품/축산물/건기식/화장품/책임수의사 위생·보수교육 수료증은 반드시 수료한 '업종'을 확인하여 지정하십시오.
  ("법정위생교육_식품제조가공업", "법정위생교육_축산물가공업", "법정위생교육_집유업", "법정위생교육_수입식품영업", "법정위생교육_우유류판매업", "법정위생교육_유통전문판매업", "법정위생교육_건강기능식품판매업", "법정위생교육_집단급식소", "법정위생교육_책임수의사", "법정위생교육_화장품책임판매")
- 연간 식품·축산물 HACCP 정기교육 수료증은 -> "HACCP정기교육"
- HACCP 팀장과정 또는 경영자과정 수료증은 -> "HACCP팀장및경영자교육"
- 위 법정 의무교육 외의 일반 직무 교육, 1회성 특강 수료증은 -> "일반수료증"

💡 [동적 확장(Dynamic) 규칙] 💡
- 가설건축물, 보건증 등 개별 관리 대상 문서는 아래 허용된 접두사로 시작하도록 키워드를 생성하십시오.
- 허용 접두사: "가설건축물_", "보건증_"
- 예시: "가설건축물_1동", "가설건축물_5~6동", "보건증_홍길동"

🚨 [기타 문서 예외 처리] 🚨
- 위 분류에 해당하지 않는 내부심사 계획안, 청소사진, 일반 기안서나 기타 참고 자료는 누락시키지 말고 "기타"로 분류하십시오. (절대 PASS 금지)

만료일이 명시되어 있지 않더라도 법정 주기가 명확한 서류는 발급일 기준으로 만료일을 산출하여 기재하고, 유효기간이 없는 영구 보존 서류(FDA_FCE, 팀장교육, 영업등록증 등)나 매뉴얼은 '영구'로 기재하십시오.

반드시 JSON 형식으로만 응답하십시오.
형식: {
    "키워드": "법정위생교육_식품제조가공업",
    "문서_실제제목": "본문 공식 명칭",
    "발급일": "YYYY-MM-DD",
    "만료일": "YYYY-MM-DD",
    "개정번호": "Rev.0",
    "분류근거": "발급기관 및 본문 내용에 따른 분류 근거"
}"""

# ==========================================
# [1] 상태 초기화 및 공식 UI 스타일 정의 (상단 잘림 완전 방지)
# ==========================================
if "master_cache_name" not in st.session_state:
    if os.path.exists(CACHE_META_FILE):
        try:
            with open(CACHE_META_FILE, "r") as f:
                cache_data = json.load(f)
                if time.time() - cache_data.get("timestamp", 0) < 11.5 * 3600:
                    st.session_state["master_cache_name"] = cache_data["name"]
        except Exception:
            pass

if "active_main_tab" not in st.session_state: st.session_state.active_main_tab = MAIN_TABS[0]
if "priority_keywords" not in st.session_state: st.session_state.priority_keywords = []
if "search_done" not in st.session_state: st.session_state.search_done = False
if "search_mode" not in st.session_state: st.session_state.search_mode = "exact"
if "found_files" not in st.session_state: st.session_state.found_files = []
if "aux_files" not in st.session_state: st.session_state.aux_files = []
if "search_keyword" not in st.session_state: st.session_state.search_keyword = ""
if "search_question" not in st.session_state: st.session_state.search_question = ""
if "final_briefing" not in st.session_state: st.session_state.final_briefing = ""
if "briefing_cache" not in st.session_state: st.session_state.briefing_cache = {}
if "show_briefing" not in st.session_state: st.session_state.show_briefing = False
if "last_file_id" not in st.session_state: st.session_state.last_file_id = ""
if "view_url" not in st.session_state: st.session_state.view_url = ""
if "preview_url" not in st.session_state: st.session_state.preview_url = ""
if "target_folder_key" not in st.session_state: st.session_state.target_folder_key = None
if "gw_keyword" not in st.session_state: st.session_state.gw_keyword = ""
if "gw_keywords_list" not in st.session_state: st.session_state.gw_keywords_list = []
if "auto_db" not in st.session_state: st.session_state.auto_db = []
if "files_to_scan" not in st.session_state: st.session_state.files_to_scan = []
if "selected_doc_idx" not in st.session_state: st.session_state.selected_doc_idx = 0
if "selected_page_num" not in st.session_state: st.session_state.selected_page_num = 1
if "chat_doc_viewer" not in st.session_state: st.session_state.chat_doc_viewer = None
if "dash_status_filter" not in st.session_state: st.session_state.dash_status_filter = "기한경과_미등록"

# 문서 보관함 · 등록 전용 상태 변수 (클릭 전 우측 뷰어 비활성화로 로딩 지연 차단)
if "explorer_selected_cat" not in st.session_state: st.session_state.explorer_selected_cat = "인허가 서류"
if "explorer_selected_folder_id" not in st.session_state: st.session_state.explorer_selected_folder_id = ""
if "explorer_active_doc" not in st.session_state: st.session_state.explorer_active_doc = None
if "explorer_page_num" not in st.session_state: st.session_state.explorer_page_num = 1

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [{
        "role": "assistant",
        "content": "안녕하십니까. 연세유업 아산공장 식품안전 및 HACCP 통합 검증 시스템입니다. 공정 관리 기준, 선행요건, 법적 인허가 및 인증 규격에 대해 문의해 주시면 사내 기준서와 현행 법령을 교차 검증하여 근거 문헌 출처와 함께 안내해 드리겠습니다.",
        "citations": []
    }]

custom_theme_css = """
<style>
@media screen {
    .block-container { padding-top: 3.8rem !important; padding-bottom: 2.5rem !important; max-width: 98% !important; }
    html, body, [class*="css"] { color: #1e293b !important; font-family: 'Pretendard', sans-serif !important; }
    [data-testid="stSidebar"] { background-color: #f8fafc !important; border-right: 1px solid #e2e8f0 !important; }
    [data-testid="stSidebar"] [data-testid="stExpander"] details { background-color: #f8fafc !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; }
    [data-testid="stSidebar"] button { background-color: #0f172a !important; color: white !important; font-weight: bold !important; border-radius: 8px !important; padding: 8px 14px !important; box-shadow: 0 3px 5px -1px rgba(0,0,0,0.08) !important; transition: all 0.2s; }
    [data-testid="stSidebar"] button:hover { background-color: #334155 !important; transform: translateY(-1px); }
    [data-testid="stSidebar"] button p { color: #ffffff !important; font-weight: bold !important; }

    .stTabs [data-baseweb="tab-list"] { border-bottom: 2px solid #e2e8f0 !important; gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: transparent !important; border: none !important; border-bottom: 3px solid transparent !important; padding: 10px 14px !important; color: #64748b !important; font-weight: 600 !important; }
    .stTabs [aria-selected="true"] { border-bottom: 3px solid #0f172a !important; color: #0f172a !important; }

    div:has(> .top-nav-marker) + div [data-testid="stRadio"] > div {
        border-bottom: 2px solid #e2e8f0 !important;
        padding-bottom: 8px !important;
        gap: 6px !important;
    }

    .paper-header-box { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }
    .citation-card { background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #0f172a; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; }
    .drive-file-row { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 6px; }

    table { border-collapse: collapse !important; width: 100% !important; margin: 1.2rem 0 !important; border: 2px solid #0f172a !important; border-radius: 8px !important; overflow: hidden !important; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1) !important; }
    thead tr { background-color: #f8fafc !important; color: #0f172a !important; border-bottom: 2px solid #0f172a !important; }
    th { font-weight: 700 !important; padding: 10px 14px !important; text-align: left !important; border-right: 1px solid #cbd5e1 !important; }
    td { padding: 10px 14px !important; border-right: 1px solid #cbd5e1 !important; border-bottom: 1px solid #e2e8f0 !important; }
    tbody tr:hover { background-color: #f1f5f9 !important; }

    .mfds-banner { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px 18px; text-align: center; font-size: 1.02rem; font-weight: 600; margin-bottom: 14px; }
    .mfds-result-item { border-bottom: 1px solid #e2e8f0; padding: 12px 6px; }
    .mfds-title { font-size: 0.98rem; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
    .mfds-path { font-size: 0.82rem; color: #64748b; font-weight: 500; }
    .mfds-snippet { font-size: 0.9rem; color: #334155; line-height: 1.55; margin-top: 4px; }
    .mfds-key { color: #dc2626; font-weight: 800; background-color: #fef08a; padding: 1px 4px; border-radius: 3px; }
    .badge-direct { background-color: #dbeafe; color: #1e40af; font-size: 0.75rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; margin-right: 6px; }
    .badge-related { background-color: #fef3c7; color: #92400e; font-size: 0.75rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; margin-right: 6px; }
}
</style>
"""
st.markdown(custom_theme_css, unsafe_allow_html=True)

# ==========================================
# [2] API 인증 및 클라우드 연동 서비스
# ==========================================
MODEL_NAME = "models/gemini-3.8-flash"
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    SHEET_ID = st.secrets["MASTER_SHEET_ID"] if "MASTER_SHEET_ID" in st.secrets else ""
    genai.configure(api_key=GEMINI_API_KEY)
except Exception:
    st.error("🚨 시스템 필수 인증 정보(secrets)가 누락되었습니다. 관리자에게 문의해 주십시오.")
    st.stop()

def get_credentials():
    try:
        return Credentials(
            token=None,
            refresh_token=st.secrets["google_oauth"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google_oauth"]["client_id"],
            client_secret=st.secrets["google_oauth"]["client_secret"]
        )
    except Exception:
        return None

def get_drive_service():
    creds = get_credentials()
    return build('drive', 'v3', credentials=creds) if creds else None

def get_sheets_service():
    creds = get_credentials()
    return build('sheets', 'v4', credentials=creds) if creds else None

def ensure_auto_db_loaded():
    if not st.session_state.auto_db and SHEET_ID:
        sheet_service = get_sheets_service()
        if sheet_service:
            try:
                result = sheet_service.spreadsheets().values().get(
                    spreadsheetId=SHEET_ID, range="DB!A:J"
                ).execute()
                values = result.get('values', [])
                if len(values) > 1:
                    headers = values[0]
                    loaded_db = []
                    for row in values[1:]:
                        row_dict = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
                        loaded_db.append(row_dict)
                    st.session_state.auto_db = loaded_db
            except Exception:
                pass
# ==========================================
# [3] 날짜 정규화, 폴더 캐시, 하위폴더 생성·업로드·자동스캔 및 세부 분류 엔진
# ==========================================
def _safe_ymd(y, m, d):
    try:
        dt = datetime.date(int(y), int(m), int(d))
        return (dt.year, dt.month, dt.day)
    except Exception:
        return None

def parse_doc_date_tuple(filename, date_str=""):
    fn = str(filename).strip()
    m_range1 = re.search(r'(20[12]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\s*[~\-]\s*20[23]\d', fn)
    if m_range1:
        res = _safe_ymd(m_range1.group(1), m_range1.group(2), m_range1.group(3))
        if res: return res

    m_range2 = re.search(r'\(?(?:20)?([12]\d)[.\-/](\d{1,2})[.\-/](\d{1,2})\s*[~\-]\s*(?:20)?[23]\d', fn)
    if m_range2:
        res = _safe_ymd(2000 + int(m_range2.group(1)), m_range2.group(2), m_range2.group(3))
        if res: return res

    m_dot = re.search(r'(?:20)?(2[0-9])\.\s*(1[0-2]|0?[1-9])\.\s*(3[01]|[12]\d|0?[1-9])', fn)
    if m_dot:
        res = _safe_ymd(2000 + int(m_dot.group(1)), m_dot.group(2), m_dot.group(3))
        if res: return res

    for m_8 in re.finditer(r'(20[12]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', fn.replace(" ", "")):
        res = _safe_ymd(m_8.group(1), m_8.group(2), m_8.group(3))
        if res: return res

    for m_6 in re.finditer(r'(?<!\d)(2[0-9])(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)', fn):
        res = _safe_ymd(2000 + int(m_6.group(1)), m_6.group(2), m_6.group(3))
        if res: return res

    if date_str:
        m_iso = re.search(r'(19\d\d|20\d\d)[.\-/](\d{1,2})[.\-/](\d{1,2})', str(date_str))
        if m_iso:
            res = _safe_ymd(m_iso.group(1), m_iso.group(2), m_iso.group(3))
            if res: return res

    m_yr = re.search(r'(?:(20[12]\d)|(2[0-9])\s*년)', fn)
    if m_yr:
        yr = int(m_yr.group(1)) if m_yr.group(1) else (2000 + int(m_yr.group(2)))
        month_guess = 10 if ("하반기" in fn or "2차" in fn) else (5 if ("상반기" in fn or "1차" in fn) else 6)
        res = _safe_ymd(yr, month_guess, 1)
        if res: return res

    return (1900, 1, 1)

def format_iso_from_tuple(dt_tuple):
    if not dt_tuple or dt_tuple[0] <= 1900:
        return "일자 미기재"
    return f"{dt_tuple[0]:04d}-{dt_tuple[1]:02d}-{dt_tuple[2]:02d}"

def is_system_junk_file(filename):
    """윈도우/맥 시스템 임시 파일(Thumbs.db, desktop.ini 등)을 전 구간에서 원천 제외합니다."""
    fn_low = str(filename).strip().lower()
    if not fn_low:
        return True
    if fn_low in ("thumbs.db", "desktop.ini", ".ds_store") or fn_low.startswith("~$"):
        return True
    return False

def is_pest_vendor_doc(row_or_name, folder_path=""):
    if isinstance(row_or_name, dict):
        combined = f"{row_or_name.get('파일명', '')} {row_or_name.get('문서_실제제목', '')} {row_or_name.get('분류근거', '')} {folder_path}"
    else:
        combined = f"{row_or_name} {folder_path}"
    pest_markers = ["삼양인터내셔날", "삼양인터네셔날", "소독,해충구제", "방제업무", "방충방서 관련 서류", "배동섭", "남정현", "권도훈"]
    return any(pm in combined for pm in pest_markers)

def is_blacklisted(filename, category_name=""):
    fn = str(filename)
    if is_system_junk_file(fn) or fn.lower().endswith(".txt") or fn.lower().endswith(".hwp"):
        return True
    if category_name in ("인증서", "특수 인증") and any(x in fn for x in ["내부 심사", "내부심사", "실시(안)", "(안)", "리스트", "계획"]):
        return True
    if category_name == "인허가" and any(x in fn for x in ["폐기물", "실적보고", "수료증", "위생교육", "법정교육", "정기교육"]):
        return True
    return False

@st.cache_data(ttl=3600)
def get_target_folder_ids(_service, root_folder_id):
    folders = [root_folder_id]
    def fetch_children(parent_id):
        page_token = None
        while True:
            res = _service.files().list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="nextPageToken, files(id)", pageSize=1000, pageToken=page_token
            ).execute()
            for item in res.get('files', []):
                folders.append(item['id'])
                fetch_children(item['id'])
            page_token = res.get('nextPageToken')
            if not page_token:
                break
    try:
        fetch_children(root_folder_id)
    except Exception:
        pass
    return folders

@st.cache_data(ttl=3600)
def get_temp_building_root_id():
    service = get_drive_service()
    if not service:
        return None
    try:
        res = service.files().list(
            q="name contains '가설건축물' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id, name)", pageSize=10
        ).execute()
        files = res.get('files', [])
        if files:
            return files[0]['id']
    except Exception:
        pass
    return None

@st.cache_data(ttl=1800)
def get_subfolders_for_category(cat_name):
    """구글 드라이브 폴더 구조와 동일하게 최상위 폴더 및 모든 하위 폴더 트리 목록을 반환합니다."""
    service = get_drive_service()
    if not service:
        return []
    root_id = get_temp_building_root_id() if cat_name == "가설건축물" else FLAT_FOLDER_DB.get(cat_name, "")
    if not root_id or str(root_id).startswith("folder_id_"):
        return []

    sub_list = [{"id": root_id, "name": cat_name, "path": cat_name, "label": f"📂 {cat_name} (최상위 폴더)"}]
    def walk_sub(parent_id, path_prefix, depth):
        page_token = None
        while True:
            try:
                res = service.files().list(
                    q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                    fields="nextPageToken, files(id, name)", orderBy="name", pageSize=200, pageToken=page_token
                ).execute()
                for item in res.get('files', []):
                    indent = " " * (depth - 1) + "└ 📁 "
                    cur_path = f"{path_prefix} > {item['name']}"
                    sub_list.append({
                        "id": item['id'],
                        "name": item['name'],
                        "path": cur_path,
                        "label": f"{indent}{item['name']}"
                    })
                    walk_sub(item['id'], cur_path, depth + 1)
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
            except Exception:
                break
    walk_sub(root_id, cat_name, 1)
    return sub_list

@st.cache_data(ttl=1800)
def get_all_managed_folders_map(_service):
    folder_map = {}
    if DRIVE_FOLDER_ID:
        folder_map[DRIVE_FOLDER_ID] = "방문심사"
    all_roots = dict(FLAT_FOLDER_DB)
    tb_root = get_temp_building_root_id()
    if tb_root:
        all_roots["가설건축물"] = tb_root
    for cat_name, root_fid in all_roots.items():
        if not root_fid or str(root_fid).startswith("folder_id_"):
            continue
        folder_map[root_fid] = cat_name
        def fetch_sub(parent_id, parent_label):
            page_token = None
            while True:
                res = _service.files().list(
                    q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                    fields="nextPageToken, files(id, name)", pageSize=1000, pageToken=page_token
                ).execute()
                for item in res.get('files', []):
                    sub_label = f"{parent_label} > {item['name']}"
                    folder_map[item['id']] = sub_label
                    fetch_sub(item['id'], sub_label)
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
        try:
            fetch_sub(root_fid, cat_name)
        except Exception:
            pass
    return folder_map

@st.cache_data(ttl=1800)
def get_cached_folder_files(f_key):
    service = get_drive_service()
    if not service:
        return []
    root_id = get_temp_building_root_id() if f_key == "가설건축물" else FLAT_FOLDER_DB.get(f_key, "")
    if not root_id or str(root_id).startswith("folder_id_"):
        return []

    folder_map = get_all_managed_folders_map(service)
    target_folders = get_target_folder_ids(service, root_id)
    files_out = []
    seen = set()
    for idx in range(0, len(target_folders), 20):
        chunk = target_folders[idx:idx + 20]
        parents_q = " or ".join([f"'{fid}' in parents" for fid in chunk])
        page_token = None
        while True:
            try:
                res = service.files().list(
                    q=f"({parents_q}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                    spaces='drive',
                    fields='nextPageToken, files(id, name, webViewLink, mimeType, createdTime, parents)',
                    pageSize=1000, pageToken=page_token
                ).execute()
                for f in res.get('files', []):
                    if f['id'] in seen or is_system_junk_file(f.get('name', '')):
                        continue
                    seen.add(f['id'])
                    p_label = next((folder_map[p] for p in f.get('parents', []) if p in folder_map), f_key)
                    f['folder_path'] = p_label
                    files_out.append(f)
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
            except Exception:
                break
    return files_out

@st.cache_data(ttl=1800)
def get_temp_building_files():
    out = []
    for f in get_cached_folder_files("가설건축물"):
        if not is_blacklisted(f['name'], "인허가"):
            out.append({
                'id': f['id'], 'name': f['name'], 'kw': '가설건축물',
                'rtitle': f['name'], 'reason': '가설건축물 축조신고 및 존치기간 연장 증빙',
                'webViewLink': f.get('webViewLink', f"https://drive.google.com/file/d/{f['id']}/view"),
                'createdTime': f.get('createdTime', ''),
                'mimeType': f.get('mimeType', 'application/pdf'),
                'folder_path': f.get('folder_path', '가설건축물'),
                'parents': f.get('parents', []),
                'snippet': "", 'matched_pages': [1]
            })
    return out

@st.cache_data(ttl=900)
def get_drive_supplement_files():
    target_cats = ["인허가 서류", "인증서", "수질검사", "물탱크청소", "방충방서 관련 서류", "교육수료증", "모의회수", "PL보험가입증명서", "선행요건", "기준서", "FSSC22000"]
    supplement = []
    seen = set()
    for tc in target_cats:
        for f in get_cached_folder_files(tc):
            if f['id'] not in seen:
                seen.add(f['id'])
                supplement.append(f)
    return supplement

@st.cache_data(ttl=1800)
def get_cached_file_bytes(file_id):
    service = get_drive_service()
    if not service:
        return None
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

def download_file_bytes(service, file_id):
    return get_cached_file_bytes(file_id)

def clear_all_folder_caches():
    get_cached_folder_files.clear()
    get_drive_supplement_files.clear()
    get_temp_building_files.clear()
    get_subfolders_for_category.clear()
    get_all_managed_folders_map.clear()
    get_target_folder_ids.clear()

def create_drive_subfolder(parent_folder_id, new_folder_name):
    """문서 보관함에서 연도별·분류별 신규 하위 폴더를 구글 드라이브에 직접 생성합니다."""
    drive_service = get_drive_service()
    if not drive_service:
        return False, "구글 드라이브 인증 서비스를 초기화할 수 없습니다."
    clean_name = str(new_folder_name).strip()
    if not clean_name:
        return False, "생성할 하위 폴더명을 입력해 주십시오."
    try:
        meta = {
            "name": clean_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id]
        }
        created = drive_service.files().create(body=meta, fields="id, name").execute()
        clear_all_folder_caches()
        return True, created.get("id", "")
    except Exception as e:
        err_s = str(e)
        if "403" in err_s or "insufficientPermissions" in err_s or "scope" in err_s.lower():
            return False, "구글 드라이브 '쓰기(폴더 생성)' 권한이 없습니다. 관리자 secrets의 OAuth refresh_token을 전체 드라이브 권한(https://www.googleapis.com/auth/drive)으로 갱신해 주십시오."
        return False, f"폴더 생성 중 오류가 발생하였습니다: {e}"

def upload_and_scan_single_file(uploaded_file, target_folder_id):
    """현재 선택한 구글 드라이브 폴더로 파일을 업로드하고, 즉시 AI 메타데이터 추출 및 마스터 시트 DB에 반영합니다."""
    drive_service = get_drive_service()
    sheet_service = get_sheets_service()
    if not drive_service:
        return False, "구글 드라이브 인증 서비스를 초기화할 수 없습니다.", None

    file_name = uploaded_file.name
    raw_bytes = uploaded_file.getvalue()
    lower_nm = file_name.lower()
    if lower_nm.endswith(".pdf"):
        mime_type, ext = "application/pdf", ".pdf"
    elif lower_nm.endswith(".png"):
        mime_type, ext = "image/png", ".png"
    else:
        mime_type, ext = "image/jpeg", ".jpg"

    try:
        media = MediaIoBaseUpload(io.BytesIO(raw_bytes), mimetype=mime_type, resumable=True)
        meta_body = {"name": file_name, "parents": [target_folder_id]}
        created = drive_service.files().create(
            body=meta_body, media_body=media, fields="id, name, webViewLink, mimeType, createdTime"
        ).execute()
    except Exception as e:
        err_s = str(e)
        if "403" in err_s or "insufficientPermissions" in err_s or "scope" in err_s.lower():
            return False, "구글 드라이브 '쓰기(업로드)' 권한이 없습니다. 관리자 secrets의 OAuth refresh_token을 전체 드라이브 권한(https://www.googleapis.com/auth/drive)으로 갱신해 주십시오.", None
        return False, f"클라우드 폴더 업로드 중 오류가 발생하였습니다: {e}", None

    fid = created.get("id")
    web_link = created.get("webViewLink", f"https://drive.google.com/file/d/{fid}/view")

    tmp_path = None
    up_gemini = None
    parsed_summary = {}
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        up_gemini = genai.upload_file(path=tmp_path)
        wait_t = 0
        while up_gemini.state.name == "PROCESSING" and wait_t < 180:
            time.sleep(3)
            wait_t += 3
            up_gemini = genai.get_file(up_gemini.name)

        model = genai.GenerativeModel(MODEL_NAME)
        ai_res = model.generate_content([up_gemini, MASTER_SCAN_PROMPT])
        json_match = re.search(r'\{.*\}', ai_res.text.strip(), re.DOTALL)
        parsed = json.loads(json_match.group(0)) if json_match else {}

        allowed_dynamic_prefixes = ("가설건축물_", "수질검사_", "보건증_", "법정위생교육_", "HACCP교육_", "HACCP팀장")
        kw = parsed.get("키워드", "기타")
        if kw not in ("PASS", "기타", "매뉴얼", "일반수료증", "HACCP정기교육", "HACCP팀장및경영자교육") and kw not in MASTER_DOC_REQUIREMENTS and not str(kw).startswith(allowed_dynamic_prefixes):
            kw = "기타"

        cycle = str(MASTER_DOC_REQUIREMENTS.get(kw, {}).get("주기", 0))
        if str(kw).startswith("법정위생교육_") or kw == "HACCP정기교육":
            cycle = "12"

        new_row = [
            kw, file_name, parsed.get("문서_실제제목", file_name), parsed.get("발급일", "미상"), parsed.get("만료일", "영구"),
            cycle, parsed.get("개정번호", "-"), parsed.get("분류근거", "문서 보관함 직접 등록"), fid, web_link
        ]

        if sheet_service and SHEET_ID:
            sheet_service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID, range="DB!A:A", valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={'values': [new_row]}
            ).execute()
            sheet_service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID, range="SCANNED!A:B", valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={'values': [[fid, file_name]]}
            ).execute()

        ensure_auto_db_loaded()
        row_dict = {
            "키워드": kw, "파일명": file_name, "문서_실제제목": parsed.get("문서_실제제목", file_name),
            "발급일": parsed.get("발급일", "미상"), "만료일": parsed.get("만료일", "영구"), "주기(개월)": cycle,
            "개정번호": parsed.get("개정번호", "-"), "분류근거": parsed.get("분류근거", "문서 보관함 직접 등록"),
            "파일 ID": fid, "뷰어 링크": web_link
        }
        st.session_state.auto_db.append(row_dict)
        parsed_summary = row_dict
    except Exception as scan_err:
        parsed_summary = {"키워드": "미분류(수동확인)", "파일명": file_name, "발급일": "-", "만료일": "-", "오류참고": str(scan_err)}
    finally:
        try:
            if up_gemini:
                genai.delete_file(up_gemini.name)
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    clear_all_folder_caches()
    doc_obj = {
        "id": fid, "name": file_name, "webViewLink": web_link,
        "mimeType": mime_type, "folder_path": "신규 등록 문서"
    }
    return True, doc_obj, parsed_summary

def normalize_education_key(fname, rtitle="", reason=""):
    combined = f"{fname} {rtitle} {reason}"
    comb_nospace = combined.replace(" ", "")
    if "HACCP" in combined.upper():
        if any(x in comb_nospace for x in ["팀장", "경영자"]):
            return ("HACCP팀장및경영자교육", "식약처 HACCP 팀장·경영자과정 수료증", 0)
        if any(x in comb_nospace for x in ["정기교육", "통합과정", "정기과정"]):
            return ("HACCP정기교육", "식품·축산물 HACCP 정기교육 수료증 (연간)", 12)
    edu_rules = [
        (["책임수의사", "첵임수의사", "수의사회"], "법정위생교육_책임수의사", "축산물 위생교육 (책임수의사 보수교육)"),
        (["수입식품"], "법정위생교육_수입식품영업", "기존영업자 위생교육 (수입식품등 수입·판매업)"),
        (["식품제조가공업"], "법정위생교육_식품제조가공업", "기존영업자 위생교육 (식품제조가공업)"),
        (["축산물가공업", "유가공업"], "법정위생교육_축산물가공업", "축산물 위생교육 (축산물가공업·유가공업)"),
        (["집유업"], "법정위생교육_집유업", "축산물 위생교육 (집유업)"),
        (["우유류판매업", "축산물판매"], "법정위생교육_우유류판매업", "축산물 위생교육 (우유류판매업)"),
        (["유통전문판매업"], "법정위생교육_유통전문판매업", "위생교육 (유통전문판매업)"),
        (["일반판매업", "건강기능식품판매", "건기식"], "법정위생교육_건강기능식품판매업", "건강기능식품 보수교육 (일반판매업)"),
        (["집단급식소"], "법정위생교육_집단급식소", "식품위생교육 (집단급식소)"),
        (["화장품책임판매"], "법정위생교육_화장품책임판매", "화장품 책임판매관리자 법정교육"),
    ]
    for triggers, norm_key, disp_label in edu_rules:
        if any(t in comb_nospace for t in triggers):
            return (norm_key, disp_label, 12)
    return (None, None, 0)

def deduplicate_latest_by_slot(files, slot_fn):
    best_by_slot = {}
    for f in files:
        slot = str(slot_fn(f))
        score = parse_doc_date_tuple(f.get('name', ''), f.get('createdTime', ''))
        if slot not in best_by_slot or score >= best_by_slot[slot][0]:
            best_by_slot[slot] = (score, f)
    sorted_items = sorted(best_by_slot.values(), key=lambda x: x[0], reverse=True)
    return [item[1] for item in sorted_items]

def sort_by_priority_patterns(files, patterns):
    def rank_key(f):
        nm = f"{f.get('kw', '')} {f.get('name', '')} {f.get('rtitle', '')}".replace(" ", "").lower()
        for idx, pat in enumerate(patterns):
            if isinstance(pat, tuple):
                inc, exc = pat
                if inc.replace(" ", "").lower() in nm and not any(e.replace(" ", "").lower() in nm for e in exc):
                    return (idx, tuple(-x for x in parse_doc_date_tuple(f.get('name', ''), f.get('createdTime', ''))))
            else:
                if pat.replace(" ", "").lower() in nm:
                    return (idx, tuple(-x for x in parse_doc_date_tuple(f.get('name', ''), f.get('createdTime', ''))))
        return (999, tuple(-x for x in parse_doc_date_tuple(f.get('name', ''), f.get('createdTime', ''))))
    return sorted(files, key=rank_key)

def extract_leading_num(filename):
    m = re.match(r'^\s*(\d+)[.\s)_]', str(filename))
    return int(m.group(1)) if m else 999

def deduplicate_fssc_docs(files):
    best = {}
    for f in files:
        nm = f.get('name', '')
        m_code = re.search(r'(YS-[가-힣A-Za-z]+-[MPI]-\d+)', nm, re.IGNORECASE)
        slot = m_code.group(1).upper() if m_code else re.sub(r'\(.*?\)|_rev\d+|_v\d+', '', nm, flags=re.IGNORECASE).strip()
        score = parse_doc_date_tuple(nm, f.get('createdTime', ''))
        if slot not in best or score >= best[slot][0]:
            best[slot] = (score, f)
    return [v[1] for v in best.values()]

def get_subtabs_for_category(category_key, files):
    if category_key == "인허가":
        def lic_slot(f):
            nm = f['name'].replace(" ", "")
            kw = str(f.get('kw', ''))
            if "사업자등록" in nm or kw == "사업자등록":
                return "사업자_생활건강" if "생활건강" in nm else "사업자_연세유업"
            if "공장등록" in nm or kw == "공장등록":
                return "공장등록"
            if "건축물대장" in nm or kw == "건축물대장":
                return "건축물대장"
            if "가설건축물" in nm or kw.startswith("가설건축물"):
                m_dong = re.search(r'\(([^)]*동)\)', nm)
                return f"가설_{m_dong.group(1)}" if m_dong else f"가설_{nm[:16]}"
            if "우유류판매" in nm:
                return "우유류판매업"
            if "유통전문" in nm and "축산물" in nm:
                return "축산물유통전문판매업"
            for k_cand, markers in [
                ("축산물가공업", ["축산물가공업", "유가공업"]),
                ("집유업", ["집유업"]),
                ("식품제조가공업", ["식품제조가공업"]),
                ("수입식품영업", ["수입식품"]),
                ("식품소분업", ["식품소분"]),
                ("건강기능식품영업", ["건강기능식품"]),
                ("지하수개발허가", ["지하수개발", "지하수이용"]),
                ("통신판매업", ["통신판매"]),
                ("방문판매업", ["방문판매"]),
                ("집단급식소", ["집단급식소"]),
                ("화장품책임판매", ["화장품책임판매"]),
            ]:
                if kw == k_cand or any(mk in nm for mk in markers):
                    return k_cand
            return kw or nm[:18]

        deduped = deduplicate_latest_by_slot(files, lic_slot)
        t_biz, t_dairy, t_food, t_bldg, t_etc = [], [], [], [], []
        for f in deduped:
            sl = lic_slot(f)
            if sl in ("사업자_연세유업", "사업자_생활건강", "공장등록"):
                t_biz.append(f)
            elif sl in ("축산물가공업", "집유업", "우유류판매업", "축산물유통전문판매업", "축산물판매업"):
                t_dairy.append(f)
            elif sl in ("식품제조가공업", "수입식품영업", "식품소분업", "건강기능식품영업"):
                t_food.append(f)
            elif sl == "건축물대장" or sl.startswith("가설_"):
                t_bldg.append(f)
            else:
                t_etc.append(f)

        return {
            "🏢 사업자·공장등록": sort_by_priority_patterns(t_biz, [("연세유업", ["생활건강"]), "공장등록", "생활건강"]),
            "🥛 유제품(축산물) 인허가": sort_by_priority_patterns(t_dairy, ["축산물가공업", "유가공업", "집유업", "우유류판매", "축산물유통전문", "축산물판매"]),
            "🍱 식품·건기식 인허가": sort_by_priority_patterns(t_food, ["식품제조가공업", "수입식품", "식품소분", "건강기능식품"]),
            "🏗️ 건축물·가설건축물": sort_by_priority_patterns(t_bldg, ["건축물대장", "1~7동", "1동", "2~4동", "5~6동", "가설건축물"]),
            "📋 기타 영업·지하수": sort_by_priority_patterns(t_etc, ["지하수", "통신판매", "방문판매", "집단급식소", "화장품"])
        }

    elif category_key == "인증서":
        def cert_slot(f):
            kw = str(f.get('kw', ''))
            nm = f['name'].upper()
            if kw and kw not in ("매뉴얼", "기타"):
                return kw
            if "CHINA" in nm or "延世" in nm or "主证" in nm: return "CHINA_HACCP"
            if "FSSC" in nm: return "FSSC22000"
            if "FFR" in nm: return "FDA_FFR"
            if "FCE" in nm: return "FDA_FCE"
            for sub_k in ["유가공", "가공두유", "원액두유", "과채주스", "과채음료", "혼합음료", "유산균음료", "커피", "액상차", "환자", "균형영양"]:
                if sub_k in f['name']:
                    return f"HACCP_{sub_k}"
            return re.sub(r'\(.*?\)', '', f['name']).strip()

        deduped = deduplicate_latest_by_slot(files, cert_slot)
        t_main_haccp, t_bev_haccp, t_fssc, t_global = [], [], [], []
        for f in deduped:
            sl = cert_slot(f)
            if sl == "FSSC22000":
                t_fssc.append(f)
            elif sl in ("CHINA_HACCP", "FDA_FFR", "FDA_FCE"):
                t_global.append(f)
            elif any(k in f"{sl} {f['name']}" for k in ["유가공", "우유", "가공두유", "원액두유"]):
                t_main_haccp.append(f)
            else:
                t_bev_haccp.append(f)

        return {
            "🥇 식약처 HACCP (유제품·두유)": sort_by_priority_patterns(t_main_haccp, ["유가공", "가공두유", "원액두유"]),
            "🥤 식약처 HACCP (음료·환자식)": sort_by_priority_patterns(t_bev_haccp, ["과채주스", "과채음료", "혼합음료", "유산균음료", "커피", "액상차", "환자"]),
            "🌐 FSSC 22000 인증서": t_fssc,
            "🚢 해외 인증·등록 (China·FDA)": sort_by_priority_patterns(t_global, ["CHINA", "延世", "FFR", "FCE"])
        }

    elif category_key == "특수 인증":
        t1 = [f for f in files if f.get('kw') == "K-MILK" or "MILK" in f['name'].upper() or "국산우유" in f['name']]
        t2 = [f for f in files if f.get('kw') == "무항생제" or "무항생제" in f['name']]
        t3 = [f for f in files if f.get('kw') == "유기가공식품" or "유기" in f['name']]
        return {
            "🥛 K-MILK 인증서": deduplicate_latest_by_slot(t1, lambda x: "KMILK"),
            "🌿 무항생제 인증서": deduplicate_latest_by_slot(t2, lambda x: "무항생제"),
            "🌱 유기가공식품 인증서": deduplicate_latest_by_slot(t3, lambda x: "유기가공")
        }

    elif category_key == "FSSC 22000 기준서":
        deduped = deduplicate_fssc_docs(files)
        t_q, t_m, t_p, t_prod, t_sup = [], [], [], [], []
        for f in deduped:
            nm = f['name']
            if any(x in nm for x in ["YS-품질", "품질경영매뉴얼", "YS-경영"]):
                t_q.append(f)
            elif "YS-관리" in nm:
                t_m.append(f)
            elif "YS-구매" in nm:
                t_p.append(f)
            elif any(x in nm for x in ["YS-생관", "YS-공무환경", "YS-환경", "YS-연구"]):
                t_prod.append(f)
            elif "YS-지원" in nm:
                t_sup.append(f)
            else:
                t_q.append(f)
        return {
            "📘 매뉴얼·경영·품질": sort_by_priority_patterns(t_q, ["M-100", "품질경영매뉴얼", "경영-P-100", "경영-P-200", "품질-P-100", "품질-P-200", "품질-P-210", "품질-P-300", "품질-P-500", "품질-P-600", "품질-P-700", "품질-P-800", "품질-P-900"]),
            "🛡️ 관리·보안·안전": sort_by_priority_patterns(t_m, ["P-210", "식품보안", "비상사태", "P-220", "P-300", "파일링"]),
            "🤝 구매·협력업체": sort_by_priority_patterns(t_p, ["구매-P-200", "협력업체", "구매-P-100", "구매-P-300", "식품사기", "구매-P-400"]),
            "🏭 생산·설비·환경·연구": sort_by_priority_patterns(t_prod, ["생관-P-100", "생관-P-200", "생관-P-300", "생관-P-400", "공무환경", "환경-P-100", "연구"]),
            "🎓 문서·교육·자격지원": sort_by_priority_patterns(t_sup, ["지원-P-100", "지원-P-200", "지원-P-300", "지원-P-400", "지원-P-500"])
        }

    elif category_key == "기준서":
        prp_keywords = ["작업장기준서", "제조시설", "위생관리기준서", "이물관리기준서", "장갑관리", "냉장냉동", "해동관리", "검사관리", "알러겐", "보관 및 운반", "용수관리", "제품회수"]
        t_prp, t_dairy_h, t_soy_h = [], [], []
        for f in files:
            fp = str(f.get('folder_path', ''))
            nm = f['name']
            if "선행요건" in fp or any(pk in nm for pk in prp_keywords):
                t_prp.append(f)
            elif any(dk in f"{fp} {nm}" for dk in ["우유", "멸균유", "발효유", "집유장"]):
                t_dairy_h.append(f)
            else:
                t_soy_h.append(f)
        return {
            "📋 선행요건 기준서 (1~12번)": sorted(t_prp, key=lambda x: (extract_leading_num(x['name']), x['name'])),
            "🥛 유제품·집유장 HACCP 기준서": sorted(t_dairy_h, key=lambda x: (x.get('folder_path', ''), extract_leading_num(x['name']))),
            "🫘 두유·음료·환자식 HACCP 기준서": sorted(t_soy_h, key=lambda x: (x.get('folder_path', ''), extract_leading_num(x['name'])))
        }

    elif category_key == "위생 절차":
        t_hyg = [f for f in files if any(x in f['name'] for x in ["위생관리", "장갑관리"])]
        t_work = [f for f in files if "작업장" in f['name']]
        t_alg = [f for f in files if "알러겐" in f['name']]
        return {
            "🧼 개인위생·복장·장갑 기준서": sort_by_priority_patterns(t_hyg, ["위생관리", "장갑관리"]),
            "🦟 작업장·방충방서 기준서": t_work,
            "🥜 알러겐 관리 기준서": t_alg
        }

    elif category_key == "보안 절차":
        t_fm = [f for f in files if "이물" in f['name']]
        t_sec = [f for f in files if any(x in f['name'] for x in ["식품보안", "P-210"])]
        t_frd = [f for f in files if any(x in f['name'] for x in ["식품사기", "구매-P-300"])]
        return {
            "🔍 이물관리 기준서": t_fm,
            "🔐 식품보안 관리 규정 (P-210)": deduplicate_fssc_docs(t_sec),
            "🛡️ 식품사기 대응 규정 (P-300)": deduplicate_fssc_docs(t_frd)
        }

    elif category_key == "회수 절차":
        t_rec = [f for f in files if "제품회수" in f['name']]
        t_cri = [f for f in files if any(x in f['name'] for x in ["위기관리", "비상사태"])]
        t_nc = [f for f in files if any(x in f['name'] for x in ["부적합", "시정조치", "고객불만"])]
        return {
            "🚨 제품회수 관리 기준서": t_rec,
            "⚡ 위기관리·비상사태 규정": deduplicate_fssc_docs(t_cri),
            "📋 부적합·시정조치·고객불만 규정": deduplicate_fssc_docs(t_nc)
        }

    elif category_key == "수질검사":
        t_tap, t_gw, t_noro, t_tank = [], [], [], []
        for f in files:
            comb = f"{f['name']} {f.get('folder_path', '')} {f.get('kw', '')}"
            if any(aux in comb for aux in ["청소사진", "청소 사진", "사업소 서식", "사업본부서식", "간이수질", "청소 기준", "신고증"]):
                continue
            if "노로" in comb:
                t_noro.append(f)
            elif any(x in comb for x in ["저수조", "물탱크"]):
                t_tank.append(f)
            elif any(x in comb for x in ["먹는물", "상수도", "수돗물"]):
                t_tap.append(f)
            else:
                t_gw.append(f)
        return {
            "🚰 먹는물(상수도) 수질검사": deduplicate_latest_by_slot(t_tap, lambda x: "먹는물"),
            "💧 지하수 수질검사 (최신)": deduplicate_latest_by_slot(t_gw, lambda x: "지하수"),
            "🧬 노로바이러스 검사": deduplicate_latest_by_slot(t_noro, lambda x: "노로"),
            "🧼 저수조 청소필증·보고서": deduplicate_latest_by_slot(t_tank, lambda x: "필증" if "필증" in x['name'] else "결과보고서")
        }

    elif category_key == "방제 레포트":
        t_map = [f for f in files if any(x in f['name'] for x in ["도면", "배치도"])]
        t_con = [f for f in files if "계약서" in f['name']]
        t_ven = [f for f in files if any(x in f['name'] for x in ["인허가", "보험", "삼양"])]
        t_hc = [f for f in files if "보건증" in f['name']]
        return {
            "🗺️ 방역 도면·배치도": deduplicate_latest_by_slot(t_map, lambda x: "방역도면"),
            "📝 방역 위탁 계약서": deduplicate_latest_by_slot(t_con, lambda x: "방역계약서"),
            "🏢 방역업체 적격증빙 (인허가·보험)": sort_by_priority_patterns(deduplicate_latest_by_slot(t_ven, lambda x: "방역보험" if "보험" in x['name'] else "방역인허가"), ["인허가", "보험"]),
            "🪪 방역기사 보건증": deduplicate_latest_by_slot(t_hc, lambda x: re.sub(r'\(.*?\)', '', x['name']).strip())
        }

    elif category_key == "보건증/교육":
        t_dairy_edu, t_food_edu, t_haccp, t_hc = [], [], [], []
        for f in files:
            if is_pest_vendor_doc(f, f.get('folder_path', '')):
                continue
            norm_k, _, _ = normalize_education_key(f['name'], f.get('rtitle', ''), f.get('reason', ''))
            if "보건증" in f['name'] or str(f.get('kw', '')).startswith("보건증"):
                t_hc.append(f)
            elif norm_k in ("HACCP정기교육", "HACCP팀장및경영자교육"):
                t_haccp.append(f)
            elif norm_k in ("법정위생교육_축산물가공업", "법정위생교육_집유업", "법정위생교육_우유류판매업", "법정위생교육_책임수의사"):
                f['_norm_edu'] = norm_k
                t_dairy_edu.append(f)
            elif norm_k and norm_k.startswith("법정위생교육_"):
                f['_norm_edu'] = norm_k
                t_food_edu.append(f)
        return {
            "🥛 유제품·축산·수의사 법정교육": sort_by_priority_patterns(deduplicate_latest_by_slot(t_dairy_edu, lambda x: x.get('_norm_edu', x['name'])), ["축산물가공업", "유가공업", "집유업", "우유류판매", "수의사"]),
            "🍱 식품·건기식·기타 법정교육": sort_by_priority_patterns(deduplicate_latest_by_slot(t_food_edu, lambda x: x.get('_norm_edu', x['name'])), ["식품제조가공업", "수입식품", "유통전문", "일반판매", "건기식", "집단급식소", "화장품"]),
            "🛡️ HACCP 정기·팀장·경영자 교육": sort_by_priority_patterns(deduplicate_latest_by_slot(t_haccp, lambda x: "정기" if "정기" in x['name'] else x['name']), ["정기", "팀장", "경영자"]),
            "🪪 자사 종사자 보건증": deduplicate_latest_by_slot(t_hc, lambda x: x['name'])
        }

    elif category_key == "설비이력":
        t_hist = [f for f in files if "설비이력" in str(f.get('folder_path', ''))]
        t_std = [f for f in files if f not in t_hist]
        return {
            "🔧 설비 유지보수 이력 문서": sorted(t_hist, key=lambda x: parse_doc_date_tuple(x['name'], x.get('createdTime', '')), reverse=True),
            "📘 제조시설·생산설비 관리 기준서": deduplicate_fssc_docs(t_std)
        }

    elif category_key == "모의회수":
        t_rec_res = [f for f in files if "제품회수관리기준서" not in f['name']]
        t_rec_std = [f for f in files if "제품회수관리기준서" in f['name']]
        return {
            "📊 모의회수·추적성 훈련 결과 (최신)": sorted(t_rec_res, key=lambda x: parse_doc_date_tuple(x['name'], x.get('createdTime', '')), reverse=True),
            "📘 제품회수 관리 기준서": t_rec_std
        }

    sorted_default = sorted(files, key=lambda x: parse_doc_date_tuple(x.get('name', ''), x.get('createdTime', '')), reverse=True)
    return {f"📄 {category_key} 관련 기준 및 최신 문서": sorted_default}
# ==========================================
# [3-계속] 통합 문서 검색(본문·연관제목), 고해상도 원문 뷰어 및 공식 좌측 사이드바
# ==========================================
DEEP_SEARCH_SYNONYM_GROUPS = [
    ["물탱크", "저수조", "청소필증"],
    ["먹는물", "상수도", "수돗물", "음용수", "제품수", "용수", "지하수", "수질검사"],
    ["알레르기", "알러지", "알러겐", "유발물질"],
    ["해충", "벌레", "방충", "방서", "방역", "포획기", "포충등", "쥐", "바퀴", "파리", "나방"],
    ["클레임", "고객불만", "소비자불만", "부적합", "시정조치"],
    ["리콜", "회수", "모의회수", "추적성", "위해식품"],
    ["보수교육", "위생교육", "정기교육", "법정교육", "교육훈련", "수료증"],
    ["영업등록", "영업신고", "영업허가", "영업장등록", "영업장신고", "인허가"],
    ["가설건축물", "존치기간", "축조신고", "건축물대장"],
    ["복장", "위생복", "위생화", "손소독", "손위생", "개인위생", "건강진단", "보건증", "장갑", "위생관리"],
    ["검교정", "교정", "계측기", "온도계", "저울", "유량계", "검사관리"],
    ["과수", "과산화수소", "무균포장", "테트라팩", "콤비팩", "콤비블럭", "카톤팩"],
    ["금속검출", "자석봉", "영구자석", "가우스", "여과망", "메쉬", "mesh", "이물"],
    ["보안", "식품보안", "테러", "제한구역", "통제구역", "시건장치", "cctv", "식품사기"],
    ["세척", "소독", "cip", "가성소다", "질산", "제조시설"],
    ["보관", "운반", "운송", "창고온도", "냉장", "냉동", "해동"],
    ["협력업체", "공급사", "판매원", "원부자재", "입고검수"],
    ["보험", "배상책임", "생산물배상", "pl보험", "책임보험"]
]

def expand_related_title_terms(keyword):
    kw_comp = keyword.replace(" ", "").lower()
    tokens = [t.lower() for t in re.split(r'\s+', keyword) if len(t) >= 2]
    related = set()
    for grp in DEEP_SEARCH_SYNONYM_GROUPS:
        grp_low = [g.lower() for g in grp]
        if any(g in kw_comp or kw_comp in g for g in grp_low) or any(tk in g for tk in tokens for g in grp_low):
            for g in grp_low:
                if g != kw_comp:
                    related.add(g)
    return list(related)

def analyze_pdf_matches_strict(file_bytes, keyword):
    if not PYMUPDF_INSTALLED or not file_bytes or not keyword:
        return [], ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        matched_pages = []
        snippets = []
        kw_clean = keyword.strip()
        tokens = [t for t in re.split(r'\s+', kw_clean) if t]
        if not tokens:
            doc.close()
            return [], ""

        compact_pat = re.compile(r'\s*'.join([re.escape(t) for t in tokens]), re.IGNORECASE)
        prox_pat = None
        if len(tokens) >= 2:
            prox_pat = re.compile(re.escape(tokens[0]) + r'.{0,35}' + re.escape(tokens[1]), re.IGNORECASE)

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = re.sub(r'\s+', ' ', page.get_text("text"))
            m = compact_pat.search(text)
            if not m and prox_pat:
                m = prox_pat.search(text)
            if m:
                matched_pages.append(page_num + 1)
                if len(snippets) < 3:
                    idx = m.start()
                    start = max(0, idx - 55)
                    end = min(len(text), m.end() + 100)
                    snippets.append(f"[p.{page_num + 1}] ...{text[start:end]}...")
        doc.close()
        return matched_pages, " / ".join(snippets)
    except Exception:
        return [], ""

def render_paper_pdf_pages(file_bytes, start_page, keyword="", continuous=False, dpi_scale=2.5):
    if not PYMUPDF_INSTALLED or not file_bytes:
        return [], 0, []
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            return [], 0, []

        kw_clean = keyword.strip() if keyword else ""
        matched_pages, _ = analyze_pdf_matches_strict(file_bytes, kw_clean) if kw_clean else ([], "")

        s_idx = max(0, min(int(start_page) - 1, total_pages - 1))
        end_idx = min(total_pages, s_idx + 4) if continuous else (s_idx + 1)

        out_images = []
        for p_idx in range(s_idx, end_idx):
            page = doc[p_idx]
            if kw_clean:
                rects = page.search_for(kw_clean)
                if not rects:
                    rects = page.search_for(kw_clean.replace(" ", ""))
                if not rects:
                    for token in [t for t in re.split(r'[\s,()/·~:-]+', kw_clean) if len(t) >= 2]:
                        rects.extend(page.search_for(token))
                for r in rects:
                    annot = page.add_highlight_annot(r)
                    annot.set_colors(stroke=(0.65, 0.92, 0.45))
                    annot.update()
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale))
            out_images.append((p_idx + 1, pix.tobytes("png")))

        doc.close()
        return out_images, total_pages, matched_pages
    except Exception:
        return [], 0, []

def render_full_height_doc_viewer(doc_info, highlight_kw="", viewer_context="tab1"):
    """우측 화면 전체 높이를 사용하는 공식 고해상도 문서 열람 뷰어 (열람실·보관함·규정검증 공용)"""
    fid = doc_info['id']
    doc_name = doc_info.get('name', '증빙 문서')
    view_url = doc_info.get('webViewLink', f"https://drive.google.com/file/d/{fid}/view")
    preview_url = f"https://drive.google.com/file/d/{fid}/preview"
    mime_str = str(doc_info.get('mimeType', 'application/pdf')).lower()

    st.markdown("<div class='paper-header-box'>", unsafe_allow_html=True)
    if viewer_context in ("chat", "explorer"):
        h1, h2, h3 = st.columns([5.8, 2.3, 1.9])
        with h1:
            st.markdown(f"**📄 {doc_name}**")
            if doc_info.get('reason'):
                st.caption(f"📌 적용 근거: {doc_info['reason']}")
            elif doc_info.get('folder_path'):
                st.caption(f"📂 보관 경로: {doc_info['folder_path']}")
        with h2:
            st.link_button("🔗 별도 창 열람", view_url, use_container_width=True)
        with h3:
            if st.button("✖ 열람창 닫기", key=f"close_{viewer_context}_{fid}", use_container_width=True):
                if viewer_context == "chat":
                    st.session_state.chat_doc_viewer = None
                else:
                    st.session_state.explorer_active_doc = None
                st.rerun()
    else:
        h1, h2 = st.columns([7.2, 2.8])
        with h1:
            st.markdown(f"**📄 {doc_name}**")
            if doc_info.get('folder_path'):
                st.caption(f"📂 보관 경로: {doc_info['folder_path']}")
        with h2:
            st.link_button("🔗 원문 별도 창 열람", view_url, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if viewer_context == "chat":
        current_p = int(doc_info.get('page', 1))
    elif viewer_context == "explorer":
        current_p = int(st.session_state.explorer_page_num)
    else:
        current_p = int(st.session_state.selected_page_num)

    def _set_viewer_page(new_val):
        if viewer_context == "chat":
            st.session_state.chat_doc_viewer['page'] = int(new_val)
        elif viewer_context == "explorer":
            st.session_state.explorer_page_num = int(new_val)
        else:
            st.session_state.selected_page_num = int(new_val)

    if "image" in mime_str or doc_name.lower().endswith((".png", ".jpg", ".jpeg")):
        img_raw = get_cached_file_bytes(fid)
        if img_raw:
            st.image(img_raw, use_container_width=True)
        else:
            st.components.v1.iframe(preview_url, height=960, scrolling=True)
        return

    if PYMUPDF_INSTALLED:
        ctrl1, ctrl2 = st.columns([6.8, 3.2])
        with ctrl1:
            v_mode = st.radio(
                "문서 열람 방식",
                ["📄 고해상도 원문 보기 (열람·확인용)", "🌐 문서 전체 스크롤 보기"],
                horizontal=True,
                label_visibility="collapsed",
                key=f"vmode_{viewer_context}_{fid}"
            )
        with ctrl2:
            cont_view = st.checkbox("📑 연속 페이지 표시", value=False, key=f"cont_{viewer_context}_{fid}")

        if "고해상도" in v_mode:
            f_bytes = get_cached_file_bytes(fid)
            pages_rendered, total_p, m_pages = render_paper_pdf_pages(
                f_bytes, current_p, keyword=highlight_kw, continuous=cont_view, dpi_scale=2.5
            )
            if pages_rendered:
                if total_p > 1:
                    nv1, nv2, nv3, nv4 = st.columns([2.2, 2.2, 2.2, 3.4])
                    with nv1:
                        if st.button("◀ 이전 면", key=f"prv_{viewer_context}_{fid}", use_container_width=True) and current_p > 1:
                            _set_viewer_page(current_p - 1)
                            st.rerun()
                    with nv2:
                        if st.button("다음 면 ▶", key=f"nxt_{viewer_context}_{fid}", use_container_width=True) and current_p < total_p:
                            _set_viewer_page(current_p + 1)
                            st.rerun()
                    with nv3:
                        jump_p = st.number_input(
                            "페이지 이동", min_value=1, max_value=max(1, total_p),
                            value=min(current_p, max(1, total_p)),
                            label_visibility="collapsed",
                            key=f"jmp_{viewer_context}_{fid}_{current_p}"
                        )
                        if jump_p != current_p:
                            _set_viewer_page(jump_p)
                            st.rerun()
                    with nv4:
                        if m_pages:
                            st.caption(f"🖍️ 검색어 위치: p.{', p.'.join(map(str, m_pages[:6]))} (총 {total_p}면)")
                        else:
                            st.caption(f"📄 {current_p} / {total_p} 면")
                elif m_pages and highlight_kw:
                    st.caption(f"🖍️ '{highlight_kw}' 해당 구절 음영 표시 완료")

                for p_no, png_bytes in pages_rendered:
                    if len(pages_rendered) > 1:
                        st.caption(f"— {p_no} / {total_p} 면 —")
                    st.image(png_bytes, use_container_width=True)
            else:
                st.components.v1.iframe(preview_url, height=960, scrolling=True)
        else:
            st.components.v1.iframe(preview_url, height=960, scrolling=True)
    else:
        st.components.v1.iframe(preview_url, height=960, scrolling=True)

def generate_on_demand_briefing(top_file, context_label=""):
    fid = top_file['id']
    if fid in st.session_state.briefing_cache:
        return st.session_state.briefing_cache[fid]

    q_label = context_label or st.session_state.search_question or top_file.get('name', '공식 증빙 서류')
    tmp_doc_path = None
    gemini_file = None
    try:
        file_bytes = get_cached_file_bytes(fid)
        file_ext = ".pdf" if "pdf" in str(top_file.get('mimeType', 'pdf')).lower() else ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_doc:
            tmp_doc.write(file_bytes)
            tmp_doc_path = tmp_doc.name

        gemini_file = genai.upload_file(path=tmp_doc_path)
        cache_name = st.session_state.get("master_cache_name")

        prompt = f"""다음 조회 항목에 대하여 외부 심사원 및 경영진 보고에 적합한 격식 있고 정중한 비즈니스 경어체(~합니다, ~입니다)로 브리핑을 작성하십시오: {q_label}
        1. 📋 [문서 적합성 확인]: 현재 열람 중인 문서가 '{q_label}' 관련 증빙 서류에 부합하는지 문서 제목, 발급 기관 및 본문 내용을 대조하여 1문장으로 명확히 기술하십시오.
        2. 💡 [사내 기준 및 법령 연계 요약]: 본 문서와 연계된 사내 HACCP/선행요건 관리 기준 및 법적 요구사항을 요약하십시오.
        3. 📄 [문서 핵심 정보 요약]: 발급일, 유효기간(만료일), 개정 상태(Rev) 및 주요 핵심 내용을 간결하게 정리하십시오."""

        if cache_name:
            try:
                cache = genai.caching.CachedContent.get(cache_name)
                model = genai.GenerativeModel.from_cached_content(cached_content=cache)
                res = model.generate_content([gemini_file, prompt])
            except Exception:
                model = genai.GenerativeModel(model_name=MODEL_NAME)
                kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False)
                res = model.generate_content([gemini_file, f"[지식베이스]\n{kb_str}\n{prompt}"])
        else:
            model = genai.GenerativeModel(model_name=MODEL_NAME)
            kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False)
            res = model.generate_content([gemini_file, f"[지식베이스]\n{kb_str}\n{prompt}"])

        st.session_state.briefing_cache[fid] = res.text
        return res.text
    except Exception as e:
        return f"⚠️ 문서 요약 분석 중 오류가 발생하였습니다.\n상세 내역: {e}"
    finally:
        try:
            if gemini_file:
                genai.delete_file(gemini_file.name)
            if tmp_doc_path and os.path.exists(tmp_doc_path):
                os.remove(tmp_doc_path)
        except Exception:
            pass

def execute_exact_match(display_keyword, folder_key=None, gw_keyword=None, priority_keywords=None, filter_folder_files=False):
    ensure_auto_db_loaded()
    gw_list = [g for g in gw_keyword if g] if isinstance(gw_keyword, list) else ([gw_keyword.strip()] if isinstance(gw_keyword, str) and gw_keyword.strip() else [])

    st.session_state.active_main_tab = MAIN_TABS[0]
    st.session_state["main_nav_radio"] = MAIN_TABS[0]
    st.session_state.update({
        "search_done": True, "search_mode": "exact",
        "search_keyword": display_keyword, "search_question": display_keyword,
        "target_folder_key": folder_key,
        "gw_keyword": gw_list[0] if gw_list else "",
        "gw_keywords_list": gw_list,
        "priority_keywords": priority_keywords or [], "last_file_id": "",
        "selected_doc_idx": 0, "selected_page_num": 1,
        "aux_files": [], "show_briefing": False
    })

    db_list = st.session_state.auto_db
    matched_files, aux_files, seen_fids = [], [], set()
    strict_kw_categories = {"인허가", "인증서", "특수 인증", "책임보험"}

    if db_list and priority_keywords:
        for row in db_list:
            fid = row.get("파일 ID", "")
            if not fid or fid in seen_fids:
                continue
            kw = str(row.get("키워드", "")).strip()
            fname = str(row.get("파일명", "")).strip()
            real_title = str(row.get("문서_실제제목", "")).strip()
            reason = str(row.get("분류근거", "")).strip()

            if is_blacklisted(fname, display_keyword):
                continue
            if display_keyword in ("책임보험", "인허가", "보건증/교육") and is_pest_vendor_doc(row):
                continue

            is_match = False
            if display_keyword in strict_kw_categories:
                for req_kw in priority_keywords:
                    if kw == req_kw or (req_kw == "가설건축물" and kw.startswith("가설건축물")):
                        is_match = True
                        break
            else:
                combined_target = f"{kw} {fname} {real_title}".replace(" ", "").lower()
                for req_kw in priority_keywords:
                    if req_kw.replace(" ", "").lower() in combined_target:
                        if display_keyword not in ("인증서", "특수 인증") and kw.startswith("HACCP_"):
                            continue
                        is_match = True
                        break

            if is_match:
                seen_fids.add(fid)
                matched_files.append({
                    'id': fid, 'name': fname or real_title, 'kw': kw,
                    'rtitle': real_title, 'reason': reason,
                    'webViewLink': row.get("뷰어 링크", f"https://drive.google.com/file/d/{fid}/view"),
                    'createdTime': row.get("발급일", ""), 'mimeType': 'application/pdf',
                    'folder_path': kw, 'snippet': "", 'matched_pages': [1]
                })

    if folder_key:
        folder_keys_to_search = [folder_key] if isinstance(folder_key, str) else folder_key
        for f_key in folder_keys_to_search:
            for f in get_cached_folder_files(f_key):
                if f['id'] in seen_fids or is_blacklisted(f['name'], display_keyword):
                    continue
                f_path = f.get('folder_path', f_key)
                if display_keyword in ("책임보험", "인허가", "보건증/교육") and is_pest_vendor_doc(f['name'], f_path):
                    continue
                fname_clean = f['name'].replace(" ", "").lower()
                if display_keyword == "특수 인증" and not any(rk in fname_clean for rk in ["milk", "국산우유", "무항생제", "유기"]):
                    continue
                if display_keyword == "인증서" and any(rk in fname_clean for rk in ["milk", "국산우유", "무항생제", "유기"]):
                    continue
                if filter_folder_files and priority_keywords:
                    if not any(rk.replace(" ", "").lower() in fname_clean for rk in priority_keywords):
                        continue

                seen_fids.add(f['id'])
                f_obj = {
                    'id': f['id'], 'name': f['name'], 'kw': "", 'rtitle': "", 'reason': "",
                    'webViewLink': f.get('webViewLink', f"https://drive.google.com/file/d/{f['id']}/view"),
                    'createdTime': f.get('createdTime', ''), 'mimeType': f.get('mimeType', 'application/pdf'),
                    'folder_path': f_path, 'snippet': "", 'matched_pages': [1]
                }
                if display_keyword == "수질검사" and any(ax in f['name'] for ax in ["청소사진", "청소 사진", "사업소 서식", "사업본부서식", "간이수질", "청소 기준", "신고증"]):
                    aux_files.append(f_obj)
                else:
                    matched_files.append(f_obj)

    if display_keyword == "인허가":
        for tf in get_temp_building_files():
            if tf['id'] not in seen_fids:
                seen_fids.add(tf['id'])
                matched_files.append(tf)

    st.session_state.found_files = matched_files
    st.session_state.aux_files = sorted(aux_files, key=lambda x: parse_doc_date_tuple(x['name']), reverse=True)

def execute_deep_search(query_text):
    service = get_drive_service()
    if not service:
        return
    ensure_auto_db_loaded()

    keyword = query_text.strip()
    tokens = [t.lower() for t in re.split(r'\s+', keyword) if t]
    compact_kw = keyword.replace(" ", "").lower()
    related_terms = expand_related_title_terms(keyword)

    st.session_state.active_main_tab = MAIN_TABS[0]
    st.session_state["main_nav_radio"] = MAIN_TABS[0]
    st.session_state.update({
        "search_done": True, "search_mode": "deep",
        "search_keyword": keyword, "search_question": query_text,
        "target_folder_key": None, "gw_keyword": "", "gw_keywords_list": [],
        "priority_keywords": [], "last_file_id": "",
        "selected_doc_idx": 0, "selected_page_num": 1,
        "aux_files": [], "show_briefing": False
    })

    with st.spinner(f"🔍 사내 문서 본문 및 '{keyword}' 연관 문헌을 정밀 조회 중입니다..."):
        folder_map = get_all_managed_folders_map(service)
        managed_folder_ids = set(folder_map.keys())
        db_by_fid = {row.get("파일 ID", ""): row for row in st.session_state.auto_db if row.get("파일 ID")}
        raw_candidates = {}

        for fid, row in db_by_fid.items():
            fname = str(row.get("파일명", ""))
            rtitle = str(row.get("문서_실제제목", ""))
            kw_col = str(row.get("키워드", ""))
            reason = str(row.get("분류근거", ""))
            if is_blacklisted(fname):
                continue

            title_comp = f"{fname} {rtitle}".replace(" ", "").lower()
            meta_comp = f"{kw_col} {reason}".replace(" ", "").lower()

            direct_t = (compact_kw in title_comp) or (tokens and all(tk in title_comp for tk in tokens))
            related_t, matched_syn = False, ""
            if not direct_t:
                for rt in related_terms:
                    if rt in title_comp or (kw_col not in ("매뉴얼", "기타") and rt in meta_comp):
                        related_t, matched_syn = True, rt
                        break

            if direct_t or related_t:
                raw_candidates[fid] = {
                    'id': fid, 'name': fname or rtitle,
                    'webViewLink': row.get("뷰어 링크", f"https://drive.google.com/file/d/{fid}/view"),
                    'createdTime': row.get("발급일", ""), 'mimeType': 'application/pdf',
                    'folder_path': f"마스터 DB > {kw_col}",
                    'is_title_match': direct_t, 'is_related_title': related_t, 'matched_syn': matched_syn
                }

        for f in get_drive_supplement_files() + get_temp_building_files():
            fid = f['id']
            if is_blacklisted(f['name']):
                continue
            fn_comp = f['name'].replace(" ", "").lower()
            direct_t = (compact_kw in fn_comp) or (tokens and all(tk in fn_comp for tk in tokens))
            related_t, matched_syn = False, ""
            if not direct_t:
                for rt in related_terms:
                    if rt in fn_comp:
                        related_t, matched_syn = True, rt
                        break
            if (direct_t or related_t) and fid not in raw_candidates:
                raw_candidates[fid] = {
                    'id': fid, 'name': f['name'],
                    'webViewLink': f.get('webViewLink', f"https://drive.google.com/file/d/{fid}/view"),
                    'createdTime': f.get('createdTime', ''), 'mimeType': f.get('mimeType', 'application/pdf'),
                    'folder_path': f.get('folder_path', '문서 보관함'),
                    'is_title_match': direct_t, 'is_related_title': related_t, 'matched_syn': matched_syn
                }

        safe_kw = keyword.replace("'", "\\'")
        page_token = None
        while True:
            try:
                res = service.files().list(
                    q=f"(name contains '{safe_kw}' or fullText contains '{safe_kw}') and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                    spaces='drive',
                    fields='nextPageToken, files(id, name, webViewLink, mimeType, createdTime, parents)',
                    pageSize=1000, pageToken=page_token
                ).execute()
                for f in res.get('files', []):
                    if is_blacklisted(f['name']):
                        continue
                    parents = f.get('parents', [])
                    if not managed_folder_ids or any(p in managed_folder_ids for p in parents):
                        fid = f['id']
                        parent_label = next((folder_map[p] for p in parents if p in folder_map), "문서 보관함")
                        fn_comp = f['name'].replace(" ", "").lower()
                        t_match = (compact_kw in fn_comp) or (tokens and all(tk in fn_comp for tk in tokens))
                        if fid not in raw_candidates:
                            raw_candidates[fid] = {
                                'id': fid, 'name': f['name'],
                                'webViewLink': f.get('webViewLink', f"https://drive.google.com/file/d/{fid}/view"),
                                'createdTime': f.get('createdTime', ''), 'mimeType': f.get('mimeType', 'application/pdf'),
                                'folder_path': parent_label,
                                'is_title_match': t_match, 'is_related_title': False, 'matched_syn': ""
                            }
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
            except Exception:
                break

        verified_files = []
        for fid, f in list(raw_candidates.items())[:40]:
            is_t_match = f.get('is_title_match', False)
            is_rel_match = f.get('is_related_title', False)
            m_pages, snip_text = [], ""

            if PYMUPDF_INSTALLED and "pdf" in str(f.get('mimeType', '')).lower():
                try:
                    file_bytes = get_cached_file_bytes(fid)
                    m_pages, snip_text = analyze_pdf_matches_strict(file_bytes, keyword)
                    if not m_pages and is_rel_match and f.get('matched_syn'):
                        m_pages, snip_text = analyze_pdf_matches_strict(file_bytes, f['matched_syn'])
                except Exception:
                    pass

            if m_pages and not is_rel_match:
                f['matched_pages'] = m_pages
                f['snippet'] = snip_text
                f['match_tier'] = "direct"
                f['highlight_term'] = keyword
                f['rank_score'] = (3 if is_t_match else 2, len(m_pages), parse_doc_date_tuple(f['name']))
                verified_files.append(f)
            elif is_t_match:
                f['matched_pages'] = [1]
                f['match_tier'] = "direct"
                f['highlight_term'] = keyword
                if fid in db_by_fid:
                    r = db_by_fid[fid]
                    f['snippet'] = f"[문서명 일치] {r.get('문서_실제제목', f['name'])} | 발급일: {r.get('발급일', '-')} | 유효기한: {r.get('만료일', '-')}"
                else:
                    f['snippet'] = f"[문서명 일치] {f['name']}"
                f['rank_score'] = (3, 1, parse_doc_date_tuple(f['name']))
                verified_files.append(f)
            elif is_rel_match:
                f['matched_pages'] = m_pages if m_pages else [1]
                f['match_tier'] = "related"
                f['highlight_term'] = f.get('matched_syn') or keyword
                syn_label = f.get('matched_syn', '')
                if snip_text:
                    f['snippet'] = f"[연관 항목 '{syn_label}' 포함] {snip_text}"
                elif fid in db_by_fid:
                    r = db_by_fid[fid]
                    f['snippet'] = f"[연관 증빙 ('{syn_label}')] {r.get('문서_실제제목', f['name'])} — {r.get('분류근거', '')}"
                else:
                    f['snippet'] = f"[연관 증빙 ('{syn_label}')] {f['name']}"
                f['rank_score'] = (1, len(m_pages), parse_doc_date_tuple(f['name']))
                verified_files.append(f)

        verified_files.sort(key=lambda x: x.get('rank_score', (0, 0, (1900, 1, 1))), reverse=True)
        st.session_state.found_files = verified_files
        if verified_files:
            st.session_state.selected_doc_idx = 0
            first_pages = verified_files[0].get('matched_pages', [1])
            st.session_state.selected_page_num = first_pages[0] if first_pages else 1

def build_available_docs_catalog():
    names, seen = [], set()
    for f in get_drive_supplement_files() + get_temp_building_files():
        nm, fp = f.get('name', ''), f.get('folder_path', '')
        if not nm or nm in seen or is_blacklisted(nm):
            continue
        if any(fp.startswith(k) for k in ["선행요건", "기준서", "FSSC22000", "인증서", "인허가 서류", "가설건축물", "수질검사", "물탱크청소", "모의회수"]):
            seen.add(nm)
            names.append(f"- [{fp}] {nm}")
    return "\n".join(names[:140])

def resolve_citation_to_viewer(cit_item, question_text=""):
    doc_title = str(cit_item.get("문서명", "")).strip()
    quote_kw = str(cit_item.get("핵심구절", "")).strip()
    reason_txt = str(cit_item.get("도출사유", "")).strip()

    pool = get_drive_supplement_files() + get_temp_building_files()
    seen_ids = {p['id'] for p in pool}
    for row in st.session_state.auto_db:
        fid = row.get("파일 ID", "")
        if fid and fid not in seen_ids and not is_system_junk_file(row.get("파일명", "")):
            seen_ids.add(fid)
            pool.append({
                'id': fid, 'name': row.get("파일명") or row.get("문서_실제제목", ""),
                'webViewLink': row.get("뷰어 링크", f"https://drive.google.com/file/d/{fid}/view"),
                'mimeType': 'application/pdf', 'folder_path': row.get("키워드", "")
            })

    target_clean = re.sub(r'\.pdf$', '', doc_title, flags=re.IGNORECASE).replace(" ", "").lower()
    title_tokens = [t.lower() for t in re.split(r'[\s_(),/\-]+', re.sub(r'\.pdf$', '', doc_title, flags=re.IGNORECASE)) if len(t) >= 2]
    q_context = f"{question_text} {doc_title} {reason_txt}"
    product_hints = [p for p in ["원액두유", "가공두유", "두유", "발효유", "멸균유", "우유", "집유장", "음료", "환자"] if p in q_context]

    scored = []
    for f in pool:
        fn, fp = f.get('name', ''), f.get('folder_path', '')
        fn_comp = re.sub(r'\.pdf$', '', fn, flags=re.IGNORECASE).replace(" ", "").lower()
        full_comp = f"{fp} {fn}".replace(" ", "").lower()
        score = 0
        if target_clean and (target_clean == fn_comp or target_clean in fn_comp or fn_comp in target_clean):
            score += 50
        for tk in title_tokens:
            if tk in full_comp:
                score += 10
        for ph in product_hints:
            if ph in full_comp:
                score += 18
        if score > 0:
            scored.append((score, parse_doc_date_tuple(fn), f))

    if not scored:
        return None

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top_candidates = [x[2] for x in scored[:5]]
    search_phrases = [p for p in [quote_kw] + [t for t in re.split(r'[\s,()/·~:-]+', quote_kw) if len(t) >= 2] if p]

    for cand in top_candidates:
        if PYMUPDF_INSTALLED and "pdf" in str(cand.get('mimeType', 'pdf')).lower():
            try:
                f_bytes = get_cached_file_bytes(cand['id'])
                for sp in search_phrases[:5]:
                    m_pages, _ = analyze_pdf_matches_strict(f_bytes, sp)
                    if m_pages:
                        return {
                            'id': cand['id'], 'name': cand['name'],
                            'webViewLink': cand.get('webViewLink', f"https://drive.google.com/file/d/{cand['id']}/view"),
                            'mimeType': cand.get('mimeType', 'application/pdf'),
                            'page': m_pages[0], 'matched_pages': m_pages,
                            'highlight_kw': sp, 'reason': reason_txt
                        }
            except Exception:
                pass

    best_f = top_candidates[0]
    return {
        'id': best_f['id'], 'name': best_f['name'],
        'webViewLink': best_f.get('webViewLink', f"https://drive.google.com/file/d/{best_f['id']}/view"),
        'mimeType': best_f.get('mimeType', 'application/pdf'),
        'page': 1, 'matched_pages': [1],
        'highlight_kw': quote_kw, 'reason': reason_txt
    }

def parse_chatbot_citations(raw_text):
    citations, clean_body = [], raw_text
    m = re.search(r'<CITATIONS>\s*(\[.*?\])\s*</CITATIONS>', raw_text, re.DOTALL)
    if m:
        clean_body = raw_text[:m.start()].strip()
        try:
            citations = json.loads(m.group(1))
        except Exception:
            citations = []
    else:
        fallback_docs = []
        for pat in re.findall(r'(YS-[가-힣A-Za-z0-9_-]+|[가-힣A-Za-z0-9_]+\s*기준서|[가-힣A-Za-z0-9_]+\s*관리규정|HACCP\s*PLAN)', raw_text):
            p_c = pat.strip()
            if p_c not in fallback_docs:
                fallback_docs.append(p_c)
        for idx, fd in enumerate(fallback_docs[:4], 1):
            citations.append({"번호": idx, "문서명": fd, "도출사유": "답변 내 직접 인용된 사내 기준 및 근거 규정", "핵심구절": ""})
    return clean_body, citations

# ==========================================
# [4] 공식 용어 기반 좌측 사이드바 (표준 증빙 조회 & 통합 문서 검색)
# ==========================================
with st.sidebar:
    st.markdown("### 🔄 규정 지식베이스 동기화")
    st.caption("최신 사내 기준서 및 인증 규격을 AI 검토 엔진에 적재합니다.")

    if st.session_state.get("master_cache_name"):
        st.success("✅ 지식베이스 동기화 활성 상태")

    if st.button("최신 기준서·인증현황 메모리 적재", use_container_width=True):
        drive_service = get_drive_service()
        ensure_auto_db_loaded()
        if not drive_service:
            st.error("구글 드라이브 API 인증에 실패하였습니다.")
        elif not st.session_state.auto_db:
            st.warning("⚠️ 마스터 DB 데이터가 비어 있습니다. '마스터 DB 관리' 메뉴에서 초기 스캔을 먼저 실행해 주십시오.")
        else:
            with st.spinner("사내 핵심 기준서, 선행요건 및 인증 문서를 선별하여 메모리에 적재 중입니다..."):
                try:
                    uploaded_laws, target_pdfs, seen_fids = [], [], set()
                    for row in reversed(st.session_state.auto_db):
                        kw, fid = row.get("키워드", ""), row.get("파일 ID", "")
                        fname = row.get("문서_실제제목") or row.get("파일명", "")
                        if not fid or fid in seen_fids or is_system_junk_file(fname):
                            continue
                        if kw in ("매뉴얼", "기준서", "선행요건") or "HACCP" in kw or "FSSC" in kw or "FDA" in kw or "인증" in kw:
                            seen_fids.add(fid)
                            target_pdfs.append({"id": fid, "name": fname})

                    for sup in get_drive_supplement_files():
                        fp = sup.get("folder_path", "")
                        if any(fp.startswith(k) for k in ["선행요건", "기준서", "FSSC22000"]) and "pdf" in sup.get("mimeType", "").lower():
                            if sup['id'] not in seen_fids:
                                seen_fids.add(sup['id'])
                                target_pdfs.append({"id": sup['id'], "name": sup['name']})

                    if len(target_pdfs) > 45:
                        target_pdfs = target_pdfs[:45]
                        st.info("ℹ️ 시스템 처리 최적화를 위해 핵심 기준서 및 인증서 45건을 우선 적재합니다.")

                    if not target_pdfs:
                        st.warning("⚠️ 적재할 기준서 또는 인증 문서가 없습니다.")
                    else:
                        cache_progress = st.progress(0)
                        for i, pf in enumerate(target_pdfs):
                            try:
                                file_bytes = download_file_bytes(drive_service, pf['id'])
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                    tmp.write(file_bytes)
                                    tmp_path = tmp.name
                                up = genai.upload_file(tmp_path, display_name=pf['name'])
                                wait_time = 0
                                while up.state.name == "PROCESSING" and wait_time < 300:
                                    time.sleep(5)
                                    wait_time += 5
                                    up = genai.get_file(up.name)
                                if up.state.name == "ACTIVE":
                                    uploaded_laws.append(up)
                                os.remove(tmp_path)
                            except Exception:
                                pass
                            cache_progress.progress((i + 1) / len(target_pdfs))

                        kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False)
                        cache_contents = uploaded_laws + [f"\n\n========================================\n[식품안전 마스터 지식베이스]\n{kb_str}"]
                        law_cache = genai.caching.CachedContent.create(
                            model=MODEL_NAME,
                            display_name="audit_master_cache",
                            system_instruction="당신은 연세유업 아산공장의 식품안전 및 HACCP/FSSC22000 규정을 총괄 검증하는 전문 AI 시스템입니다. 모든 답변은 외부 심사원 및 경영진에게 보고되는 수준으로 격식 있고 정중한 비즈니스 경어체를 사용하십시오.",
                            contents=cache_contents,
                            ttl=datetime.timedelta(hours=12)
                        )
                        st.session_state["master_cache_name"] = law_cache.name
                        with open(CACHE_META_FILE, "w") as f:
                            json.dump({"name": law_cache.name, "timestamp": time.time()}, f)
                        st.success(f"✅ 핵심 기준서 및 인증 문서({len(target_pdfs)}건) 적재 완료 (12시간 유지)")
                except Exception as e:
                    st.error(f"지식베이스 적재 중 오류가 발생하였습니다: {e}")

    st.markdown("---")
    sidebar_tab1, sidebar_tab2 = st.tabs(["📋 표준 증빙 조회", "🔍 통합 문서 검색"])

    with sidebar_tab2:
        with st.form(key='search_form'):
            st.caption("문서 본문 내 검색어 및 연관 주제 문서(예: 물탱크➔저수조, 알레르기➔알러겐)를 통합 조회합니다.")
            manual_query = st.text_input("검색어 입력:", placeholder="문서명, 관리기준 또는 키워드 입력", label_visibility="collapsed")
            if st.form_submit_button("통합 정밀 검색 실행", use_container_width=True) and manual_query:
                execute_deep_search(manual_query)

    with sidebar_tab1:
        st.caption("심사 영역별 최신 공식 증빙서류 및 전자결재 기록을 즉시 호출합니다.")

        with st.expander("📁 1. 사업장 인허가 및 인증 현황", expanded=True):
            if st.button("영업 인허가 · 공장등록 · 건축물", use_container_width=True):
                execute_exact_match("인허가", "인허가 서류", "", [
                    "사업자등록", "공장등록", "건축물대장", "식품제조가공업", "축산물가공업", "집유업",
                    "수입식품영업", "식품소분업", "축산물판매업", "건강기능식품영업", "통신판매업", "방문판매업", "집단급식소", "화장품책임판매", "지하수개발허가", "가설건축물"
                ])
            if st.button("HACCP · FSSC · 해외 인증서", use_container_width=True):
                execute_exact_match("인증서", "인증서", "", [
                    "HACCP_가공두유", "HACCP_원액두유", "HACCP_유가공업", "HACCP_환자식",
                    "HACCP_과채주스", "HACCP_과채음료", "HACCP_혼합음료", "HACCP_유산균음료", "HACCP_커피", "HACCP_액상차",
                    "CHINA_HACCP", "FSSC22000", "FDA_FCE", "FDA_FFR"
                ])
            if st.button("K-MILK · 무항생제 · 유기가공 인증", use_container_width=True):
                execute_exact_match("특수 인증", "인증서", "", ["K-MILK", "무항생제", "유기가공식품"])

        with st.expander("📘 2. 식품안전 기준서 및 전사 규정", expanded=True):
            if st.button("선행요건 · 품목별 HACCP 기준서", use_container_width=True):
                execute_exact_match("기준서", ["선행요건", "기준서"], "", [])
            if st.button("FSSC 22000 품질·안전 경영규정", use_container_width=True):
                execute_exact_match("FSSC 22000 기준서", "FSSC22000", "", [])
            if st.button("개인위생 · 방충방서 · 알러겐 기준", use_container_width=True):
                execute_exact_match("위생 절차", "선행요건", "", [
                    "위생관리기준서", "장갑관리기준서", "알러겐", "작업장기준서"
                ], filter_folder_files=True)
            if st.button("이물관리 · 식품보안 · 식품사기 규정", use_container_width=True):
                execute_exact_match("보안 절차", ["선행요건", "FSSC22000"], "", [
                    "이물관리기준서", "식품보안", "식품사기", "P-210", "구매-P-300"
                ], filter_folder_files=True)
            if st.button("위기대응 · 부적합 · 제품회수 기준", use_container_width=True):
                execute_exact_match("회수 절차", ["선행요건", "FSSC22000"], "", [
                    "제품회수관리기준서", "위기관리규정", "비상사태", "부적합품관리규정", "시정조치", "고객불만"
                ], filter_folder_files=True)

        with st.expander("🧼 3. 위생·환경 검사 및 교육 이력"):
            if st.button("용수 수질검사 · 저수조 청소필증", use_container_width=True):
                execute_exact_match("수질검사", ["수질검사", "물탱크청소"], ["용수 검사 성적서"], ["수질검사", "저수조청소"])
            if st.button("방충·방서 정기 점검 및 업체증빙", use_container_width=True):
                execute_exact_match("방제 레포트", "방충방서 관련 서류", ["방역 관리 리포트"], [])
            if st.button("법정 위생교육 · HACCP 교육 · 보건증", use_container_width=True):
                execute_exact_match("보건증/교육", "교육수료증", ["위생교육"], ["보건증", "법정위생교육", "HACCP정기교육", "교육_"])
            if st.button("작업장 환경·위생 미생물 검사 (GW)", use_container_width=True):
                execute_exact_match(
                    "환경·위생 미생물 검사", "선행요건",
                    ["작업자 손 위생검사 결과", "낙하세균 검사 결과", "표면오염도 검사 결과", "압축공기 미생물검사 결과", "세척.소독제 농도 검증 결과"],
                    ["위생관리기준서", "작업장기준서"], filter_folder_files=True
                )
            if st.button("냉장·냉동 창고 온도 모니터링 (GW)", use_container_width=True):
                execute_exact_match(
                    "냉장·냉동 온도 모니터링", "선행요건",
                    ["냉장/냉동 창고 온도 모니터링 일지"],
                    ["냉장냉동설비관리기준서", "보관 및 운반"], filter_folder_files=True
                )

        with st.expander("⚙️ 4. 중요관리점(CCP) 및 설비 검교정"):
            if st.button("품목별 공정관리 및 제품검사 일보 (GW)", use_container_width=True):
                execute_exact_match(
                    "CCP 공정관리 일보", "기준서",
                    ["우유 포장 공정관리 일보", "발효유 포장 공정관리 일보", "음료류 일반검사 일보", "중국 수출 우유 제품검사 일보"],
                    ["HACCP PLAN", "제조공정설명서"], filter_folder_files=True
                )
            if st.button("무균성 시험 · 과산화수소 잔류검증 (GW)", use_container_width=True):
                execute_exact_match(
                    "무균테스트 및 과산화수소 검증", "기준서",
                    ["상업적 무균테스트 결과 보고서", "테트라팩 과산화수소 잔류여부 검증 결과", "콤비팩 과산화수소 잔류여부 검증 결과", "카톤팩 과산화수소 잔류여부 검증 결과"],
                    ["HACCP PLAN"], filter_folder_files=True
                )
            if st.button("계측기기 · 자력기기 검교정 이력 (GW)", use_container_width=True):
                execute_exact_match(
                    "계측기 및 자력기기 검·교정", "선행요건",
                    ["측정기기 공인기관 검·교정 결과", "현장 온도센서 공인기관 검·교정 결과", "유량계 공인기관 교정 결과", "자체 측정기기 검·교정결과", "자력기기 점검 결과"],
                    ["검사관리기준서", "제조시설관리기준서"], filter_folder_files=True
                )
            if st.button("제조설비 유지보수 및 관리 이력", use_container_width=True):
                execute_exact_match(
                    "설비이력", ["설비이력", "선행요건", "FSSC22000"], "",
                    ["설비", "제조시설관리기준서", "생산설비관리규정", "부대시설관리규정"]
                )

        with st.expander("📦 5. 원부자재 검사 및 사후 추적관리"):
            if st.button("원·부자재 입고 검수 기록 (GW)", use_container_width=True):
                execute_exact_match(
                    "원부자재 입고 검수", ["선행요건", "FSSC22000"],
                    ["부자재 입고 검수서"],
                    ["검사관리기준서", "협력업체관리규정", "구매업무규정"], filter_folder_files=True
                )
            if st.button("자가품질검사 · 알러겐 검증 기록 (GW)", use_container_width=True):
                execute_exact_match(
                    "자가품질 및 알러겐·미생물 검증", "선행요건",
                    ["자가품질검사 검사결과", "알러겐 및 미생물 검증 결과", "병원성 미생물 배지 수불부", "음료류 일반검사 일보"],
                    ["검사관리기준서", "알러겐 관리기준서"], filter_folder_files=True
                )
            if st.button("고객불만 · 부적합 및 시정조치 (GW)", use_container_width=True):
                execute_exact_match(
                    "클레임 및 부적합 시정조치", "FSSC22000",
                    ["소비자 클레임 현황(제조단계, 공장)", "대리점 클레임 현황", "품질(제품, 원·부자재) 부적합 현황 보고", "문제점 개선 대책 결과 보고"],
                    ["고객불만처리규정", "부적합품관리규정", "시정조치"], filter_folder_files=True
                )
            if st.button("모의회수 · 추적성 훈련 결과", use_container_width=True):
                execute_exact_match("모의회수", ["모의회수", "선행요건"], ["모의회수"], ["모의회수", "추적성", "제품회수관리기준서"])
            if st.button("생산물배상책임보험(PL) 증권", use_container_width=True):
                execute_exact_match("책임보험", "PL보험가입증명서", "", ["책임보험"])
# ==========================================
# [5] 전체높이 분할 라우터 및 메인 5개 공식 메뉴 화면 구성
# ==========================================
def _sync_nav_tab():
    st.session_state.active_main_tab = st.session_state.main_nav_radio

def render_header_and_nav():
    st.markdown("<h2 style='margin-top:0; padding-top:0; margin-bottom:0.35rem;'>🛡️ 식품안전 · HACCP 통합 증빙 시스템</h2>", unsafe_allow_html=True)
    st.markdown("<div class='top-nav-marker'></div>", unsafe_allow_html=True)
    if "main_nav_radio" not in st.session_state:
        st.session_state.main_nav_radio = st.session_state.active_main_tab
    st.radio(
        "상단 주 메뉴",
        MAIN_TABS,
        horizontal=True,
        label_visibility="collapsed",
        key="main_nav_radio",
        on_change=_sync_nav_tab
    )

current_tab = st.session_state.active_main_tab

# ----------------- MENU 1: 📄 심사 증빙 열람 -----------------
if current_tab == MAIN_TABS[0]:
    keyword = st.session_state.search_keyword
    raw_files = [f for f in st.session_state.found_files if not is_blacklisted(f['name'], keyword)] if st.session_state.search_done else []
    gw_items = st.session_state.get("gw_keywords_list", [])
    if not gw_items and st.session_state.get("gw_keyword"):
        gw_items = [st.session_state.gw_keyword]

    if st.session_state.search_done and raw_files:
        left_panel, right_viewer = st.columns([0.95, 1.45], gap="large")
        top_file, active_hl_kw = None, ""

        with left_panel:
            render_header_and_nav()

            if gw_items:
                st.info("💻 **전자결재(그룹웨어) 승인 기록 조회**")
                gw_cols = st.columns(min(len(gw_items), 2))
                for g_idx, g_kw in enumerate(gw_items):
                    g_url = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?keyword={urllib.parse.quote(g_kw)}"
                    with gw_cols[g_idx % len(gw_cols)]:
                        st.link_button(f"📄 [{g_kw}] 조회", g_url, type="primary", use_container_width=True)
                st.markdown("---")

            if st.session_state.search_mode == "deep":
                direct_cnt = sum(1 for x in raw_files if x.get('match_tier') == 'direct')
                rel_cnt = len(raw_files) - direct_cnt
                st.markdown(
                    f"<div class='mfds-banner'>검색어 <span style='color:#1d4ed8;'>‘{keyword}’</span> 조회 결과 총 <span style='color:#1d4ed8;'>{len(raw_files)}건</span> "
                    f"<span style='font-size:0.86rem; color:#475569;'>(본문·제목 일치 {direct_cnt}건 / 연관 문헌 {rel_cnt}건)</span></div>",
                    unsafe_allow_html=True
                )

                with st.expander(f"📋 검색 문헌 목록 (총 {len(raw_files)}건) — 선택 시 우측 원문 전환", expanded=True):
                    for idx, f in enumerate(raw_files):
                        c_info, c_btn = st.columns([7.3, 2.7])
                        folder_label = f.get('folder_path', '문서 보관함')
                        m_pages = f.get('matched_pages', [1])
                        first_p = m_pages[0] if m_pages else 1
                        snip_raw = f.get('snippet') or f"문서명: {f['name']}"
                        badge_html = "<span class='badge-direct'>직접일치</span>" if f.get('match_tier') == 'direct' else "<span class='badge-related'>연관문헌</span>"

                        snip_html = snip_raw
                        for tk in [t for t in re.split(r'\s+', keyword) if len(t) >= 1]:
                            snip_html = re.sub(f"({re.escape(tk)})", r"<span class='mfds-key'>\1</span>", snip_html, flags=re.IGNORECASE)

                        with c_info:
                            st.markdown(
                                f"<div class='mfds-result-item'>"
                                f"<div class='mfds-title'>{badge_html}{idx + 1}. {f['name']} <span class='mfds-path'>[{folder_label}] (p.{', p.'.join(map(str, m_pages[:4]))})</span></div>"
                                f"<div class='mfds-snippet'>{snip_html}</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        with c_btn:
                            st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
                            is_curr = (idx == min(st.session_state.selected_doc_idx, len(raw_files) - 1))
                            btn_lbl = f"✅ 열람 중 (p.{first_p})" if is_curr else f"📄 원문 열람 (p.{first_p})"
                            if st.button(btn_lbl, key=f"deep_sel_{idx}", type=("primary" if is_curr else "secondary"), use_container_width=True):
                                st.session_state.selected_doc_idx = idx
                                st.session_state.selected_page_num = first_p
                                st.session_state.show_briefing = False
                                st.rerun()

                sel_idx = min(st.session_state.selected_doc_idx, len(raw_files) - 1)
                top_file = raw_files[sel_idx]
                active_hl_kw = top_file.get('highlight_term', keyword)

            else:
                subtab_map = get_subtabs_for_category(keyword, raw_files)
                non_empty_tabs = {k: v for k, v in subtab_map.items() if v} or subtab_map
                tab_labels = list(non_empty_tabs.keys())

                if len(tab_labels) > 1:
                    st.markdown("**📂 세부 문서 분류**")
                    chosen_subtab = st.radio(
                        "세부 문서 분류",
                        tab_labels,
                        horizontal=True,
                        label_visibility="collapsed",
                        key=f"subtab_radio_{keyword}"
                    )
                else:
                    chosen_subtab = tab_labels[0]

                active_list = non_empty_tabs.get(chosen_subtab, [])
                if active_list:
                    opts = {f"{i + 1}. {f['name']}": f for i, f in enumerate(active_list)}
                    if len(active_list) > 1:
                        sel_name = st.selectbox(
                            f"✅ [{chosen_subtab}] 열람 대상 문서 선택 ({len(active_list)}종)",
                            list(opts.keys()),
                            key=f"doc_select_{keyword}_{chosen_subtab}"
                        )
                    else:
                        sel_name = list(opts.keys())[0]
                        st.success(f"✅ **[{chosen_subtab}] 최신 공식 증빙:** `{opts[sel_name]['name']}`")
                    top_file = opts[sel_name]

                    if st.session_state.last_file_id != top_file['id']:
                        st.session_state.last_file_id = top_file['id']
                        st.session_state.selected_page_num = 1
                        st.session_state.show_briefing = False

                if st.session_state.aux_files:
                    with st.expander(f"📎 부속 증빙 및 참고 자료 ({len(st.session_state.aux_files)}건)", expanded=False):
                        aux_df = [{"연번": i + 1, "문서명": af['name'], "열람": af['webViewLink']} for i, af in enumerate(st.session_state.aux_files)]
                        st.dataframe(aux_df, hide_index=True, use_container_width=True, column_config={"열람": st.column_config.LinkColumn(display_text="별도 창 열람")})

            if top_file is not None:
                st.markdown("---")
                b_col1, b_col2 = st.columns([7.2, 2.8])
                with b_col1:
                    if st.button("📋 AI 문서 검토 요약 보기", type="primary", use_container_width=True, key=f"btn_brief_{top_file['id']}"):
                        st.session_state.show_briefing = True
                with b_col2:
                    if st.session_state.show_briefing:
                        if st.button("요약 닫기", use_container_width=True, key=f"hide_brief_{top_file['id']}"):
                            st.session_state.show_briefing = False
                            st.rerun()

                if st.session_state.show_briefing:
                    with st.spinner("📋 문서 적합성 및 관련 법규·기준 연계 내역을 작성 중입니다..."):
                        brief_txt = generate_on_demand_briefing(top_file)
                    if "오류" in brief_txt:
                        st.error(brief_txt)
                    else:
                        st.success(brief_txt)

        with right_viewer:
            if top_file is not None:
                render_full_height_doc_viewer(top_file, highlight_kw=active_hl_kw, viewer_context="tab1")

    else:
        render_header_and_nav()
        if st.session_state.search_done:
            if gw_items:
                st.info("💻 **전자결재(그룹웨어) 승인 기록 조회**")
                gw_cols = st.columns(min(len(gw_items), 3))
                for g_idx, g_kw in enumerate(gw_items):
                    g_url = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?keyword={urllib.parse.quote(g_kw)}"
                    with gw_cols[g_idx % len(gw_cols)]:
                        st.link_button(f"📄 [{g_kw}] 결재문서함 열람", g_url, type="primary", use_container_width=True)
            else:
                st.warning(f"⚠️ 요청하신 항목('{keyword}')에 해당하는 등록 문서가 없습니다. 좌측 메뉴에서 다른 분류를 선택하거나 검색어를 변경해 주십시오.")
        else:
            st.info("👈 좌측 **[표준 증빙 조회]** 메뉴에서 심사 항목을 선택하거나 **[통합 문서 검색]**에 키워드를 입력하시면, 우측 전체 화면에 고해상도 원문이 즉시 표시됩니다.")

# ----------------- MENU 2: 🗂️ 문서 보관함 · 등록 (폴더 직접 탐색 + 하위폴더 생성 + 즉시 업로드·DB반영 + 선택 시에만 우측 뷰어 오픈) -----------------
elif current_tab == MAIN_TABS[1]:
    all_archive_cats = [
        ("인허가 서류", "🏢 인허가 서류"),
        ("가설건축물", "🏗️ 가설건축물"),
        ("인증서", "🥇 국내외 인증서"),
        ("기준서", "📘 HACCP 기준서"),
        ("선행요건", "📋 선행요건 기준서"),
        ("FSSC22000", "🌐 FSSC 22000 규정"),
        ("수질검사", "💧 수질검사 성적서"),
        ("물탱크청소", "🧼 저수조 청소필증"),
        ("교육수료증", "🎓 법정 교육·보건증"),
        ("방충방서 관련 서류", "🦟 방충·방서 증빙"),
        ("모의회수", "🔄 모의회수 훈련"),
        ("PL보험가입증명서", "🛡️ PL 배상책임보험"),
        ("설비이력", "🔧 설비 유지보수"),
        ("생산실적보고", "📊 생산실적 보고"),
        ("환경관리팀_폐기물계약서", "♻️ 폐기물 계약·실적")
    ]

    def render_archive_explorer_body():
        st.markdown("#### 🗂️ 분류별 문서 보관함 탐색 및 신규 증빙 등록")
        st.caption("구글 드라이브 폴더 구조와 동일하게 각 폴더별 보관 문서를 직접 확인하여 최신 서류를 등록·동기화하며, 열람이 필요한 문서를 클릭하면 우측 화면에 원문이 표시됩니다.")

        # 1단계: 15개 대분류 보관함 그리드
        st.markdown("**1️⃣ 대분류 보관함 선택**")
        grid_cols = st.columns(5 if st.session_state.explorer_active_doc is None else 3)
        col_mod = len(grid_cols)
        for idx, (cat_key, cat_label) in enumerate(all_archive_cats):
            is_sel = (st.session_state.explorer_selected_cat == cat_key)
            with grid_cols[idx % col_mod]:
                if st.button(
                    cat_label,
                    key=f"arch_cat_{cat_key}",
                    type=("primary" if is_sel else "secondary"),
                    use_container_width=True
                ):
                    st.session_state.explorer_selected_cat = cat_key
                    st.session_state.explorer_selected_folder_id = ""
                    st.session_state.explorer_active_doc = None
                    st.session_state.explorer_page_num = 1
                    st.rerun()

        cur_cat = st.session_state.explorer_selected_cat
        subfolders = get_subfolders_for_category(cur_cat)
        cat_all_files = sorted(
            get_cached_folder_files(cur_cat),
            key=lambda x: parse_doc_date_tuple(x.get('name', ''), x.get('createdTime', '')),
            reverse=True
        )

        if not subfolders:
            st.warning(f"⚠️ '{cur_cat}' 보관함의 클라우드 폴더 경로를 확인할 수 없습니다.")
            return

        # 폴더별 직접 보유 파일 수 집계 (구글 드라이브 실제 폴더처럼 각 폴더 내부 파일 수 표시)
        direct_counts = {}
        for f in cat_all_files:
            for p_id in f.get("parents", []):
                direct_counts[p_id] = direct_counts.get(p_id, 0) + 1

        folder_choices = []
        for sf in subfolders:
            cnt = direct_counts.get(sf["id"], 0)
            folder_choices.append({
                "id": sf["id"],
                "path": sf["path"],
                "name": sf["name"],
                "display": f"{sf['label']}  ({cnt}건)"
            })
        folder_choices.append({
            "id": "ALL",
            "path": f"{cur_cat} (하위 폴더 포함 전체)",
            "name": cur_cat,
            "display": f"🔎 [{cur_cat}] 하위 폴더 포함 전체 통합 보기 ({len(cat_all_files)}건)"
        })

        # 기본 선택 폴더 인덱스 결정 (하위 폴더 생성 직후 해당 폴더로 자동 포커싱)
        default_f_idx = 0
        if st.session_state.explorer_selected_folder_id:
            for f_i, fc in enumerate(folder_choices):
                if fc["id"] == st.session_state.explorer_selected_folder_id:
                    default_f_idx = f_i
                    break
        else:
            # 최상위 폴더가 비어 있고 하위 폴더에만 파일이 있는 경우 가장 마지막 연도/하위 폴더를 기본 선택
            if direct_counts.get(subfolders[0]["id"], 0) == 0 and len(subfolders) > 1:
                default_f_idx = len(subfolders) - 1

        st.markdown("---")
        nav_c1, nav_c2 = st.columns([6.2, 3.8])
        with nav_c1:
            chosen_disp = st.selectbox(
                "2️⃣ 세부 폴더 위치 선택 (선택한 폴더 내부의 실제 보관 파일 목록이 아래에 표시됩니다)",
                [fc["display"] for fc in folder_choices],
                index=default_f_idx,
                key=f"folder_nav_{cur_cat}_{st.session_state.explorer_selected_folder_id}"
            )
            chosen_folder = next(fc for fc in folder_choices if fc["display"] == chosen_disp)
            if chosen_folder["id"] != st.session_state.explorer_selected_folder_id and chosen_folder["id"] != "ALL":
                st.session_state.explorer_selected_folder_id = chosen_folder["id"]
        with nav_c2:
            name_filter = st.text_input("🔍 현재 목록 내 문서명 검색", placeholder="파일명 또는 연도 입력...", key=f"flt_{cur_cat}")

        # 현재 선택한 폴더의 하위 직속 폴더 바로가기 버튼 표시 (구글 드라이브 폴더 탐색 방식)
        if chosen_folder["id"] != "ALL":
            cur_path_prefix = chosen_folder["path"] + " > "
            child_subfolders = [
                sf for sf in subfolders
                if sf["path"].startswith(cur_path_prefix) and " > " not in sf["path"][len(cur_path_prefix):]
            ]
            if child_subfolders:
                st.caption(f"📁 **`{chosen_folder['path']}` 내부 하위 폴더 바로가기:**")
                ch_cols = st.columns(min(len(child_subfolders), 4))
                for c_idx, ch_sf in enumerate(child_subfolders):
                    ch_cnt = direct_counts.get(ch_sf["id"], 0)
                    with ch_cols[c_idx % len(ch_cols)]:
                        if st.button(f"📁 {ch_sf['name']} ({ch_cnt})", key=f"jump_sf_{ch_sf['id']}", use_container_width=True):
                            st.session_state.explorer_selected_folder_id = ch_sf["id"]
                            st.rerun()

        # 선택한 폴더 내 실제 파일 필터링
        if chosen_folder["id"] == "ALL":
            folder_files = cat_all_files
        else:
            folder_files = [f for f in cat_all_files if chosen_folder["id"] in f.get("parents", [])]

        if name_filter.strip():
            nf_low = name_filter.strip().lower()
            folder_files = [f for f in folder_files if nf_low in f.get("name", "").lower()]

        # 3단계: 현재 폴더 내 파일 목록 및 온디맨드 원문 열람 버튼
        st.markdown(f"**3️⃣ 현재 위치 (`{chosen_folder['path']}`) 보관 문서 목록 — 총 `{len(folder_files)}건`**")
        if not folder_files:
            st.info("📂 현재 선택하신 폴더에는 보관된 문서가 없습니다. 아래에서 새 하위 폴더를 만들거나 신규 파일을 바로 업로드할 수 있습니다.")
        else:
            latest_dt = parse_doc_date_tuple(folder_files[0].get("name", ""), folder_files[0].get("createdTime", ""))
            if latest_dt[0] > 1900:
                st.caption(f"🕒 이 폴더의 가장 최근 문서 기준일: **{format_iso_from_tuple(latest_dt)}** (`{folder_files[0]['name']}`)")

            with st.container(height=360, border=True):
                for idx, f in enumerate(folder_files, 1):
                    dt_str = format_iso_from_tuple(parse_doc_date_tuple(f.get("name", ""), f.get("createdTime", "")))
                    upl_str = f.get("createdTime", "")[:10] if f.get("createdTime") else "-"
                    is_viewing = (st.session_state.explorer_active_doc is not None and st.session_state.explorer_active_doc.get("id") == f["id"])

                    r1, r2, r3 = st.columns([6.4, 2.0, 1.6])
                    with r1:
                        path_note = f" · `{f.get('folder_path', '')}`" if chosen_folder["id"] == "ALL" else ""
                        st.markdown(
                            f"**{idx}. {f['name']}**  \n"
                            f"<span style='font-size:0.83rem; color:#64748b;'>문서기준일: {dt_str} | 드라이브 등록일: {upl_str}{path_note}</span>",
                            unsafe_allow_html=True
                        )
                    with r2:
                        btn_txt = "✅ 우측 열람 중" if is_viewing else "📄 원문 열람"
                        if st.button(btn_txt, key=f"open_exp_{f['id']}", type=("primary" if is_viewing else "secondary"), use_container_width=True):
                            st.session_state.explorer_active_doc = f
                            st.session_state.explorer_page_num = 1
                            st.rerun()
                    with r3:
                        st.link_button("별도 창", f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view"), use_container_width=True)

        # 4단계: 현재 폴더 기준 하위 폴더 생성 & 신규 증빙 업로드 및 자동 DB 동기화
        st.markdown("---")
        target_upload_folder = subfolders[0] if chosen_folder["id"] == "ALL" else next((sf for sf in subfolders if sf["id"] == chosen_folder["id"]), subfolders[0])

        act_col1, act_col2 = st.columns([4.2, 5.8], gap="medium")
        with act_col1:
            with st.expander("➕ 현재 위치에 새 하위 폴더 생성", expanded=False):
                st.caption(f"상위 위치: `{target_upload_folder['path']}`")
                new_sf_name = st.text_input("신규 하위 폴더명 입력", placeholder="예: 27년도, 2027년 상반기", key=f"new_sf_{cur_cat}")
                if st.button("📁 하위 폴더 생성 실행", use_container_width=True, key=f"btn_mk_sf_{cur_cat}"):
                    ok_sf, res_sf = create_drive_subfolder(target_upload_folder["id"], new_sf_name)
                    if ok_sf:
                        st.session_state.explorer_selected_folder_id = res_sf
                        st.success(f"✅ '{new_sf_name}' 폴더가 생성되어 해당 폴더로 이동합니다.")
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.error(f"🚨 {res_sf}")

        with act_col2:
            with st.expander(f"📤 현재 폴더 (`{target_upload_folder['path']}`)에 신규 서류 업로드 · 자동 DB 반영", expanded=True):
                up_file_obj = st.file_uploader(
                    "등록할 파일 선택 (PDF, PNG, JPG — 업로드 즉시 해당 구글 드라이브 폴더 저장 및 마스터 시트 자동 반영)",
                    type=["pdf", "png", "jpg", "jpeg"],
                    key=f"uploader_{cur_cat}_{target_upload_folder['id']}"
                )
                if up_file_obj is not None:
                    if st.button("🚀 현재 폴더에 업로드 및 마스터 DB 즉시 동기화", type="primary", use_container_width=True, key=f"btn_up_{cur_cat}"):
                        with st.spinner(f"'{up_file_obj.name}' 파일을 `{target_upload_folder['path']}` 폴더에 업로드하고 AI 판독 후 시트에 저장 중입니다..."):
                            ok, doc_or_err, meta_info = upload_and_scan_single_file(up_file_obj, target_upload_folder["id"])
                        if ok:
                            doc_or_err["folder_path"] = target_upload_folder["path"]
                            st.session_state.explorer_active_doc = doc_or_err
                            st.session_state.explorer_page_num = 1
                            st.success(
                                f"✅ 업로드 및 DB 동기화 완료: **{up_file_obj.name}**\n\n"
                                f"• 저장 위치: `{target_upload_folder['path']}` | 분류코드: `{meta_info.get('키워드', '-')}` | 만료기한: `{meta_info.get('만료일', '-')}`"
                            )
                            time.sleep(1.0)
                            st.rerun()
                        else:
                            st.error(f"🚨 업로드 실패: {doc_or_err}")

    # 문서를 직접 클릭하기 전에는 전체 폭 탐색기만 표시(로딩 지연 0초), 클릭 시에만 우측 원문 뷰어 분할 오픈
    if st.session_state.explorer_active_doc is not None:
        exp_left, exp_right = st.columns([1.0, 1.4], gap="large")
        with exp_left:
            render_header_and_nav()
            render_archive_explorer_body()
        with exp_right:
            render_full_height_doc_viewer(st.session_state.explorer_active_doc, highlight_kw="", viewer_context="explorer")
    else:
        render_header_and_nav()
        render_archive_explorer_body()

# ----------------- MENU 3: 📊 법정 기한 현황 -----------------
elif current_tab == MAIN_TABS[2]:
    render_header_and_nav()
    st.markdown("### 📊 법정 의무 서류 · 인증 · 정기검사 유효기한 현황")
    st.caption("상단의 관리 상태별 집계 버튼을 선택하면 해당 대상 목록이 하단에 즉시 표시되며, 우측 '원문 열람'을 통해 증빙 원본을 확인할 수 있습니다.")

    ensure_auto_db_loaded()
    supplement_drive_files = get_drive_supplement_files()
    temp_bldg_files = get_temp_building_files()
    today = datetime.date.today()

    def register_dash_candidate(dash_map, norm_kw, entry_dict, score_tuple):
        if norm_kw not in dash_map or score_tuple > dash_map[norm_kw]["score"]:
            dash_map[norm_kw] = {"entry": entry_dict, "score": score_tuple}

    latest_dash_dict = {}

    for row in st.session_state.auto_db:
        kw = str(row.get("키워드", "")).strip()
        fname = str(row.get("파일명", "")).strip()
        rtitle = str(row.get("문서_실제제목", "")).strip()
        reason = str(row.get("분류근거", "")).strip()
        if not kw or kw in ("PASS", "기타", "매뉴얼", "일반수료증") or is_system_junk_file(fname) or is_pest_vendor_doc(row):
            continue

        if kw in ("수질검사_반기", "수질검사_음용수"):
            comb_w = f"{fname} {rtitle} {reason}"
            kw = "수질검사_먹는물" if any(w in comb_w for w in ["먹는물", "상수도", "수돗물"]) else "수질검사_지하수"
        elif kw == "수질검사_노로바이러스":
            kw = "수질검사_노로"
        elif kw in ("수질검사_간이", "수질검사_저수조"):
            continue

        if kw.startswith("교육_") or kw.startswith("법정위생교육") or kw.startswith("HACCP정기교육") or kw.startswith("HACCP교육"):
            norm_edu_kw, disp_edu, edu_cyc = normalize_education_key(fname, rtitle, reason)
            if not norm_edu_kw:
                continue
            kw = norm_edu_kw
            row = dict(row)
            row["_disp_title"] = disp_edu
            row["주기(개월)"] = str(edu_cyc)

        score_t = parse_doc_date_tuple(fname, row.get("발급일", ""))
        register_dash_candidate(latest_dash_dict, kw, row, score_t)

    for f in supplement_drive_files:
        fn, fp = f.get("name", ""), f.get("folder_path", "")
        if is_pest_vendor_doc(fn, fp) or is_blacklisted(fn):
            continue
        dt_t = parse_doc_date_tuple(fn, f.get("createdTime", ""))
        iso_issue = format_iso_from_tuple(dt_t)
        inferred_kw, inferred_exp, inferred_disp, inferred_cyc = None, "", "", "12"

        if "인허가" in fp and "사업자등록" in fn and "연세유업" in fn:
            inferred_kw, inferred_exp, inferred_cyc = "사업자등록", "영구", "0"
        elif "인증서" in fp and ("CHINA" in fn.upper() or "延世" in fn or "主证" in fn):
            inferred_kw = "CHINA_HACCP"
            m_exp = re.search(r'20[12]\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\s*[~\-]\s*(20[23]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', fn)
            inferred_exp = f"{m_exp.group(1)}-{m_exp.group(2)}-{m_exp.group(3)}" if m_exp else ""
        elif "모의회수" in fp or "모의회수" in fn:
            inferred_kw = "모의회수"
        elif ("물탱크청소" in fp or "저수조" in fn) and any(x in fn for x in ["필증", "Report", "결과"]):
            if not any(ax in fn for ax in ["사진", "서식", "간이", "기준"]):
                inferred_kw, inferred_cyc = "저수조청소", "6"
        elif "수질검사" in fp and not any(ax in fn for ax in ["사진", "서식", "간이", "기준"]):
            if "노로" in fn:
                inferred_kw = "수질검사_노로"
            elif any(w in f"{fn} {fp}" for w in ["먹는물", "상수도", "수돗물"]):
                inferred_kw = "수질검사_먹는물"
            elif "성적서" in fn:
                inferred_kw, inferred_cyc = "수질검사_지하수", "6"
        elif "교육수료증" in fp:
            norm_k, disp_l, cyc_m = normalize_education_key(fn)
            if norm_k:
                inferred_kw, inferred_disp, inferred_cyc = norm_k, disp_l, str(cyc_m)

        if inferred_kw:
            sup_entry = {
                "키워드": inferred_kw, "파일명": fn, "문서_실제제목": inferred_disp or fn,
                "발급일": iso_issue, "만료일": inferred_exp, "주기(개월)": inferred_cyc,
                "개정번호": "-", "파일 ID": f["id"],
                "뷰어 링크": f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view"),
                "_disp_title": inferred_disp
            }
            register_dash_candidate(latest_dash_dict, inferred_kw, sup_entry, dt_t)

    for tf in temp_bldg_files:
        fn = tf['name']
        m_dong = re.search(r'\(([^)]*동)\)', fn)
        dong_key = f"가설건축물_{m_dong.group(1)}" if m_dong else f"가설건축물_{fn[:12]}"
        m_exp8 = re.search(r'(20[23]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', fn.replace(" ", ""))
        exp_val = f"{m_exp8.group(1)}-{m_exp8.group(2)}-{m_exp8.group(3)}" if m_exp8 else "영구"
        cyc_val = "36" if m_exp8 else "0"
        tb_entry = {
            "키워드": dong_key, "파일명": fn,
            "문서_실제제목": f"가설건축물 축조·존치기간 증빙 ({m_dong.group(1) if m_dong else '전체'})",
            "발급일": "-", "만료일": exp_val, "주기(개월)": cyc_val,
            "개정번호": "-", "파일 ID": tf['id'], "뷰어 링크": tf['webViewLink'],
            "_disp_title": f"가설건축물 축조·연장 증빙 ({m_dong.group(1) if m_dong else '총괄'})"
        }
        register_dash_candidate(latest_dash_dict, dong_key, tb_entry, parse_doc_date_tuple(fn))

    db_dict = {kw: v["entry"] for kw, v in latest_dash_dict.items()}

    def compute_expiry_and_status(doc, cycle_months, is_edu=False):
        issue_raw = str(doc.get("발급일", "")).strip()
        exp_raw = str(doc.get("만료일", "")).strip()
        dt_tuple = parse_doc_date_tuple(doc.get("파일명", ""), issue_raw)
        issue_clean = issue_raw if re.match(r'^\d{4}-\d{2}-\d{2}$', issue_raw) else (issue_raw if issue_raw == "-" else format_iso_from_tuple(dt_tuple))

        if int(cycle_months) == 0 or exp_raw == "영구":
            return issue_clean, "영구", "-", "✅ 영구보존 (갱신불필요)", 99999

        expire_date = None
        if exp_raw and exp_raw not in ("미상", "일자 미기재", "없음", "해당없음", "-"):
            try:
                expire_date = pd.to_datetime(exp_raw).date()
            except Exception:
                expire_date = None

        if is_edu and dt_tuple[0] > 1900:
            yr_end_exp = datetime.date(dt_tuple[0] + 1, 12, 31)
            if expire_date is None or yr_end_exp > expire_date:
                expire_date = yr_end_exp
        elif expire_date is None and dt_tuple[0] > 1900 and int(cycle_months) > 0:
            base_dt = datetime.date(dt_tuple[0], dt_tuple[1], dt_tuple[2])
            expire_date = (pd.Timestamp(base_dt) + pd.DateOffset(months=int(cycle_months)) - pd.Timedelta(days=1)).date()

        if expire_date is None:
            return issue_clean, "확인 필요", "-", "⚠️ 일자 확인 필요", 0

        d_day = (expire_date - today).days
        exp_fmt = expire_date.strftime("%Y-%m-%d")
        if d_day < 0:
            status_txt = "🚨 기한 경과 (갱신 요망)"
        elif d_day <= 30:
            status_txt = "⚠️ 만료 임박 (30일 이내)"
        else:
            status_txt = "🟢 적격 (유효)"
        return issue_clean, exp_fmt, str(d_day), status_txt, d_day

    dashboard_data, processed_keys = [], set()

    for key, meta in MASTER_DOC_REQUIREMENTS.items():
        processed_keys.add(key)
        cyc = int(meta["주기"])
        gw_form = meta.get("gw", "")

        if gw_form and key not in db_dict:
            gw_link = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?keyword={urllib.parse.quote(gw_form)}"
            dashboard_data.append({
                "분류코드": key, "법정 관리 항목명": meta["표시명"], "법정주기(개월)": cyc,
                "등록 문서명": f"[그룹웨어 전자결재] {gw_form}", "발급·시행일": "상시결재", "유효만료일": "월간점검",
                "잔여일(D-Day)": "-", "관리상태": "🟢 적격 (그룹웨어 관리)", "원문 열람": gw_link, "_d_num": 99999
            })
            continue

        if key in db_dict:
            doc = db_dict[key]
            iss_c, exp_c, d_str, st_txt, d_num = compute_expiry_and_status(doc, cyc, is_edu=False)
            dashboard_data.append({
                "분류코드": key, "법정 관리 항목명": meta["표시명"], "법정주기(개월)": cyc,
                "등록 문서명": doc.get("파일명") or doc.get("문서_실제제목", ""),
                "발급·시행일": iss_c, "유효만료일": exp_c, "잔여일(D-Day)": d_str, "관리상태": st_txt,
                "원문 열람": doc.get("뷰어 링크", ""), "_d_num": d_num
            })
        else:
            dashboard_data.append({
                "분류코드": key, "법정 관리 항목명": meta["표시명"], "법정주기(개월)": cyc,
                "등록 문서명": "-", "발급·시행일": "-", "유효만료일": "-", "잔여일(D-Day)": "-",
                "관리상태": "🚨 미비 (문서 미등록)", "원문 열람": "", "_d_num": -99999
            })

    allowed_dyn = ("가설건축물_", "보건증_", "법정위생교육_", "HACCP정기교육", "HACCP팀장및경영자교육")
    for key, doc in sorted(db_dict.items()):
        if key not in processed_keys and key.startswith(allowed_dyn):
            is_edu_item = key.startswith("법정위생교육_") or key == "HACCP정기교육"
            cyc = 0 if key == "HACCP팀장및경영자교육" else int(doc.get("주기(개월)", 12) or 0)
            if key.startswith("가설건축물_") and str(doc.get("만료일", "")) not in ("", "영구", "미상"):
                cyc = 36
            iss_c, exp_c, d_str, st_txt, d_num = compute_expiry_and_status(doc, cyc, is_edu=is_edu_item)
            disp_label = doc.get("_disp_title") or f"{doc.get('문서_실제제목', key)}"
            dashboard_data.append({
                "분류코드": key, "법정 관리 항목명": disp_label, "법정주기(개월)": cyc,
                "등록 문서명": doc.get("파일명", ""), "발급·시행일": iss_c, "유효만료일": exp_c,
                "잔여일(D-Day)": d_str, "관리상태": st_txt, "원문 열람": doc.get("뷰어 링크", ""), "_d_num": d_num
            })

    df_dashboard = pd.DataFrame(dashboard_data)

    if not df_dashboard.empty:
        mask_exp = df_dashboard["관리상태"].str.contains("경과|미비|확인 필요", na=False)
        mask_30 = (df_dashboard["_d_num"] >= 0) & (df_dashboard["_d_num"] <= 30)
        mask_90 = (df_dashboard["_d_num"] >= 0) & (df_dashboard["_d_num"] <= 90)
        mask_180 = (df_dashboard["_d_num"] >= 0) & (df_dashboard["_d_num"] <= 180)
        mask_ok = df_dashboard["관리상태"].str.contains("적격|영구", na=False)

        b_cols = st.columns(6)
        if b_cols[0].button(f"📋 전체 관리 대상\n({len(df_dashboard)}건)", use_container_width=True):
            st.session_state.dash_status_filter = "전체"
        if b_cols[1].button(f"🚨 기한경과 · 미비\n({int(mask_exp.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "기한경과_미등록"
        if b_cols[2].button(f"⚠️ 30일 이내 만료\n({int(mask_30.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "30일"
        if b_cols[3].button(f"📅 90일 이내 도래\n({int(mask_90.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "90일"
        if b_cols[4].button(f"🗓️ 180일 이내 도래\n({int(mask_180.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "180일"
        if b_cols[5].button(f"✅ 적격 · 영구보존\n({int(mask_ok.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "정상_영구"

        def style_status(val):
            if "미비" in str(val): return 'color: white; background-color: #0f172a; font-weight:bold'
            if "경과" in str(val): return 'color: white; background-color: #ef4444; font-weight:bold'
            if "임박" in str(val) or "확인" in str(val): return 'color: black; background-color: #fbbf24; font-weight:bold'
            if "적격" in str(val): return 'color: white; background-color: #22c55e'
            if "영구" in str(val): return 'color: white; background-color: #3b82f6'
            return ''

        disp_cols = ["분류코드", "법정 관리 항목명", "법정주기(개월)", "등록 문서명", "발급·시행일", "유효만료일", "잔여일(D-Day)", "관리상태", "원문 열람"]
        cur_f = st.session_state.dash_status_filter
        filter_map = {
            "전체": ("📋 전체 법정 의무 서류 및 인증 현황", df_dashboard),
            "기한경과_미등록": ("🚨 기한 경과 및 미등록 항목 (갱신·보완 대상)", df_dashboard[mask_exp]),
            "30일": ("⚠️ 30일 이내 유효기한 만료 예정 항목", df_dashboard[mask_30].sort_values("_d_num")),
            "90일": ("📅 90일(3개월) 이내 갱신 도래 항목", df_dashboard[mask_90].sort_values("_d_num")),
            "180일": ("🗓️ 180일(6개월) 이내 갱신 도래 항목", df_dashboard[mask_180].sort_values("_d_num")),
            "정상_영구": ("✅ 적격 유지 및 영구 보존 항목", df_dashboard[mask_ok])
        }
        f_title, f_df = filter_map.get(cur_f, filter_map["전체"])

        st.markdown(f"#### {f_title} — 총 `{len(f_df)}건`")
        if f_df.empty:
            st.success("✅ 선택하신 상태 조건에 해당하는 항목이 없습니다.")
        else:
            st.dataframe(
                f_df[disp_cols].style.map(style_status, subset=['관리상태']),
                hide_index=True, use_container_width=True,
                column_config={"원문 열람": st.column_config.LinkColumn(display_text="원문 열람")}
            )

        st.markdown("---")
        st.markdown("#### 📂 영역별 법정 증빙 관리 대장")

        edu_insp_mask = df_dashboard["분류코드"].apply(lambda x: x.startswith(("수질검사_", "저수조", "방충방서_", "모의회수", "보건증_", "법정위생교육_", "HACCP정기교육", "HACCP팀장")))
        df_edu_insp = df_dashboard[edu_insp_mask]

        cert_mask = df_dashboard["분류코드"].apply(lambda x: x.startswith(("HACCP_", "CHINA_HACCP", "FSSC", "K-MILK", "무항생제", "유기가공", "FDA_", "책임보험")))
        df_cert = df_dashboard[cert_mask]

        handled_12 = set(df_edu_insp["분류코드"]).union(set(df_cert["분류코드"]))
        df_license = df_dashboard[~df_dashboard["분류코드"].isin(handled_12)]

        with st.expander("📅 1. 정기 위생검사 및 법정 의무교육 현황", expanded=False):
            st.dataframe(df_edu_insp[disp_cols].style.map(style_status, subset=['관리상태']), hide_index=True, use_container_width=True, column_config={"원문 열람": st.column_config.LinkColumn(display_text="원문 열람")})

        with st.expander("🥇 2. 국내외 식품안전 인증 및 배상책임보험 현황", expanded=False):
            st.dataframe(df_cert[disp_cols].style.map(style_status, subset=['관리상태']), hide_index=True, use_container_width=True, column_config={"원문 열람": st.column_config.LinkColumn(display_text="원문 열람")})

        with st.expander("📁 3. 사업장 영업 인허가 및 건축물·시설 등록 현황", expanded=False):
            st.dataframe(df_license[disp_cols].style.map(style_status, subset=['관리상태']), hide_index=True, use_container_width=True, column_config={"원문 열람": st.column_config.LinkColumn(display_text="원문 열람")})

# ----------------- MENU 4: ⚙️ 마스터 DB 관리 -----------------
elif current_tab == MAIN_TABS[3]:
    render_header_and_nav()
    st.markdown("### ⚙️ 클라우드 문서 일괄 AI 판독 및 마스터 DB 동기화")
    st.caption("구글 드라이브 웹에서 다수의 파일을 직접 추가한 경우, 미등록 신규 문서만 선별하여 마스터 데이터베이스(Google Sheets)에 일괄 반영합니다.")

    if not PYMUPDF_INSTALLED:
        st.error("🚨 고해상도 원문 뷰어 및 검색어 음영 표시를 위해 `requirements.txt`에 `PyMuPDF` 패키지를 설치해 주십시오.")

    scan_options = list(FLAT_FOLDER_DB.keys()) + ["가설건축물"]
    default_targets = ["인허가 서류", "가설건축물", "인증서", "수질검사", "물탱크청소", "교육수료증", "모의회수", "PL보험가입증명서", "기준서", "선행요건", "FSSC22000"]
    selected_targets = st.multiselect("📌 동기화 대상 보관함 선택", options=scan_options, default=default_targets)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 1단계: 보관함 내 전체 문서 확인", type="secondary", use_container_width=True):
            if not selected_targets:
                st.error("동기화할 보관함을 하나 이상 선택해 주십시오.")
            else:
                clear_all_folder_caches()
                files_to_scan = []
                with st.spinner("지정된 보관함 및 하위 폴더의 문서를 조회 중입니다..."):
                    for cat in selected_targets:
                        if cat == "가설건축물":
                            files_to_scan.extend(get_temp_building_files())
                        else:
                            files_to_scan.extend(get_cached_folder_files(cat))

                valid_files = [
                    f for f in files_to_scan
                    if not is_system_junk_file(f.get('name', '')) and ("pdf" in f['mimeType'].lower() or "image" in f['mimeType'].lower())
                ]
                st.info(f"📂 조회된 유효 파일: **{len(files_to_scan)}건** (판독 가능 PDF·이미지: **{len(valid_files)}건**)")
                st.session_state.files_to_scan = valid_files

    with col2:
        if st.button("🔄 2단계: 신규 미등록 문서 일괄 판독 및 DB 반영", type="primary", use_container_width=True):
            if "files_to_scan" not in st.session_state or not st.session_state.files_to_scan:
                st.warning("먼저 '1단계: 보관함 내 전체 문서 확인'을 실행해 주십시오.")
            else:
                service = get_drive_service()
                sheet_service = get_sheets_service()
                progress_bar = st.progress(0)
                log_box = st.empty()
                log_history, error_log = [], []

                def update_log(msg):
                    log_history.append(msg)
                    log_box.code("\n".join(log_history[-15:]), language="text")

                scanned_ids = set()
                if sheet_service and SHEET_ID:
                    try:
                        sc_res = sheet_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="SCANNED!A:A").execute()
                        for row in sc_res.get('values', []):
                            if row:
                                scanned_ids.add(row[0])
                    except Exception:
                        update_log("⚠️ SCANNED 이력 시트를 확인할 수 없어 전체 대상 분석을 시작합니다.")

                files_to_process = [f for f in st.session_state.files_to_scan if f['id'] not in scanned_ids]
                skipped_count = len(st.session_state.files_to_scan) - len(files_to_process)
                if skipped_count > 0:
                    update_log(f"⏭️ 기등록 완료 문서 {skipped_count}건 제외 / 신규 문서 {len(files_to_process)}건 판독 시작")

                total = len(files_to_process)
                if total == 0:
                    update_log("✅ 모든 문서가 이미 마스터 DB에 최신 상태로 등록되어 있습니다.")
                    st.success("추가로 동기화할 신규 문서가 없습니다.")
                else:
                    model = genai.GenerativeModel(MODEL_NAME)
                    allowed_dynamic_prefixes = ("가설건축물_", "수질검사_", "보건증_", "법정위생교육_", "HACCP교육_", "HACCP팀장")

                    for i, f in enumerate(files_to_process):
                        update_log(f"⏳ [{i+1}/{total}] 문서 메타데이터 판독 중: {f['name']}")
                        progress_bar.progress((i + 1) / total)
                        fid = f['id']
                        try:
                            mime = f['mimeType'].lower()
                            if "pdf" in mime: ext = ".pdf"
                            elif "png" in mime: ext = ".png"
                            elif "jpeg" in mime or "jpg" in mime: ext = ".jpg"
                            else:
                                continue

                            file_bytes = download_file_bytes(service, fid)
                            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                                tmp.write(file_bytes)
                                tmp_path = tmp.name

                            up_file = genai.upload_file(path=tmp_path)
                            wait_time = 0
                            while up_file.state.name == "PROCESSING" and wait_time < 300:
                                time.sleep(5)
                                wait_time += 5
                                up_file = genai.get_file(up_file.name)

                            if up_file.state.name != "ACTIVE":
                                raise Exception("문서 파일 처리 지연 또는 손상")

                            time.sleep(3.5)
                            ai_res = model.generate_content([up_file, MASTER_SCAN_PROMPT])
                            json_match = re.search(r'\{.*\}', ai_res.text.strip(), re.DOTALL)
                            if not json_match:
                                raise Exception("메타데이터 JSON 추출 형식 오류")

                            parsed = json.loads(json_match.group(0))
                            kw = parsed.get("키워드", "")
                            if kw not in ("PASS", "기타", "매뉴얼", "일반수료증", "HACCP정기교육", "HACCP팀장및경영자교육") and kw not in MASTER_DOC_REQUIREMENTS and not kw.startswith(allowed_dynamic_prefixes):
                                kw = "기타"

                            if kw != "PASS":
                                cycle = str(MASTER_DOC_REQUIREMENTS.get(kw, {}).get("주기", 0))
                                if kw.startswith("법정위생교육_") or kw == "HACCP정기교육":
                                    cycle = "12"
                                new_row = [
                                    kw, f['name'], parsed.get("문서_실제제목", ""), parsed.get("발급일", ""), parsed.get("만료일", ""),
                                    cycle, parsed.get("개정번호", "-"), parsed.get("분류근거", ""), fid, f['webViewLink']
                                ]
                                if sheet_service and SHEET_ID:
                                    sheet_service.spreadsheets().values().append(
                                        spreadsheetId=SHEET_ID, range="DB!A:A", valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                                        body={'values': [new_row]}
                                    ).execute()
                                    sheet_service.spreadsheets().values().append(
                                        spreadsheetId=SHEET_ID, range="SCANNED!A:B", valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                                        body={'values': [[fid, f['name']]]}
                                    ).execute()
                                    row_dict = {
                                        "키워드": kw, "파일명": f['name'], "문서_실제제목": parsed.get("문서_실제제목", ""),
                                        "발급일": parsed.get("발급일", ""), "만료일": parsed.get("만료일", ""), "주기(개월)": cycle,
                                        "개정번호": parsed.get("개정번호", "-"), "분류근거": parsed.get("분류근거", ""),
                                        "파일 ID": fid, "뷰어 링크": f['webViewLink']
                                    }
                                    st.session_state.auto_db.append(row_dict)

                            update_log(f"✅ [{i+1}/{total}] 마스터 DB 반영 완료 ({kw})")
                            genai.delete_file(up_file.name)
                            os.remove(tmp_path)
                        except Exception as e:
                            error_msg = str(e)
                            if "429" in error_msg or "quota" in error_msg.lower():
                                update_log(f"⚠️ [{i+1}/{total}] API 호출량 조절 대기(15초)...")
                                time.sleep(15)
                            else:
                                update_log(f"❌ [{i+1}/{total}] 판독 제외: {error_msg}")
                                error_log.append(f"'{f['name']}': {error_msg}")

                    clear_all_folder_caches()
                    st.success("✅ 신규 문서 판독 및 마스터 DB 동기화가 완료되었습니다.")
                    if error_log:
                        with st.expander(f"⚠️ 확인이 필요한 항목 ({len(error_log)}건)"):
                            for err in error_log:
                                st.write(err)

# ----------------- MENU 5: ⚖️ 규정 · 법규 검증 -----------------
elif current_tab == MAIN_TABS[4]:
    def render_chat_panel_body():
        st.markdown("### ⚖️ 사내 식품안전 기준 및 법적 인허가·인증 규격 검증")
        st.caption("3단계 교차 검증(사내 기준 추출 ➔ 법령·인증 범위 대조 ➔ 공식 검토 보고)을 수행하며, 답변 하단의 **[1], [2] 근거 문헌**을 선택하면 우측 화면에 해당 원문 페이지가 즉시 표시됩니다.")

        for msg_idx, msg in enumerate(st.session_state.chat_messages):
            with st.chat_message(msg["role"]):
                safe_content = re.sub(r'(\d)~(\d)', r'\1&#126;\2', msg["content"])
                st.markdown(safe_content, unsafe_allow_html=True)

                cits = msg.get("citations", [])
                if msg["role"] == "assistant" and cits:
                    st.markdown("##### 📚 판단 근거 문헌 및 기준서 출처 (선택 시 우측 원문 해당 페이지 열람)")
                    prev_user_q = ""
                    if msg_idx > 0 and st.session_state.chat_messages[msg_idx - 1]["role"] == "user":
                        prev_user_q = st.session_state.chat_messages[msg_idx - 1]["content"]

                    for c_idx, cit in enumerate(cits):
                        num_no = cit.get("번호", c_idx + 1)
                        doc_nm = cit.get("문서명", "사내 기준서")
                        why_txt = cit.get("도출사유", "")
                        cc1, cc2 = st.columns([7.5, 2.5])
                        with cc1:
                            st.markdown(
                                f"<div class='citation-card'>"
                                f"<b>[{num_no}] {doc_nm}</b><br>"
                                f"<span style='font-size:0.88rem; color:#475569;'>• 적용 근거: {why_txt}</span>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        with cc2:
                            st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
                            if st.button(f"📄 [{num_no}] 원문 열람", key=f"cit_open_{msg_idx}_{c_idx}", type="primary", use_container_width=True):
                                with st.spinner(f"'{doc_nm}' 해당 조항 페이지를 탐색 중입니다..."):
                                    resolved = resolve_citation_to_viewer(cit, question_text=prev_user_q)
                                    if resolved:
                                        st.session_state.chat_doc_viewer = resolved
                                        st.rerun()
                                    else:
                                        st.warning(f"'{doc_nm}' 원문을 자동 매칭하지 못했습니다. 좌측 '통합 문서 검색'을 이용해 주십시오.")

        if user_prompt := st.chat_input("검토할 공정 기준, 한계기준, 인증 범위 또는 선행요건 사항을 입력해 주십시오."):
            st.session_state.chat_messages.append({"role": "user", "content": user_prompt})
            with st.chat_message("user"):
                st.markdown(user_prompt)

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                with st.status("🛡️ 3단계 규정 및 법적 인증 범위 교차 검증 진행 중...", expanded=True) as status:
                    try:
                        ensure_auto_db_loaded()
                        kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False)
                        docs_catalog = build_available_docs_catalog()
                        cache_name = st.session_state.get("master_cache_name")

                        if cache_name:
                            try:
                                cache = genai.caching.CachedContent.get(cache_name)
                                base_model = genai.GenerativeModel.from_cached_content(cached_content=cache)
                            except Exception:
                                base_model = genai.GenerativeModel(model_name=MODEL_NAME)
                        else:
                            base_model = genai.GenerativeModel(model_name=MODEL_NAME)

                        st.write("📋 **[1단계: 사내 기준 추출]** 전후 연계 공정(End-to-End) 및 선행요건 관련 기준 확인 중...")
                        prompt_A = f"""[Agent A 임무: 사내 기준 및 공정 데이터 추출]
                        지식베이스:\n{kb_str}\n\n사용자 질의: {user_prompt}
                        
                        임무: 사용자의 질의에 정확히 답변하기 위한 객관적인 기준 데이터 리포트를 작성하십시오.
                        
                        [전 공정(End-to-End) 통합 추출 원칙]:
                        사용자가 특정 단일 공정(예: 살균, 여과)이나 특정 반제품(예: 원액두유, 배양액)에 국한하여 질의하더라도 해당 구간만 단편적으로 추출하지 마십시오.
                        지식베이스 및 적재된 기준서를 탐색하여 해당 품목·공정과 직결되는 [원료 수불 및 전처리 ➔ 주 가공 및 살균/멸균 ➔ 여과 ➔ 무균 충전·포장(포장지 멸균) ➔ 완제품 출하]까지의 전체 공정 체계와 이에 따른 모든 중요관리점(CCP) 및 선행요건 기준을 포괄적으로 도출하여 기술하십시오."""
                        res_A = base_model.generate_content(prompt_A).text

                        st.write("⚖️ **[2단계: 법규·인증 범위 대조]** 사내 기준서 및 품목별 법적 인증 효력 교차 검증 중...")
                        prompt_B = f"""[Agent B 임무: 법규 및 인증 규격 적격성 검수]
                        [현재 아산공장 인증 보유 현황]: 지식베이스의 '공장현재인증현황' 참고.
                        
                        [Agent A가 도출한 공정 및 기준 분석 내용]:
                        {res_A}
                        
                        임무: 메모리에 적재된 마스터 지식베이스, 기준서 및 실제 HACCP/FSSC22000 인증서를 대조하여 다음 기준에 따라 엄격히 교차 검증하십시오.
                        
                        트랙 1 (인증 범위 / 신제품 도입 / 공정 변경 질의):
                        - [품목별 법적 독립성 엄수 원칙]: 식품위생법 및 축산물위생관리법상 HACCP 인증은 철저히 '개별 품목(유형)' 단위로 부여됩니다. 타 품목(예: 가공두유)이 무균포장 공정 인증을 보유하고 있더라도, 질의 대상 품목(예: 원액두유)이 물리적으로 동일한 설비 라인을 공유한다는 이유만으로 법적 인증 효력이 자동 승계되거나 공유되지 않습니다.
                        - 질의 대상 품목의 인증서 및 기준서상 특정 공정(예: 여과, 살균)까지만 인증이 완료되어 있다면, "완제품 포장 출하를 위해서는 누락된 후속 공정(멸균 및 포장 등)에 대한 HACCP 변경인증(공정 추가) 및 품목제조보고를 관할 기관으로부터 사전 취득해야 함"을 법적 근거에 입각하여 명확히 판정하십시오.
                        
                        트랙 2 (일반 위생 규정 / 작업장 기준 / 선행요건 질의):
                        - 작업장 환경, 개인위생, 방충방서, CIP, 보관·운송 등 일반 기준 질의는 Agent A가 추출한 수치와 주기가 사내 기준서와 정확히 일치하는지 검증하여 확정하십시오."""
                        res_B = base_model.generate_content(prompt_B).text

                        st.write("📑 **[3단계: 공식 검토 보고서 작성]** 최종 검토 의견 및 근거 문헌 출처 연결 중...")
                        history_for_gemini = []
                        for m in st.session_state.chat_messages[-6:-1]:
                            if m["role"] == "assistant":
                                if "안녕하십니까" in m["content"] or "안녕하세요!" in m["content"]:
                                    continue
                                history_for_gemini.append({"role": "model", "parts": [m["content"]]})
                            else:
                                history_for_gemini.append({"role": "user", "parts": [m["content"]]})

                        prompt_C = f"""[Agent C 임무: 공식 심사 대응 및 경영진 보고용 최종 답변 작성]
                        [Agent B의 법규·인증 교차검증 판정 결과]:
                        {res_B}
                        
                        [현재 사내 드라이브에 실제 등록된 문서 목록]:
                        {docs_catalog}
                        
                        임무: 위 검증 결과를 바탕으로 외부 심사원(방문심사 업체, 인증기관) 및 사내 경영진·상급자가 직접 열람할 수 있는 수준의 명확하고 품격 있는 공식 답변을 작성하십시오.
                        
                        [작성 수칙 및 어조(Tone & Manner) 절대 원칙]:
                        1. **공식 비즈니스 경어체 엄수**: '숲', '나비효과', '퉁치다', '건바이건' 등 비유적 표현이나 구어체, 가벼운 수식어 사용을 전면 금지합니다. 철저히 정중하고 격식 있는 경어체(~합니다, ~입니다, ~바랍니다)와 정확한 식품안전 전문 용어(한계기준, 중요관리점, 유효성 평가, 변경관리, 교차오염 방지, 선행요건 등)만을 사용하여 신뢰감 있게 서술하십시오.
                        2. **종합 판정 결론 최상단 명시**: 답변 첫 줄에 질의 사항에 대한 최종 판정 결론(현행 기준 적합 여부, 조건부 가능, 변경인증 필수 여부 등)을 두괄식으로 명확히 선언하십시오. 특히 품목별 미인증 공정이 존재하는 경우, 현 상태로는 완제품 출하가 불가하며 관할 기관의 변경인증(공정 추가)이 선행되어야 함을 명확히 명시하십시오.
                        3. **전체 공정 체계 및 관리 기준 제시**: 해당 품목이 완제품으로 출하되기 위해 거쳐야 하는 전체 공정 흐름을 제시할 때에는 화면 우측으로 잘리는 가로형 코드블록 대신 가독성 높은 마크다운 표(Table) 또는 번호 목록으로 정리하십시오. 또한 범위 표기 시 마크다운 취소선이 발생하지 않도록 물결표(~) 대신 하이픈(-)이나 '내지'를 사용하거나 정확히 표기하십시오.
                        4. **전사적 연계 영향 및 각주 번호([1], [2]) 표기**: 답변의 핵심 판단 근거가 되는 문장 끝에 각주 번호(`[1]`, `[2]` 등, 최대 4개)를 표기하고, 답변 맨 마지막 줄 아래에 위 [현재 사내 드라이브에 실제 등록된 문서 목록]에 존재하는 실제 파일명을 기준으로 아래와 같은 정확한 `<CITATIONS>` JSON 블록을 반드시 첨부하십시오.
                        <CITATIONS>
                        [
                          {{"번호": 1, "문서명": "실제 등록된 정확한 파일명", "도출사유": "이 문서를 근거로 해당 답변을 도출한 핵심 이유 1줄 요약", "핵심구절": "해당 문서 본문에서 찾아 형광펜 음영을 칠할 핵심 기준 수치 또는 구절"}}
                        ]
                        </CITATIONS>"""

                        final_chat = base_model.start_chat(history=history_for_gemini)
                        res_C = final_chat.send_message(prompt_C)
                        clean_answer, extracted_citations = parse_chatbot_citations(res_C.text)

                        status.update(label="✅ 규정 교차 검증 및 근거 출처 연결 완료", state="complete", expanded=False)
                        safe_full_response = re.sub(r'(\d)~(\d)', r'\1&#126;\2', clean_answer)
                        message_placeholder.markdown(safe_full_response, unsafe_allow_html=True)
                        st.session_state.chat_messages.append({
                            "role": "assistant",
                            "content": clean_answer,
                            "citations": extracted_citations
                        })
                        st.rerun()
                    except Exception as e:
                        err_msg = f"⚠️ 검증 시스템 처리 중 오류가 발생하였습니다: {e}"
                        status.update(label="🚨 시스템 오류 발생", state="error", expanded=False)
                        message_placeholder.error(err_msg)
                        st.session_state.chat_messages.append({"role": "assistant", "content": err_msg, "citations": []})

    if st.session_state.chat_doc_viewer:
        chat_left, chat_right = st.columns([0.95, 1.45], gap="large")
        with chat_left:
            render_header_and_nav()
            render_chat_panel_body()
        with chat_right:
            v_info = st.session_state.chat_doc_viewer
            render_full_height_doc_viewer(v_info, highlight_kw=v_info.get("highlight_kw", ""), viewer_context="chat")
    else:
        render_header_and_nav()
        render_chat_panel_body()
