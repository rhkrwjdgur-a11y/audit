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
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# [0] 시스템 픽스 및 타임아웃 방어막
# ==========================================
st.set_page_config(page_title="HACCP Agent", page_icon="🛡️", layout="wide")
socket.setdefaulttimeout(600)

try:
    import fitz  # PyMuPDF
    PYMUPDF_INSTALLED = True
except ImportError:
    PYMUPDF_INSTALLED = False

CACHE_META_FILE = "haccp_agent_cache.json"

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
# [0-1] 구글 드라이브 폴더 1:1 매칭 DB
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
# [0-3] 법정주기 및 필수 서류 마스터 리스트 (Top-down 고정 항목)
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
# [1] 상태 초기화 및 커스텀 디자인
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

if "priority_keywords" not in st.session_state: st.session_state.priority_keywords = []
if "search_done" not in st.session_state: st.session_state.search_done = False
if "search_mode" not in st.session_state: st.session_state.search_mode = "exact"
if "found_files" not in st.session_state: st.session_state.found_files = []
if "aux_files" not in st.session_state: st.session_state.aux_files = []
if "search_keyword" not in st.session_state: st.session_state.search_keyword = ""
if "search_question" not in st.session_state: st.session_state.search_question = ""
if "final_briefing" not in st.session_state: st.session_state.final_briefing = ""
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

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [{"role": "assistant", "content": "안녕하십니까. 연세유업 아산공장 식품안전 및 HACCP 통합 검증 시스템입니다. 공정 관리 기준, 선행요건, 법적 인허가 및 인증 규격에 대해 문의해 주시면 사내 기준서와 현행 법령을 교차 검증하여 명확히 안내해 드리겠습니다."}]

custom_theme_css = """
<style>
@media screen {
    html, body, [class*="css"] { color: #1e293b !important; font-family: 'Pretendard', sans-serif !important; }
    [data-testid="stSidebar"] { background-color: #f8fafc !important; border-right: 1px solid #e2e8f0 !important; }
    [data-testid="stSidebar"] [data-testid="stExpander"] details { background-color: #f8fafc !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; }
    [data-testid="stSidebar"] button { background-color: #0f172a !important; color: white !important; font-weight: bold !important; border-radius: 8px !important; padding: 8px 16px !important; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1) !important; transition: all 0.2s; }
    [data-testid="stSidebar"] button:hover { background-color: #334155 !important; transform: translateY(-1px); }
    [data-testid="stSidebar"] button p { color: #ffffff !important; font-weight: bold !important; }

    .stTabs [data-baseweb="tab-list"] { border-bottom: 2px solid #e2e8f0 !important; gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: transparent !important; border: none !important; border-bottom: 3px solid transparent !important; padding: 12px 16px !important; color: #64748b !important; font-weight: 600 !important; }
    .stTabs [aria-selected="true"] { border-bottom: 3px solid #0f172a !important; color: #0f172a !important; }

    table { border-collapse: collapse !important; width: 100% !important; margin: 1.5rem 0 !important; border: 2px solid #0f172a !important; border-radius: 8px !important; overflow: hidden !important; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1) !important; }
    thead tr { background-color: #f8fafc !important; color: #0f172a !important; border-bottom: 2px solid #0f172a !important; }
    th { font-weight: 700 !important; padding: 12px 16px !important; text-align: left !important; border-right: 1px solid #cbd5e1 !important; }
    td { padding: 12px 16px !important; border-right: 1px solid #cbd5e1 !important; border-bottom: 1px solid #e2e8f0 !important; }
    tbody tr:hover { background-color: #f1f5f9 !important; }

    .mfds-banner { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 18px 24px; text-align: center; font-size: 1.15rem; font-weight: 600; margin-bottom: 20px; }
    .mfds-result-item { border-bottom: 1px solid #e2e8f0; padding: 14px 8px; }
    .mfds-title { font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 6px; }
    .mfds-path { font-size: 0.85rem; color: #64748b; font-weight: 500; }
    .mfds-snippet { font-size: 0.95rem; color: #334155; line-height: 1.6; margin-top: 6px; }
    .mfds-key { color: #dc2626; font-weight: 800; background-color: #fef08a; padding: 1px 4px; border-radius: 3px; }
}
</style>
"""
st.markdown(custom_theme_css, unsafe_allow_html=True)

# ==========================================
# [2] API 인증 및 서비스
# ==========================================
MODEL_NAME = "models/gemini-3.8-flash"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/spreadsheets']

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    SHEET_ID = st.secrets["MASTER_SHEET_ID"] if "MASTER_SHEET_ID" in st.secrets else ""
    genai.configure(api_key=GEMINI_API_KEY)
except Exception:
    st.error("🚨 필수 키(secrets)가 누락되었습니다.")
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
# [3] 유틸리티, 날짜/최신본 정밀 정렬 및 음영 뷰어 엔진
# ==========================================
def _safe_ymd(y, m, d):
    """달력상 유효한 날짜인지 검증하여 잘못된 일련번호 매칭으로 인한 오류를 방지합니다."""
    try:
        dt = datetime.date(int(y), int(m), int(d))
        return (dt.year, dt.month, dt.day)
    except Exception:
        return None

def parse_doc_date_tuple(filename, date_str=""):
    """파일명 및 발급일에서 유효한 (연, 월, 일) 튜플을 정확히 추출하여 최신본 정렬에 사용합니다."""
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
        return "미상"
    return f"{dt_tuple[0]:04d}-{dt_tuple[1]:02d}-{dt_tuple[2]:02d}"

def extract_year_string(filename, created_time=""):
    dt = parse_doc_date_tuple(filename, created_time)
    if dt[0] > 1900:
        return f"{dt[0]}년도"
    return f"{str(created_time)[:4]}년도" if created_time and len(str(created_time)) >= 4 else "분류 없음"

def is_pest_vendor_doc(row_or_name, folder_path=""):
    """외주 방역업체(삼양인터내셔날 등) 소속 보험/보건증인지 판별하여 자사 서류와 엄격히 분리합니다."""
    if isinstance(row_or_name, dict):
        combined = f"{row_or_name.get('파일명', '')} {row_or_name.get('문서_실제제목', '')} {row_or_name.get('분류근거', '')} {folder_path}"
    else:
        combined = f"{row_or_name} {folder_path}"
    pest_markers = ["삼양인터내셔날", "삼양인터네셔날", "소독,해충구제", "방제업무", "방충방서 관련 서류", "배동섭", "남정현", "권도훈"]
    return any(pm in combined for pm in pest_markers)

def is_blacklisted(filename, category_name=""):
    fn = str(filename)
    if "Thumbs.db" in fn or fn.endswith(".txt") or fn.endswith(".hwp"):
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

@st.cache_data(ttl=1800)
def get_all_managed_folders_map(_service):
    folder_map = {}
    if DRIVE_FOLDER_ID:
        folder_map[DRIVE_FOLDER_ID] = "방문심사"
    for cat_name, root_fid in FLAT_FOLDER_DB.items():
        if root_fid.startswith("folder_id_"):
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

@st.cache_data(ttl=900)
def get_drive_supplement_files():
    """시트 미스캔 최신 파일들을 드라이브 폴더에서 실시간 보완 조회합니다."""
    service = get_drive_service()
    if not service:
        return []
    folder_map = get_all_managed_folders_map(service)
    target_cats = ["인허가 서류", "인증서", "수질검사", "물탱크청소", "방충방서 관련 서류", "교육수료증", "모의회수", "PL보험가입증명서", "선행요건", "기준서", "FSSC22000"]
    target_fids = [fid for fid, path in folder_map.items() if any(path.startswith(tc) for tc in target_cats)]

    supplement = []
    seen = set()
    for idx in range(0, len(target_fids), 20):
        chunk = target_fids[idx:idx + 20]
        parents_q = " or ".join([f"'{fid}' in parents" for fid in chunk])
        page_token = None
        while True:
            try:
                res = service.files().list(
                    q=f"({parents_q}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                    fields="nextPageToken, files(id, name, webViewLink, mimeType, createdTime, parents)",
                    pageSize=1000, pageToken=page_token
                ).execute()
                for f in res.get('files', []):
                    if f['id'] in seen:
                        continue
                    seen.add(f['id'])
                    p_label = ""
                    for p in f.get('parents', []):
                        if p in folder_map:
                            p_label = folder_map[p]
                            break
                    f['folder_path'] = p_label
                    supplement.append(f)
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
            except Exception:
                break
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

def normalize_education_key(fname, rtitle="", reason=""):
    """교육 수료증의 파일명·실제제목·분류근거를 종합 분석하여 표준 업종 키로 정규화합니다."""
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
    """동일 항목(슬롯) 내 과거 연도 중복 문서를 제거하고 가장 최신 문서 1건만 남깁니다."""
    best_by_slot = {}
    for f in files:
        slot = str(slot_fn(f))
        score = parse_doc_date_tuple(f.get('name', ''), f.get('createdTime', ''))
        if slot not in best_by_slot or score >= best_by_slot[slot][0]:
            best_by_slot[slot] = (score, f)
    sorted_items = sorted(best_by_slot.values(), key=lambda x: x[0], reverse=True)
    return [item[1] for item in sorted_items]

def analyze_pdf_matches_strict(file_bytes, keyword):
    """딥 서치 시 연속 구문 또는 동일 문맥(35자 이내 근접) 일치 페이지만 정확히 추출합니다."""
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

def analyze_pdf_matches(file_bytes, keyword):
    return analyze_pdf_matches_strict(file_bytes, keyword)

def extract_snippet_from_pdf(file_bytes, keyword):
    _, snip_str = analyze_pdf_matches_strict(file_bytes, keyword)
    return snip_str if snip_str else "💡 문서 내 텍스트 매칭 없음 (파일명 매칭 또는 이미지 스캔본)"

def render_highlighted_pdf_page(file_bytes, page_num, keyword):
    """특정 PDF 페이지 내 검색어 위치에 연두색 형광펜 음영을 칠해 고해상도 이미지로 반환합니다."""
    if not PYMUPDF_INSTALLED or not file_bytes:
        return None, 0, []
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            return None, 0, []

        kw_clean = keyword.strip() if keyword else ""
        matched_pages, _ = analyze_pdf_matches_strict(file_bytes, kw_clean) if kw_clean else ([], "")

        p_idx = max(0, min(int(page_num) - 1, total_pages - 1))
        page = doc[p_idx]

        if kw_clean:
            rects = page.search_for(kw_clean)
            if not rects:
                rects = page.search_for(kw_clean.replace(" ", ""))
            if not rects:
                for token in [t for t in re.split(r'[\s,()/·~-]+', kw_clean) if len(t) >= 2]:
                    rects.extend(page.search_for(token))
            for r in rects:
                annot = page.add_highlight_annot(r)
                annot.set_colors(stroke=(0.65, 0.92, 0.45))
                annot.update()

        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes, total_pages, matched_pages
    except Exception:
        return None, 0, []

def execute_deep_search(query_text):
    service = get_drive_service()
    if not service:
        return
    ensure_auto_db_loaded()

    keyword = query_text.strip()
    tokens = [t.lower() for t in re.split(r'\s+', keyword) if t]
    compact_kw = keyword.replace(" ", "").lower()

    title_synonyms = [compact_kw]
    if "영업" in compact_kw and "등록" in compact_kw:
        title_synonyms.extend(["영업등록", "영업등록증"])
    if "영업" in compact_kw and "신고" in compact_kw:
        title_synonyms.extend(["영업신고", "영업신고증"])

    st.session_state.update({
        "search_done": True, "search_mode": "deep",
        "search_keyword": keyword, "search_question": query_text,
        "target_folder_key": None, "gw_keyword": "", "gw_keywords_list": [],
        "priority_keywords": [], "last_file_id": "",
        "selected_doc_idx": 0, "selected_page_num": 1, "aux_files": []
    })

    with st.spinner(f"🔍 전체 하위 폴더 및 PDF 본문에서 '{keyword}' 정밀 검증 및 음영 좌표를 분석 중입니다..."):
        folder_map = get_all_managed_folders_map(service)
        managed_folder_ids = set(folder_map.keys())
        db_by_fid = {row.get("파일 ID", ""): row for row in st.session_state.auto_db if row.get("파일 ID")}

        raw_candidates = {}
        for fid, row in db_by_fid.items():
            fname = str(row.get("파일명", ""))
            rtitle = str(row.get("문서_실제제목", ""))
            title_comb = f"{fname} {rtitle}".replace(" ", "").lower()
            if any(syn in title_comb for syn in title_synonyms) or (tokens and all(tk in title_comb for tk in tokens)):
                raw_candidates[fid] = {
                    'id': fid, 'name': fname or rtitle,
                    'webViewLink': row.get("뷰어 링크", f"https://drive.google.com/file/d/{fid}/view"),
                    'createdTime': row.get("발급일", ""), 'mimeType': 'application/pdf',
                    'folder_path': f"마스터 DB > {row.get('키워드', '')}",
                    'is_title_match': True
                }

        safe_kw = keyword.replace("'", "\\'")
        page_token = None
        while True:
            res = service.files().list(
                q=f"(name contains '{safe_kw}' or fullText contains '{safe_kw}') and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                spaces='drive',
                fields='nextPageToken, files(id, name, webViewLink, mimeType, createdTime, parents)',
                pageSize=1000, pageToken=page_token
            ).execute()
            for f in res.get('files', []):
                parents = f.get('parents', [])
                if not managed_folder_ids or any(p in managed_folder_ids for p in parents):
                    fid = f['id']
                    parent_label = next((folder_map[p] for p in parents if p in folder_map), "사내 문서함")
                    fn_comp = f['name'].replace(" ", "").lower()
                    t_match = any(syn in fn_comp for syn in title_synonyms) or (tokens and all(tk in fn_comp for tk in tokens))
                    if fid not in raw_candidates:
                        f['folder_path'] = parent_label
                        f['is_title_match'] = t_match
                        raw_candidates[fid] = f
                    else:
                        raw_candidates[fid]['folder_path'] = parent_label
                        raw_candidates[fid]['is_title_match'] = raw_candidates[fid]['is_title_match'] or t_match
            page_token = res.get('nextPageToken')
            if not page_token:
                break

        verified_files = []
        for fid, f in list(raw_candidates.items())[:35]:
            is_t_match = f.get('is_title_match', False)
            m_pages, snip_text = [], ""

            if PYMUPDF_INSTALLED and "pdf" in f.get('mimeType', '').lower():
                try:
                    file_bytes = get_cached_file_bytes(fid)
                    m_pages, snip_text = analyze_pdf_matches_strict(file_bytes, keyword)
                except Exception:
                    pass

            if m_pages:
                f['matched_pages'] = m_pages
                f['snippet'] = snip_text
                f['rank_score'] = (2 if is_t_match else 1, len(m_pages))
                verified_files.append(f)
            elif is_t_match:
                f['matched_pages'] = [1]
                if fid in db_by_fid:
                    r = db_by_fid[fid]
                    f['snippet'] = f"[공식 증빙 문서] 명칭: {r.get('문서_실제제목', f['name'])} | 발급일: {r.get('발급일', '-')} | 유효기간: {r.get('만료일', '-')} | 내용: {r.get('분류근거', '-')}"
                else:
                    f['snippet'] = f"[문서 제목 일치] {f['name']}"
                f['rank_score'] = (2, 1)
                verified_files.append(f)

        verified_files.sort(key=lambda x: x.get('rank_score', (0, 0)), reverse=True)
        st.session_state.found_files = verified_files
        if verified_files:
            st.session_state.selected_doc_idx = 0
            first_pages = verified_files[0].get('matched_pages', [1])
            st.session_state.selected_page_num = first_pages[0] if first_pages else 1

def locate_reference_in_drive(ref_term):
    """챗봇 답변의 강조 문구(굵은 글씨 또는 규정 코드) 클릭 시 해당 문서와 페이지를 즉시 찾아냅니다."""
    service = get_drive_service()
    if not service:
        return None
    ensure_auto_db_loaded()

    clean_term = re.sub(r'[*_`\[\]]', '', ref_term).strip()

    rule_alias_map = {
        "보관": ["보관 및 운반", "보관운반"],
        "운반": ["보관 및 운반", "보관운반"],
        "작업장": ["작업장기준서"],
        "조도": ["작업장기준서"],
        "온습도": ["작업장기준서", "보관 및 운반"],
        "온·습도": ["작업장기준서", "보관 및 운반"],
        "위생": ["위생관리기준서"],
        "복장": ["위생관리기준서"],
        "이물": ["이물관리기준서"],
        "장갑": ["장갑관리기준서"],
        "냉장": ["냉장냉동설비", "보관 및 운반"],
        "해동": ["해동관리기준서"],
        "검사": ["검사관리기준서"],
        "알러겐": ["알러겐 관리기준서", "알러겐"],
        "알레르기": ["알러겐 관리기준서", "알러겐"],
        "용수": ["용수관리 기준서"],
        "회수": ["제품회수관리기준서", "위기관리규정"],
        "M-100": ["품질경영매뉴얼", "M-100"],
        "P-210": ["식품보안 관리 규정", "시정조치", "P-210"],
        "식품보안": ["식품보안 관리 규정", "P-210"],
        "제한구역": ["식품보안 관리 규정", "P-210"],
        "P-200": ["부적합품관리규정", "협력업체관리규정", "경영검토규정", "교육훈련규정", "P-200"],
        "부적합": ["부적합품관리규정"],
        "협력업체": ["협력업체관리규정"],
        "내부감사": ["내부감사", "P-800"],
        "P-100": ["품질보증 업무규정", "부대시설관리규정", "환경관리규정", "생산관리규정", "문서관리"],
        "P-300": ["고객불만처리규정", "작업환경및안전", "식품사기대응규정", "공정관리규정"],
        "P-900": ["위기관리규정"],
        "가설건축물": ["가설건축물", "보관 및 운반", "작업장기준서"],
        "원액두유": ["원액두유"],
        "가공두유": ["가공두유"],
        "살균": ["제조공정설명서", "HACCP PLAN"],
        "멸균": ["제조공정설명서", "HACCP PLAN"],
        "테트라팩": ["HACCP PLAN", "제조공정설명서"],
        "콤비팩": ["HACCP PLAN", "제조공정설명서"],
        "CIP": ["제조시설관리기준서", "위생관리기준서"]
    }

    search_hints = [clean_term]
    for k, v_list in rule_alias_map.items():
        if k.lower() in clean_term.lower():
            search_hints.extend(v_list)

    folder_map = get_all_managed_folders_map(service)
    managed_folder_ids = set(folder_map.keys())
    candidates = []
    seen_ids = set()

    for row in reversed(st.session_state.auto_db):
        fid = row.get("파일 ID", "")
        if not fid or fid in seen_ids:
            continue
        fname = str(row.get("파일명", ""))
        rtitle = str(row.get("문서_실제제목", ""))
        if any(h.replace(" ", "").lower() in (fname + rtitle).replace(" ", "").lower() for h in search_hints):
            seen_ids.add(fid)
            candidates.append({'id': fid, 'name': fname or rtitle, 'webViewLink': row.get("뷰어 링크", f"https://drive.google.com/file/d/{fid}/view")})

    for h in search_hints[:3]:
        safe_h = h.replace("'", "\\'")
        try:
            res = service.files().list(
                q=f"(name contains '{safe_h}' or fullText contains '{safe_h}') and mimeType = 'application/pdf' and trashed = false",
                fields="files(id, name, webViewLink, parents)", pageSize=15
            ).execute()
            for f in res.get('files', []):
                if f['id'] not in seen_ids:
                    parents = f.get('parents', [])
                    if not managed_folder_ids or any(p in managed_folder_ids for p in parents):
                        seen_ids.add(f['id'])
                        candidates.append(f)
        except Exception:
            pass

    if not candidates:
        return None

    kw_tokens = [clean_term] + [t for t in re.split(r'[\s,()/·~:-]+', clean_term) if len(t) >= 2]
    for cand in candidates[:6]:
        try:
            f_bytes = get_cached_file_bytes(cand['id'])
            for token in kw_tokens:
                m_pages, _ = analyze_pdf_matches_strict(f_bytes, token)
                if m_pages:
                    return {
                        'id': cand['id'], 'name': cand['name'],
                        'webViewLink': cand.get('webViewLink', f"https://drive.google.com/file/d/{cand['id']}/view"),
                        'page': m_pages[0], 'matched_pages': m_pages,
                        'highlight_kw': token, 'ref_term': clean_term
                    }
        except Exception:
            pass

    top_cand = candidates[0]
    return {
        'id': top_cand['id'], 'name': top_cand['name'],
        'webViewLink': top_cand.get('webViewLink', f"https://drive.google.com/file/d/{top_cand['id']}/view"),
        'page': 1, 'matched_pages': [1],
        'highlight_kw': clean_term, 'ref_term': clean_term
    }
# ==========================================
# [3-추가] 전 구간 핀셋 매칭·가설건축물 자동탐색·다중 GW 연동 고도화 엔진
# ==========================================
if "gw_keywords_list" not in st.session_state:
    st.session_state.gw_keywords_list = []

@st.cache_data(ttl=1800)
def get_temp_building_files():
    """상위 또는 별도 경로에 위치한 '가설건축물' 폴더를 이름으로 자동 탐색하여 내부 필증·연장공문 전체를 반환합니다."""
    service = get_drive_service()
    if not service:
        return []
    found = []
    seen = set()
    try:
        res_folders = service.files().list(
            q="name contains '가설건축물' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id, name)", pageSize=20
        ).execute()
        for folder in res_folders.get('files', []):
            sub_ids = get_target_folder_ids(service, folder['id'])
            for fid in sub_ids:
                res_f = service.files().list(
                    q=f"'{fid}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                    fields="files(id, name, webViewLink, mimeType, createdTime)", pageSize=200
                ).execute()
                for f in res_f.get('files', []):
                    if f['id'] not in seen and not is_blacklisted(f['name'], "인허가"):
                        seen.add(f['id'])
                        found.append({
                            'id': f['id'], 'name': f['name'], 'kw': '가설건축물',
                            'rtitle': f['name'], 'reason': '가설건축물 축조신고 및 존치기간 연장 증빙',
                            'webViewLink': f.get('webViewLink', f"https://drive.google.com/file/d/{f['id']}/view"),
                            'createdTime': f.get('createdTime', ''),
                            'mimeType': f.get('mimeType', 'application/pdf'),
                            'folder_path': f"가설건축물 > {folder['name']}",
                            'snippet': "", 'matched_pages': [1]
                        })
    except Exception:
        pass
    return found

def sort_by_priority_patterns(files, patterns):
    """지정된 대표 서류가 항상 1번으로 자동 오픈되도록 우선순위 패턴 순서대로 정렬합니다."""
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
    """FSSC 22000 규정집에서 문서 코드(예: YS-품질-P-200) 기준 최신 개정본 1건만 남깁니다."""
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
    """전 구간 원클릭 카테고리에 대해 심사 직관성을 극대화한 우측 세부 탭과 1번 우선 정렬을 수행합니다."""
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
            elif sl in ("축산물가공업", "집유업", "우유류판매업", "축산물유통전문판매업") or "축산물판매업" == sl:
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
        t_prp_sorted = sorted(t_prp, key=lambda x: (extract_leading_num(x['name']), x['name']))
        return {
            "📋 선행요건 기준서 (1~12번)": t_prp_sorted,
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
    return {f"📄 {category_key} 관련 근거 및 최신 문서": sorted_default}

def execute_exact_match(display_keyword, folder_key=None, gw_keyword=None, priority_keywords=None, filter_folder_files=False):
    service = get_drive_service()
    if not service:
        return
    ensure_auto_db_loaded()

    gw_list = []
    if isinstance(gw_keyword, list):
        gw_list = [g for g in gw_keyword if g]
    elif isinstance(gw_keyword, str) and gw_keyword.strip():
        gw_list = [gw_keyword.strip()]

    st.session_state.update({
        "search_done": True, "search_mode": "exact",
        "search_keyword": display_keyword, "search_question": display_keyword,
        "target_folder_key": folder_key,
        "gw_keyword": gw_list[0] if gw_list else "",
        "gw_keywords_list": gw_list,
        "priority_keywords": priority_keywords or [], "last_file_id": "",
        "selected_doc_idx": 0, "selected_page_num": 1, "aux_files": []
    })

    db_list = st.session_state.auto_db
    matched_files = []
    aux_files = []
    seen_fids = set()

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
        folder_map = get_all_managed_folders_map(service)
        folder_keys_to_search = [folder_key] if isinstance(folder_key, str) else folder_key
        for f_key in folder_keys_to_search:
            if f_key in FLAT_FOLDER_DB and not FLAT_FOLDER_DB[f_key].startswith("folder_id_"):
                target_folders = get_target_folder_ids(service, FLAT_FOLDER_DB[f_key])
                for fid in target_folders:
                    page_token = None
                    while True:
                        res = service.files().list(
                            q=f"'{fid}' in parents and trashed = false", spaces='drive',
                            fields='nextPageToken, files(id, name, webViewLink, mimeType, createdTime)',
                            pageSize=1000, pageToken=page_token
                        ).execute()
                        for f in res.get('files', []):
                            if f['mimeType'] == 'application/vnd.google-apps.folder' or f['id'] in seen_fids:
                                continue
                            if is_blacklisted(f['name'], display_keyword):
                                continue
                            f_path = folder_map.get(fid, f_key)
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
                        page_token = res.get('nextPageToken')
                        if not page_token:
                            break

    # 인허가 조회 시 별도 경로의 '가설건축물' 폴더 파일 자동 병합
    if display_keyword == "인허가":
        for tf in get_temp_building_files():
            if tf['id'] not in seen_fids:
                seen_fids.add(tf['id'])
                matched_files.append(tf)

    st.session_state.found_files = matched_files
    st.session_state.aux_files = sorted(aux_files, key=lambda x: parse_doc_date_tuple(x['name']), reverse=True)

# ==========================================
# [4] 사이드바 (마스터 캐싱 및 전 구간 원클릭 핀셋 버튼)
# ==========================================
with st.sidebar:
    st.markdown("### 🔄 마스터 지식베이스 동기화")
    st.caption("최신 사내 규정 및 인증 현황을 AI 검증 엔진에 적재합니다. (1일 1회 권장)")
    
    if st.session_state.get("master_cache_name"):
        st.success("✅ 마스터 지식베이스가 활성화되어 있습니다.")
        
    if st.button("마스터 지식베이스 갱신 및 적재", use_container_width=True):
        drive_service = get_drive_service()
        ensure_auto_db_loaded()
        if not drive_service:
            st.error("구글 드라이브 API 인증에 실패하였습니다.")
        elif not st.session_state.auto_db:
            st.warning("⚠️ 마스터 DB 데이터가 비어 있습니다. 4번 탭에서 문서 스캔을 먼저 진행해 주십시오.")
        else:
            with st.spinner("마스터 DB 및 기준서 폴더의 최신 기준서·선행요건·인증서를 선별하여 메모리에 적재 중입니다..."):
                try:
                    uploaded_laws = []
                    target_pdfs = []
                    seen_fids = set()
                    
                    for row in reversed(st.session_state.auto_db):
                        kw = row.get("키워드", "")
                        fid = row.get("파일 ID", "")
                        fname = row.get("문서_실제제목") or row.get("파일명", "")
                        if not fid or fid in seen_fids:
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
                        st.info("ℹ️ 시스템 처리 용량 최적화를 위해 최신 핵심 기준서 및 인증서 45건을 우선 적재합니다.")
                    
                    if not target_pdfs:
                        st.warning("⚠️ 적재할 기준서 또는 인증서 문서가 없습니다.")
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
                            
                        st.success(f"✅ 핵심 기준서 및 인증 문서({len(target_pdfs)}건) 메모리 적재 완료 (12시간 유지)")
                except Exception as e:
                    st.error(f"지식베이스 적재 중 오류가 발생하였습니다: {e}")
                
    st.markdown("---")
    
    sidebar_tab1, sidebar_tab2 = st.tabs(["🎯 전산 심사방어", "🔍 딥 서치"])

    with sidebar_tab2:
        with st.form(key='search_form'):
            st.caption("전체 하위 폴더 및 PDF 본문 내 키워드를 정밀 탐색하여 문맥 요약과 음영 페이지를 표시합니다.")
            manual_query = st.text_input("검색어 입력:", placeholder="예: 사과, 조도, 과산화수소, 알러겐", label_visibility="collapsed")
            if st.form_submit_button("본문 정밀 검색 실행 🚀", use_container_width=True) and manual_query:
                execute_deep_search(manual_query)

    with sidebar_tab1:
        st.caption("전산 및 클라우드 기반으로 즉시 열람·증빙이 가능한 심사 대응 문서 카테고리입니다.")
        
        with st.expander("📁 1. 영업 인허가 및 각종 인증서", expanded=True):
            if st.button("영업신고/공장등록/가설건축물", use_container_width=True):
                execute_exact_match("인허가", "인허가 서류", "", [
                    "사업자등록", "공장등록", "건축물대장", "식품제조가공업", "축산물가공업", "집유업",
                    "수입식품영업", "식품소분업", "축산물판매업", "건강기능식품영업", "통신판매업", "방문판매업", "집단급식소", "화장품책임판매", "지하수개발허가", "가설건축물"
                ])
            if st.button("HACCP 및 FSSC 인증서", use_container_width=True):
                execute_exact_match("인증서", "인증서", "", [
                    "HACCP_가공두유", "HACCP_원액두유", "HACCP_유가공업", "HACCP_환자식",
                    "HACCP_과채주스", "HACCP_과채음료", "HACCP_혼합음료", "HACCP_유산균음료", "HACCP_커피", "HACCP_액상차",
                    "CHINA_HACCP", "FSSC22000", "FDA_FCE", "FDA_FFR"
                ])
            if st.button("K-MILK / 무항생제 / 유기농", use_container_width=True):
                execute_exact_match("특수 인증", "인증서", "", ["K-MILK", "무항생제", "유기가공식품"])

        with st.expander("📘 2. 사내 규정 및 절차 (매뉴얼)", expanded=True):
            if st.button("선행요건 / HACCP 기준서", use_container_width=True):
                execute_exact_match("기준서", ["선행요건", "기준서"], "", [])
            if st.button("FSSC 22000 기준서 (전사 규정)", use_container_width=True):
                execute_exact_match("FSSC 22000 기준서", "FSSC22000", "", [])
            if st.button("위생 / 해충 / 알러겐 절차", use_container_width=True):
                execute_exact_match("위생 절차", "선행요건", "", [
                    "위생관리기준서", "장갑관리기준서", "알러겐", "작업장기준서"
                ], filter_folder_files=True)
            if st.button("이물 / 식품보안 절차", use_container_width=True):
                execute_exact_match("보안 절차", ["선행요건", "FSSC22000"], "", [
                    "이물관리기준서", "식품보안", "식품사기", "P-210", "구매-P-300"
                ], filter_folder_files=True)
            if st.button("위기대응 및 회수 절차", use_container_width=True):
                execute_exact_match("회수 절차", ["선행요건", "FSSC22000"], "", [
                    "제품회수관리기준서", "위기관리규정", "비상사태", "부적합품관리규정", "시정조치", "고객불만"
                ], filter_folder_files=True)
        
        with st.expander("🧼 3. 위생·환경 평가 및 인력 점검"):
            if st.button("수질검사 성적서 / 저수조 청소", use_container_width=True):
                execute_exact_match("수질검사", ["수질검사", "물탱크청소"], ["용수 검사 성적서"], ["수질검사", "저수조청소"])
            if st.button("방역 관리 리포트 (GW)", use_container_width=True):
                execute_exact_match("방제 레포트", "방충방서 관련 서류", ["방역 관리 리포트"], [])
            if st.button("종사자 법정/보건증 및 수료증", use_container_width=True):
                execute_exact_match("보건증/교육", "교육수료증", ["위생교육"], ["보건증", "법정위생교육", "HACCP정기교육", "교육_"])
            if st.button("손 위생 및 낙하세균 (GW)", use_container_width=True):
                execute_exact_match(
                    "환경·위생 미생물 검사", "선행요건",
                    ["작업자 손 위생검사 결과", "낙하세균 검사 결과", "표면오염도 검사 결과", "압축공기 미생물검사 결과", "세척.소독제 농도 검증 결과"],
                    ["위생관리기준서", "작업장기준서"], filter_folder_files=True
                )
            if st.button("냉장/냉동 창고 온도 일지 (GW)", use_container_width=True):
                execute_exact_match(
                    "냉장·냉동 온도 모니터링", "선행요건",
                    ["냉장/냉동 창고 온도 모니터링 일지"],
                    ["냉장냉동설비관리기준서", "보관 및 운반"], filter_folder_files=True
                )
            
        with st.expander("⚙️ 4. CCP 공정 관리 및 설비 검증"):
            if st.button("공정관리 일보 (GW)", use_container_width=True):
                execute_exact_match(
                    "CCP 공정관리 일보", "기준서",
                    ["우유 포장 공정관리 일보", "발효유 포장 공정관리 일보", "음료류 일반검사 일보", "중국 수출 우유 제품검사 일보"],
                    ["HACCP PLAN", "제조공정설명서"], filter_folder_files=True
                )
            if st.button("상업적 무균테스트 (GW)", use_container_width=True):
                execute_exact_match(
                    "무균테스트 및 과산화수소 검증", "기준서",
                    ["상업적 무균테스트 결과 보고서", "테트라팩 과산화수소 잔류여부 검증 결과", "콤비팩 과산화수소 잔류여부 검증 결과", "카톤팩 과산화수소 잔류여부 검증 결과"],
                    ["HACCP PLAN"], filter_folder_files=True
                )
            if st.button("계측기 검·교정 이력 (GW)", use_container_width=True):
                execute_exact_match(
                    "계측기 및 자력기기 검·교정", "선행요건",
                    ["측정기기 공인기관 검·교정 결과", "현장 온도센서 공인기관 검·교정 결과", "유량계 공인기관 교정 결과", "자체 측정기기 검·교정결과", "자력기기 점검 결과"],
                    ["검사관리기준서", "제조시설관리기준서"], filter_folder_files=True
                )
            if st.button("설비 유지보수 이력", use_container_width=True):
                execute_exact_match(
                    "설비이력", ["설비이력", "선행요건", "FSSC22000"], "",
                    ["설비", "제조시설관리기준서", "생산설비관리규정", "부대시설관리규정"]
                )
            
        with st.expander("📦 5. 원부자재 관리 및 사후 추적성"):
            if st.button("입고 검수서 (GW)", use_container_width=True):
                execute_exact_match(
                    "원부자재 입고 검수", ["선행요건", "FSSC22000"],
                    ["부자재 입고 검수서"],
                    ["검사관리기준서", "협력업체관리규정", "구매업무규정"], filter_folder_files=True
                )
            if st.button("자가품질 및 제품검사 (GW)", use_container_width=True):
                execute_exact_match(
                    "자가품질 및 알러겐·미생물 검증", "선행요건",
                    ["자가품질검사 검사결과", "알러겐 및 미생물 검증 결과", "병원성 미생물 배지 수불부", "음료류 일반검사 일보"],
                    ["검사관리기준서", "알러겐 관리기준서"], filter_folder_files=True
                )
            if st.button("클레임 현황 및 시정조치 (GW)", use_container_width=True):
                execute_exact_match(
                    "클레임 및 부적합 시정조치", "FSSC22000",
                    ["소비자 클레임 현황(제조단계, 공장)", "대리점 클레임 현황", "품질(제품, 원·부자재) 부적합 현황 보고", "문제점 개선 대책 결과 보고"],
                    ["고객불만처리규정", "부적합품관리규정", "시정조치"], filter_folder_files=True
                )
            if st.button("모의회수 기록", use_container_width=True):
                execute_exact_match("모의회수", ["모의회수", "선행요건"], ["모의회수"], ["모의회수", "추적성", "제품회수관리기준서"])
            if st.button("PL보험 및 영업배상책임보험", use_container_width=True):
                execute_exact_match("책임보험", "PL보험가입증명서", "", ["책임보험"])

# ==========================================
# [5] 메인 UI 탭 구성
# ==========================================
st.markdown("## 🛡️ HACCP Agent 통합 포털")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🤖 원클릭 뷰어 & 스니펫", "📁 탐색기", "🚨 탑다운 대시보드", "⚙️ DB 자동화(관리자)", "💬 HACCP 챗봇"])

# ----------------- TAB 1: 뷰어 & 스니펫 (우측 세부탭 + 다중 GW 핀셋 + 최신본 1건 직행 + 음영 뷰어) -----------------
with tab1:
    if st.session_state.search_done:
        keyword = st.session_state.search_keyword
        
        # 상단 그룹웨어(전자결재) 다중 양식 핀셋 바로가기 패널
        gw_items = st.session_state.get("gw_keywords_list", [])
        if not gw_items and st.session_state.get("gw_keyword"):
            gw_items = [st.session_state.gw_keyword]
            
        if gw_items:
            st.info(f"💻 **전자결재(그룹웨어) 실시간 기록 증빙 바로가기** — 클릭 시 해당 결재 문서함이 새 창에서 즉시 열립니다.")
            gw_cols = st.columns(min(len(gw_items), 3))
            for g_idx, g_kw in enumerate(gw_items):
                g_url = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?keyword={urllib.parse.quote(g_kw)}"
                with gw_cols[g_idx % len(gw_cols)]:
                    st.link_button(f"👉 [{g_kw}] 열기", g_url, type="primary", use_container_width=True)
            st.markdown("---")

        raw_files = [f for f in st.session_state.found_files if not is_blacklisted(f['name'], keyword)]
        top_file = None
        
        if not raw_files:
            if not gw_items:
                st.warning(f"⚠️ 조회 항목('{keyword}')과 일치하는 클라우드 문서가 없습니다. 검색어를 변경하거나 다른 카테고리를 선택해 주십시오.")
        else:
            # [모드 A] 딥 서치: 식약처 식품공전 스타일 검색 결과 리스트
            if st.session_state.search_mode == "deep":
                st.markdown(
                    f"<div class='mfds-banner'>검색어 <span style='color:#1d4ed8;'>‘{keyword}’</span>에 대한 총 <span style='color:#1d4ed8;'>{len(raw_files)}건</span>의 검증된 검색결과를 찾았습니다.</div>",
                    unsafe_allow_html=True
                )
                
                with st.expander(f"📋 사내 기준서 및 문서 검색 결과 목록 (1~{len(raw_files)} / 총 {len(raw_files)}건) - 클릭 시 해당 음영 페이지로 즉시 이동", expanded=True):
                    for idx, f in enumerate(raw_files):
                        c_info, c_btn1, c_btn2 = st.columns([7.2, 1.6, 1.2])
                        folder_label = f.get('folder_path', '사내 문서함')
                        m_pages = f.get('matched_pages', [1])
                        first_p = m_pages[0] if m_pages else 1
                        snip_raw = f.get('snippet') or f"문서명: {f['name']}"
                        
                        snip_html = snip_raw
                        for tk in [t for t in re.split(r'\s+', keyword) if len(t) >= 1]:
                            snip_html = re.sub(f"({re.escape(tk)})", r"<span class='mfds-key'>\1</span>", snip_html, flags=re.IGNORECASE)
                            
                        with c_info:
                            st.markdown(
                                f"<div class='mfds-result-item'>"
                                f"<div class='mfds-title'>• {idx + 1}. {f['name']} <span class='mfds-path'>[{folder_label}] (매칭 페이지: p.{', p.'.join(map(str, m_pages[:5]))})</span></div>"
                                f"<div class='mfds-snippet'>{snip_html}</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        with c_btn1:
                            st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
                            if st.button(f"📄 본문 음영 열람 (p.{first_p})", key=f"deep_sel_{idx}", use_container_width=True):
                                st.session_state.selected_doc_idx = idx
                                st.session_state.selected_page_num = first_p
                                st.session_state.last_file_id = ""
                        with c_btn2:
                            st.markdown("<div style='margin-top:18px;'></div>", unsafe_allow_html=True)
                            st.link_button("새창으로 열기", f.get('webViewLink', f"https://drive.google.com/file/d/{f['id']}/view"), use_container_width=True)
                st.markdown("---")
                
                sel_idx = min(st.session_state.selected_doc_idx, len(raw_files) - 1)
                top_file = raw_files[sel_idx]
                
            # [모드 B] 원클릭 심사방어: 우측 화면 세부 카테고리 탭(Sub-tab) 분할 + 1번 대표 문서 즉시 오픈
            else:
                subtab_map = get_subtabs_for_category(keyword, raw_files)
                non_empty_tabs = {k: v for k, v in subtab_map.items() if v}
                if not non_empty_tabs:
                    non_empty_tabs = subtab_map
                    
                tab_labels = list(non_empty_tabs.keys())
                if len(tab_labels) > 1:
                    chosen_subtab = st.radio(
                        "📂 세부 증빙 분류 선택",
                        tab_labels,
                        horizontal=True,
                        key=f"subtab_radio_{keyword}"
                    )
                else:
                    chosen_subtab = tab_labels[0]
                    
                active_list = non_empty_tabs.get(chosen_subtab, [])
                if not active_list:
                    st.warning(f"⚠️ '{chosen_subtab}' 항목에 해당하는 최신 파일이 아직 등록되지 않았습니다.")
                else:
                    opts = {f"{i + 1}. {f['name']}": f for i, f in enumerate(active_list)}
                    if len(active_list) > 1:
                        sel_name = st.selectbox(
                            f"✅ [{chosen_subtab}] 증빙 서류 선택 ({len(active_list)}종)",
                            list(opts.keys()),
                            key=f"doc_select_{keyword}_{chosen_subtab}"
                        )
                    else:
                        sel_name = list(opts.keys())[0]
                        st.success(f"⚡ **[{chosen_subtab}] 공식 증빙 자동 매칭:** `{opts[sel_name]['name']}`")
                    top_file = opts[sel_name]
                    
                if st.session_state.aux_files:
                    with st.expander(f"📎 부속 참고 자료 (청소사진·관공서 서식·간이검사 등 {len(st.session_state.aux_files)}건 별도 보관)", expanded=False):
                        aux_df = [{"No": i + 1, "파일명": af['name'], "열람": af['webViewLink']} for i, af in enumerate(st.session_state.aux_files)]
                        st.dataframe(aux_df, hide_index=True, use_container_width=True, column_config={"열람": st.column_config.LinkColumn(display_text="새 창 열기")})

            # 선택된 문서 뷰어 및 AI 브리핑 실행 (탭/문서 변경 시 잔상 없이 즉시 갱신)
            if top_file is not None:
                cur_view_url = top_file.get('webViewLink', f"https://drive.google.com/file/d/{top_file['id']}/view")
                cur_preview_url = f"https://drive.google.com/file/d/{top_file['id']}/preview"
                st.session_state.view_url = cur_view_url
                st.session_state.preview_url = cur_preview_url
                
                if st.session_state.last_file_id != top_file['id']:
                    m_pages = top_file.get('matched_pages', [1])
                    st.session_state.selected_page_num = m_pages[0] if m_pages else 1
                    
                    with st.spinner("🤖 문서 적합성 및 관련 규정 교차 분석 중..."):
                        try:
                            file_bytes = get_cached_file_bytes(top_file['id'])
                            file_ext = ".pdf" if "pdf" in top_file.get('mimeType', '').lower() else ".jpg"
                            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_doc:
                                tmp_doc.write(file_bytes)
                                tmp_doc_path = tmp_doc.name
                            
                            gemini_file = genai.upload_file(path=tmp_doc_path)
                            cache_name = st.session_state.get("master_cache_name")
                            
                            prompt = f"""다음 조회 항목에 대하여 외부 심사원 및 경영진 보고에 적합한 격식 있고 정중한 비즈니스 경어체(~합니다, ~입니다)로 브리핑을 작성하십시오: {st.session_state.search_question}
                            1. 📋 [문서 적합성 확인]: 현재 열람 중인 문서가 '{st.session_state.search_keyword}' 관련 증빙 서류에 부합하는지 문서 제목, 발급 기관 및 본문 내용을 대조하여 1문장으로 명확히 기술하십시오.
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
                                
                            st.session_state.final_briefing = res.text
                        except Exception as e:
                            st.session_state.final_briefing = f"⚠️ 분석 오류가 발생하였습니다. (API 연결 상태 확인 요망)\n상세 내역: {e}"
                        finally:
                            try:
                                genai.delete_file(gemini_file.name)
                                os.remove(tmp_doc_path)
                            except:
                                pass
                    st.session_state.last_file_id = top_file['id']

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"#### 📄 {top_file['name']}")
                    st.markdown(f"🔗 **[원본 문서 새 창에서 열기]({cur_view_url})**")
                    
                    if PYMUPDF_INSTALLED and "pdf" in top_file.get('mimeType', 'pdf').lower():
                        default_v_idx = 0 if st.session_state.search_mode == "deep" else 1
                        viewer_mode = st.radio(
                            "뷰어 모드 선택",
                            ["🖍️ 검색어 본문 음영(하이라이트) 페이지 뷰어", "🌐 구글 드라이브 원본 스크롤 뷰어"],
                            index=default_v_idx, horizontal=True, label_visibility="collapsed",
                            key=f"vmode_{top_file['id']}"
                        )
                        if "음영" in viewer_mode:
                            f_bytes = get_cached_file_bytes(top_file['id'])
                            hl_kw = keyword if st.session_state.search_mode == "deep" else ""
                            img_bytes, total_p, m_pages = render_highlighted_pdf_page(
                                f_bytes, st.session_state.selected_page_num, hl_kw
                            )
                            if img_bytes:
                                nav1, nav2, nav3, nav4 = st.columns([2, 2, 3, 3])
                                with nav1:
                                    if st.button("◀ 이전 페이지", key=f"prev_{top_file['id']}", use_container_width=True) and st.session_state.selected_page_num > 1:
                                        st.session_state.selected_page_num -= 1
                                        st.rerun()
                                with nav2:
                                    if st.button("다음 페이지 ▶", key=f"next_{top_file['id']}", use_container_width=True) and st.session_state.selected_page_num < total_p:
                                        st.session_state.selected_page_num += 1
                                        st.rerun()
                                with nav3:
                                    new_p = st.number_input("페이지 이동", min_value=1, max_value=max(1, total_p), value=min(st.session_state.selected_page_num, max(1, total_p)), label_visibility="collapsed", key=f"pnum_{top_file['id']}")
                                    if new_p != st.session_state.selected_page_num:
                                        st.session_state.selected_page_num = new_p
                                        st.rerun()
                                with nav4:
                                    if m_pages:
                                        st.caption(f"🖍️ 검색어 포함 페이지: p.{', p.'.join(map(str, m_pages[:8]))} (총 {total_p}p)")
                                    else:
                                        st.caption(f"현재 {st.session_state.selected_page_num} / {total_p} 페이지")
                                st.image(img_bytes, use_container_width=True)
                            else:
                                st.components.v1.iframe(cur_preview_url, height=600, scrolling=True)
                        else:
                            st.components.v1.iframe(cur_preview_url, height=600, scrolling=True)
                    else:
                        st.components.v1.iframe(cur_preview_url, height=600, scrolling=True)
                        
                with col2:
                    st.write("📋 **AI 문서 검토 및 규정 연계 브리핑:**")
                    if "오류" in st.session_state.final_briefing:
                        st.error(st.session_state.final_briefing)
                    else:
                        st.success(st.session_state.final_briefing)

# ----------------- TAB 2: 수동 탐색 -----------------
with tab2:
    st.markdown("### 📁 공장 심사 서류 다이렉트 탐색기")
    
    explore_options = list(FLAT_FOLDER_DB.keys()) + ["가설건축물 (별도 폴더 자동탐색)"]
    col_major, col_minor = st.columns(2)
    with col_major:
        selected_major = st.selectbox("📂 대분류 선택", explore_options)

    if st.button(f"'{selected_major}' 전체 문서 호출", type="primary"):
        if selected_major == "가설건축물 (별도 폴더 자동탐색)":
            tb_files = get_temp_building_files()
            if not tb_files:
                st.warning("가설건축물 폴더 내 문서를 찾지 못했습니다.")
            else:
                display_data = [
                    {"No": idx, "파일명": f.get('name'), "생성일자": f.get('createdTime', '').split('T')[0] if f.get('createdTime') else '-', "서류 열람": f.get('webViewLink', '')}
                    for idx, f in enumerate(tb_files, 1)
                ]
                st.dataframe(display_data, hide_index=True, use_container_width=True, column_config={"서류 열람": st.column_config.LinkColumn(display_text="뷰어 열기")})
        else:
            target_folder_id = FLAT_FOLDER_DB[selected_major]
            if target_folder_id.startswith("folder_id_"):
                st.warning(f"⚠️ '{selected_major}' 폴더의 구글 드라이브 경로가 설정되지 않았습니다.")
            else:
                drive_service = get_drive_service()
                if drive_service:
                    with st.spinner("폴더 내 문서 목록을 조회 중입니다..."):
                        try:
                            t_folders = get_target_folder_ids(drive_service, target_folder_id)
                            all_disp = []
                            for fid in t_folders:
                                pt = None
                                while True:
                                    results = drive_service.files().list(
                                        q=f"'{fid}' in parents and trashed = false", spaces='drive',
                                        fields='nextPageToken, files(id, name, webViewLink, createdTime, mimeType)',
                                        orderBy='createdTime desc', pageSize=1000, pageToken=pt
                                    ).execute()
                                    for f in results.get('files', []):
                                        if f['mimeType'] != 'application/vnd.google-apps.folder':
                                            all_disp.append(f)
                                    pt = results.get('nextPageToken')
                                    if not pt:
                                        break

                            if not all_disp:
                                st.warning("해당 폴더에 등록된 문서가 없습니다.")
                            else:
                                display_data = []
                                for idx, f in enumerate(all_disp, 1):
                                    raw_date = f.get('createdTime', '')
                                    clean_date = raw_date.split('T')[0] if raw_date else '날짜 없음'
                                    display_data.append({"No": idx, "파일명": f.get('name'), "생성일자": clean_date, "서류 열람": f.get('webViewLink', '')})
                                st.dataframe(
                                    display_data, hide_index=True, use_container_width=True,
                                    column_config={"서류 열람": st.column_config.LinkColumn(display_text="뷰어 열기")}
                                )
                        except Exception as e:
                            st.error(f"오류: {e}")

# ----------------- TAB 3: 대시보드 (클릭형 상태 필터 버튼 + 가설건축물/교육/수질/보험 정밀 추적) -----------------
with tab3:
    st.markdown("### 🚨 실시간 법정 서류 및 인증 유효기간 대시보드")
    st.caption("상단의 상태별 건수 버튼을 클릭하면 아래에 해당 서류 목록이 즉시 펼쳐지며, 우측 '원본 열기'를 통해 문서를 바로 확인할 수 있습니다.")
    
    ensure_auto_db_loaded()
    supplement_drive_files = get_drive_supplement_files()
    temp_bldg_files = get_temp_building_files()
    today = datetime.date.today()

    def register_dash_candidate(dash_map, norm_kw, entry_dict, score_tuple):
        if norm_kw not in dash_map or score_tuple > dash_map[norm_kw]["score"]:
            dash_map[norm_kw] = {"entry": entry_dict, "score": score_tuple}

    latest_dash_dict = {}
    
    # 1단계: 구글 시트 마스터 DB 정규화 적재
    for row in st.session_state.auto_db:
        kw = str(row.get("키워드", "")).strip()
        fname = str(row.get("파일명", "")).strip()
        rtitle = str(row.get("문서_실제제목", "")).strip()
        reason = str(row.get("분류근거", "")).strip()
        if not kw or kw in ("PASS", "기타", "매뉴얼", "일반수료증"):
            continue
        if is_pest_vendor_doc(row):
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

    # 2단계: 드라이브 내 미스캔 최신 파일 보완 적재
    for f in supplement_drive_files:
        fn = f.get("name", "")
        fp = f.get("folder_path", "")
        if is_pest_vendor_doc(fn, fp) or is_blacklisted(fn):
            continue
        dt_t = parse_doc_date_tuple(fn, f.get("createdTime", ""))
        iso_issue = format_iso_from_tuple(dt_t)
        
        inferred_kw = None
        inferred_exp = ""
        inferred_disp = ""
        inferred_cyc = "12"
        
        if "인허가" in fp and "사업자등록" in fn and "연세유업" in fn:
            inferred_kw = "사업자등록"
            inferred_exp = "영구"
            inferred_cyc = "0"
        elif "인증서" in fp and ("CHINA" in fn.upper() or "延世" in fn or "主证" in fn):
            inferred_kw = "CHINA_HACCP"
            m_exp = re.search(r'20[12]\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\s*[~\-]\s*(20[23]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', fn)
            inferred_exp = f"{m_exp.group(1)}-{m_exp.group(2)}-{m_exp.group(3)}" if m_exp else ""
        elif "모의회수" in fp or "모의회수" in fn:
            inferred_kw = "모의회수"
        elif ("물탱크청소" in fp or "저수조" in fn) and any(x in fn for x in ["필증", "Report", "결과"]):
            if not any(ax in fn for ax in ["사진", "서식", "간이", "기준"]):
                inferred_kw = "저수조청소"
                inferred_cyc = "6"
        elif "수질검사" in fp and not any(ax in fn for ax in ["사진", "서식", "간이", "기준"]):
            if "노로" in fn:
                inferred_kw = "수질검사_노로"
            elif any(w in f"{fn} {fp}" for w in ["먹는물", "상수도", "수돗물"]):
                inferred_kw = "수질검사_먹는물"
            elif "성적서" in fn:
                inferred_kw = "수질검사_지하수"
                inferred_cyc = "6"
        elif "교육수료증" in fp:
            norm_k, disp_l, cyc_m = normalize_education_key(fn)
            if norm_k:
                inferred_kw = norm_k
                inferred_disp = disp_l
                inferred_cyc = str(cyc_m)
                
        if inferred_kw:
            sup_entry = {
                "키워드": inferred_kw, "파일명": fn, "문서_실제제목": inferred_disp or fn,
                "발급일": iso_issue, "만료일": inferred_exp, "주기(개월)": inferred_cyc,
                "개정번호": "-", "파일 ID": f["id"],
                "뷰어 링크": f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view"),
                "_disp_title": inferred_disp
            }
            register_dash_candidate(latest_dash_dict, inferred_kw, sup_entry, dt_t)

    # 3단계: 별도 경로 '가설건축물' 동별 필증 및 존치기간 만료일 자동 반영
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
            return issue_clean, "영구", "-", "✅ 영구 (갱신 불필요)", 99999
            
        expire_date = None
        if exp_raw and exp_raw not in ("미상", "없음", "해당없음", "-"):
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
            return issue_clean, "확인 필요", "-", "⚠️ 날짜 확인 필요", 0
            
        d_day = (expire_date - today).days
        exp_fmt = expire_date.strftime("%Y-%m-%d")
        if d_day < 0:
            status_txt = "🚨 기간 경과 (즉시 갱신)"
        elif d_day <= 30:
            status_txt = "⚠️ 갱신 임박 (30일 이내)"
        else:
            status_txt = "🟢 정상"
        return issue_clean, exp_fmt, str(d_day), status_txt, d_day

    dashboard_data = []
    processed_keys = set()
    
    for key, meta in MASTER_DOC_REQUIREMENTS.items():
        processed_keys.add(key)
        cyc = int(meta["주기"])
        gw_form = meta.get("gw", "")
        
        if gw_form and key not in db_dict:
            gw_link = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?keyword={urllib.parse.quote(gw_form)}"
            dashboard_data.append({
                "구분(키워드)": key, "서류명(마스터)": meta["표시명"], "법정주기(개월)": cyc,
                "스캔된 파일명": f"[그룹웨어 전자결재] {gw_form}", "발급일": "상시결재", "만료일": "월간점검",
                "D-Day": "-", "상태": "🟢 정상 (그룹웨어 관리)", "원본 열람": gw_link, "_d_num": 99999
            })
            continue
            
        if key in db_dict:
            doc = db_dict[key]
            iss_c, exp_c, d_str, st_txt, d_num = compute_expiry_and_status(doc, cyc, is_edu=False)
            dashboard_data.append({
                "구분(키워드)": key, "서류명(마스터)": meta["표시명"], "법정주기(개월)": cyc,
                "스캔된 파일명": doc.get("파일명") or doc.get("문서_실제제목", ""),
                "발급일": iss_c, "만료일": exp_c, "D-Day": d_str, "상태": st_txt,
                "원본 열람": doc.get("뷰어 링크", ""), "_d_num": d_num
            })
        else:
            dashboard_data.append({
                "구분(키워드)": key, "서류명(마스터)": meta["표시명"], "법정주기(개월)": cyc,
                "스캔된 파일명": "-", "발급일": "-", "만료일": "-", "D-Day": "-",
                "상태": "🚨 누락 (파일 없음)", "원본 열람": "", "_d_num": -99999
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
                "구분(키워드)": key, "서류명(마스터)": disp_label, "법정주기(개월)": cyc,
                "스캔된 파일명": doc.get("파일명", ""), "발급일": iss_c, "만료일": exp_c,
                "D-Day": d_str, "상태": st_txt, "원본 열람": doc.get("뷰어 링크", ""), "_d_num": d_num
            })

    df_dashboard = pd.DataFrame(dashboard_data)
    
    if not df_dashboard.empty:
        mask_exp = df_dashboard["상태"].str.contains("경과|누락|확인 필요", na=False)
        mask_30 = (df_dashboard["_d_num"] >= 0) & (df_dashboard["_d_num"] <= 30)
        mask_90 = (df_dashboard["_d_num"] >= 0) & (df_dashboard["_d_num"] <= 90)
        mask_180 = (df_dashboard["_d_num"] >= 0) & (df_dashboard["_d_num"] <= 180)
        mask_ok = df_dashboard["상태"].str.contains("정상|영구", na=False)

        b_cols = st.columns(6)
        if b_cols[0].button(f"📋 전체 서류\n({len(df_dashboard)}건)", use_container_width=True):
            st.session_state.dash_status_filter = "전체"
        if b_cols[1].button(f"🚨 기한경과·미등록\n({int(mask_exp.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "기한경과_미등록"
        if b_cols[2].button(f"⚠️ 30일 내 만료\n({int(mask_30.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "30일"
        if b_cols[3].button(f"📅 3개월 내 도래\n({int(mask_90.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "90일"
        if b_cols[4].button(f"🗓️ 6개월 내 도래\n({int(mask_180.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "180일"
        if b_cols[5].button(f"✅ 정상·영구 서류\n({int(mask_ok.sum())}건)", use_container_width=True):
            st.session_state.dash_status_filter = "정상_영구"

        def style_status(val):
            if "누락" in str(val): return 'color: white; background-color: #000000; font-weight:bold'
            if "경과" in str(val): return 'color: white; background-color: #ef4444; font-weight:bold'
            if "임박" in str(val) or "확인" in str(val): return 'color: black; background-color: #fbbf24; font-weight:bold'
            if "정상" in str(val): return 'color: white; background-color: #22c55e'
            if "영구" in str(val): return 'color: white; background-color: #3b82f6'
            return ''

        disp_cols = ["구분(키워드)", "서류명(마스터)", "법정주기(개월)", "스캔된 파일명", "발급일", "만료일", "D-Day", "상태", "원본 열람"]
        
        cur_f = st.session_state.dash_status_filter
        filter_map = {
            "전체": ("📋 전체 관리 서류 목록", df_dashboard),
            "기한경과_미등록": ("🚨 기한 경과 및 미등록 서류 (즉시 조치 대상)", df_dashboard[mask_exp]),
            "30일": ("⚠️ 30일 이내 만료 임박 서류", df_dashboard[mask_30].sort_values("_d_num")),
            "90일": ("📅 3개월(90일) 이내 만료 도래 서류", df_dashboard[mask_90].sort_values("_d_num")),
            "180일": ("🗓️ 6개월(180일) 이내 만료 도래 서류", df_dashboard[mask_180].sort_values("_d_num")),
            "정상_영구": ("✅ 정상 및 영구 보존 서류", df_dashboard[mask_ok])
        }
        f_title, f_df = filter_map.get(cur_f, filter_map["전체"])
        
        st.markdown(f"#### {f_title} — 총 `{len(f_df)}건`")
        if f_df.empty:
            st.success("🎉 해당 조건에 속하는 대상 서류가 0건입니다.")
        else:
            st.dataframe(
                f_df[disp_cols].style.map(style_status, subset=['상태']),
                hide_index=True, use_container_width=True,
                column_config={"원본 열람": st.column_config.LinkColumn(display_text="원본 열기")}
            )

        st.markdown("---")
        st.markdown("#### 📂 카테고리별 전체 관리 대장")
        
        edu_insp_mask = df_dashboard["구분(키워드)"].apply(lambda x: x.startswith(("수질검사_", "저수조", "방충방서_", "모의회수", "보건증_", "법정위생교육_", "HACCP정기교육", "HACCP팀장")))
        df_edu_insp = df_dashboard[edu_insp_mask]
        
        cert_mask = df_dashboard["구분(키워드)"].apply(lambda x: x.startswith(("HACCP_", "CHINA_HACCP", "FSSC", "K-MILK", "무항생제", "유기가공", "FDA_", "책임보험")))
        df_cert = df_dashboard[cert_mask]
        
        handled_12 = set(df_edu_insp["구분(키워드)"]).union(set(df_cert["구분(키워드)"]))
        df_license = df_dashboard[~df_dashboard["구분(키워드)"].isin(handled_12)]
        
        with st.expander("📅 1. 정기 검사 및 법정 의무 교육 (주기별 갱신 대상)", expanded=False):
            st.dataframe(df_edu_insp[disp_cols].style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True, column_config={"원본 열람": st.column_config.LinkColumn(display_text="원본 열기")})
            
        with st.expander("🥇 2. HACCP 및 주요 식품안전 시스템 인증서 / 책임보험", expanded=False):
            st.dataframe(df_cert[disp_cols].style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True, column_config={"원본 열람": st.column_config.LinkColumn(display_text="원본 열기")})
            
        with st.expander("📁 3. 영업 인허가 및 시설·가설건축물 등록증", expanded=False):
            st.dataframe(df_license[disp_cols].style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True, column_config={"원본 열람": st.column_config.LinkColumn(display_text="원본 열기")})

# ----------------- TAB 4: AI 마스터 DB -----------------
with tab4:
    st.markdown("### ⚙️ 문서 AI 일괄 스캔 및 DB 동기화 (관리자용)")
    st.markdown("유효기간 및 개정 관리가 필요한 지정 폴더의 문서를 AI가 정밀 스캔하여 마스터 DB에 자동 업데이트합니다.")
    
    if not PYMUPDF_INSTALLED:
        st.error("🚨 딥 서치(본문 스니펫 미리보기) 기능을 위해 Github의 `requirements.txt`에 `PyMuPDF`를 추가해 주십시오.")

    scan_options = list(FLAT_FOLDER_DB.keys()) + ["가설건축물"]
    default_targets = ["인허가 서류", "가설건축물", "인증서", "수질검사", "물탱크청소", "교육수료증", "모의회수", "PL보험가입증명서", "기준서", "선행요건", "FSSC22000"]
    selected_targets = st.multiselect(
        "📌 스캔할 카테고리 선택 (관리 대상 폴더 선택)",
        options=scan_options,
        default=default_targets
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 1단계: 대상 파일 조회 (스캔 전 확인)", type="secondary", use_container_width=True):
            if not selected_targets:
                st.error("스캔할 카테고리를 하나 이상 선택해 주십시오.")
            else:
                service = get_drive_service()
                files_to_scan = []
                
                with st.spinner("선택된 폴더 및 하위 폴더의 문서들을 검색 중입니다..."):
                    for cat in selected_targets:
                        if cat == "가설건축물":
                            for tf in get_temp_building_files():
                                files_to_scan.append(tf)
                            continue
                        tf_id = FLAT_FOLDER_DB[cat]
                        if tf_id.startswith("folder_id_"):
                            continue
                        
                        t_folders = get_target_folder_ids(service, tf_id)
                        for folder_id in t_folders:
                            page_token = None
                            while True:
                                res = service.files().list(
                                    q=f"'{folder_id}' in parents and trashed = false",
                                    fields='nextPageToken, files(id, name, mimeType, webViewLink)',
                                    pageSize=1000, pageToken=page_token
                                ).execute()
                                for f in res.get('files', []):
                                    if f['mimeType'] != 'application/vnd.google-apps.folder':
                                        files_to_scan.append(f)
                                page_token = res.get('nextPageToken')
                                if not page_token:
                                    break
                    
                valid_files = [f for f in files_to_scan if "pdf" in f['mimeType'].lower() or "image" in f['mimeType'].lower()]
                
                st.info(f"📂 총 **{len(files_to_scan)}개**의 파일이 확인되었습니다.")
                if len(valid_files) == 0:
                    st.error("🚨 스캔 가능한 PDF 또는 이미지 파일이 없습니다. (문서 포맷 확인 요망)")
                else:
                    st.success(f"✅ AI 스캔 대상 문서(PDF/이미지)는 총 **{len(valid_files)}개**입니다.")
                st.session_state.files_to_scan = valid_files

    with col2:
        if st.button("🔄 2단계: 초정밀 전체 스캔 및 시트 저장 실행", type="primary", use_container_width=True):
            if "files_to_scan" not in st.session_state or not st.session_state.files_to_scan:
                st.warning("먼저 '1단계: 대상 파일 조회' 버튼을 클릭해 주십시오.")
            else:
                service = get_drive_service()
                sheet_service = get_sheets_service()
                
                progress_bar = st.progress(0)
                log_box = st.empty()
                log_history = []
                
                def update_log(msg):
                    log_history.append(msg)
                    display_text = "\n".join(log_history[-15:])
                    log_box.code(display_text, language="text")

                error_log = []
                
                scanned_ids = set()
                if sheet_service and SHEET_ID:
                    try:
                        sc_res = sheet_service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="SCANNED!A:A").execute()
                        sc_vals = sc_res.get('values', [])
                        for row in sc_vals:
                            if row:
                                scanned_ids.add(row[0])
                    except Exception:
                        update_log("⚠️ SCANNED 시트를 찾을 수 없거나 비어 있습니다. 초기 스캔을 시작합니다.")
                
                files_to_process = [f for f in st.session_state.files_to_scan if f['id'] not in scanned_ids]
                skipped_count = len(st.session_state.files_to_scan) - len(files_to_process)
                
                if skipped_count > 0:
                    update_log(f"⏭️ 기스캔 완료 문서 {skipped_count}건을 제외하고 신규 {len(files_to_process)}건을 분석합니다.")
                
                total = len(files_to_process)
                if total == 0:
                    update_log("✅ 모든 문서가 이미 최신 상태로 스캔 완료되었습니다.")
                    st.success("새로 추가된 문서가 없어 스캔을 종료합니다.")
                else:
                    model = genai.GenerativeModel(MODEL_NAME)
                    
                    prompt = """본 문서의 핵심 메타데이터를 정밀하게 추출하십시오. (공식 심사 대응용 무결성 데이터)
                    
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
                    
                    allowed_dynamic_prefixes = ("가설건축물_", "수질검사_", "보건증_", "법정위생교육_", "HACCP교육_", "HACCP팀장")
                    
                    for i, f in enumerate(files_to_process):
                        update_log(f"⏳ [{i+1}/{total}] 문서 정밀 분석 중: {f['name']}")
                        progress_bar.progress((i + 1) / total)
                        
                        fid = f['id']
                        
                        try:
                            mime = f['mimeType'].lower()
                            if "pdf" in mime: ext = ".pdf"
                            elif "png" in mime: ext = ".png"
                            elif "jpeg" in mime or "jpg" in mime: ext = ".jpg"
                            else:
                                update_log(f"⏭️ [{i+1}/{total}] 미지원 포맷 제외: {f['name']}")
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
                                if wait_time % 15 == 0:
                                    update_log(f"⏳ [{i+1}/{total}] 문서 데이터 처리 대기 중... ({wait_time}초 경과)")
                                up_file = genai.get_file(up_file.name)
                                
                            if up_file.state.name == "FAILED":
                                raise Exception("문서 파일 판독 불가 (파일 손상 확인 요망)")
                            elif up_file.state.name == "PROCESSING":
                                raise Exception("서버 응답 시간 초과 (5분 초과)")
                            
                            time.sleep(3.5)
                            ai_res = model.generate_content([up_file, prompt])
                            
                            text_res = ai_res.text.strip()
                            json_match = re.search(r'\{.*\}', text_res, re.DOTALL)
                            if not json_match:
                                raise Exception("AI 응답 데이터 형식 오류")
                            
                            parsed = json.loads(json_match.group(0))
                            kw = parsed.get("키워드", "")
                            
                            if kw not in ("PASS", "기타", "매뉴얼", "일반수료증", "HACCP정기교육", "HACCP팀장및경영자교육") and kw not in MASTER_DOC_REQUIREMENTS and not kw.startswith(allowed_dynamic_prefixes):
                                update_log(f"🛡️ 미지정 키워드 '기타' 분류 전환: {kw}")
                                kw = "기타"
                                parsed["키워드"] = kw
                            
                            if kw != "PASS":
                                cycle = str(MASTER_DOC_REQUIREMENTS.get(kw, {}).get("주기", 0))
                                if kw.startswith("법정위생교육_") or kw == "HACCP정기교육":
                                    cycle = "12"
                                    
                                new_row = [
                                    kw, f['name'], parsed.get("문서_실제제목", ""), parsed.get("발급일", ""), parsed.get("만료일", ""),
                                    cycle, parsed.get("개정번호", "-"), parsed.get("분류근거", ""), fid, f['webViewLink']
                                ]
                                
                                if sheet_service and SHEET_ID:
                                    try:
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
                                        if not st.session_state.auto_db:
                                            st.session_state.auto_db = []
                                        st.session_state.auto_db.append(row_dict)
                                        
                                    except Exception as e:
                                        update_log(f"⚠️ 시트 기록 오류: {e}")
                                        
                            update_log(f"✅ [{i+1}/{total}] 메타데이터 추출 및 DB 반영 완료 ({kw})")
                            
                            genai.delete_file(up_file.name)
                            os.remove(tmp_path)
                            
                        except Exception as e:
                            error_msg = str(e)
                            if "429" in error_msg or "quota" in error_msg.lower():
                                update_log(f"⚠️ [{i+1}/{total}] API 요청 한도 조절을 위해 15초 대기 후 재개합니다...")
                                time.sleep(15)
                            elif "time" in error_msg.lower() or "connect" in error_msg.lower() or "503" in error_msg:
                                update_log(f"🔌 [{i+1}/{total}] 네트워크 지연으로 해당 파일 건너뜀: {error_msg}")
                                error_log.append(f"🔌 '{f['name']}' 처리 지연 제외: {error_msg}")
                                continue
                            else:
                                update_log(f"❌ [{i+1}/{total}] 스캔 실패 (제외): {error_msg}")
                                error_log.append(f"❌ '{f['name']}' 스캔 오류: {error_msg}")
                    
                    update_log("🎉 전체 스캔 및 마스터 DB 실시간 동기화가 완료되었습니다.")
                    st.success("문서 스캔 및 구글 시트 DB 업데이트가 완료되었습니다.")
                    
                    if error_log:
                        st.error(f"⚠️ 총 {len(error_log)}건의 문서 처리 중 확인이 필요한 내역이 있습니다.")
                        with st.expander("상세 오류 로그 확인"):
                            for err in error_log:
                                st.write(err)

# ----------------- TAB 5: HACCP 챗봇 (Multi-Agent System + 강조문구 원문 페이지 직행 뷰어) -----------------
def extract_clickable_highlights(content_text):
    """챗봇 답변에서 규정 코드(YS-...) 및 굵은 글씨(**...**) 강조 구문을 추출하여 원문 직행 버튼 목록을 생성합니다."""
    refs = []
    for m in re.findall(r'YS-[가-힣A-Za-z0-9_-]+(?:\([가-힣,\s]+\))?', content_text):
        m_clean = m.strip()
        if m_clean not in refs:
            refs.append(m_clean)
    skip_words = {"최종 판정", "종합 판정", "수신", "발신", "문서번호", "제목", "기인증 범위 준수", "법적 한계선"}
    for b in re.findall(r'\*\*([^*]+)\*\*', content_text):
        b_clean = b.strip().rstrip(':').strip()
        if 2 <= len(b_clean) <= 28 and not any(sw in b_clean for sw in skip_words):
            if b_clean not in refs:
                refs.append(b_clean)
    return refs[:12]

with tab5:
    st.markdown("### 💬 식품안전 및 HACCP 통합 검증 AI 시스템")
    st.caption("사내 기준서, 선행요건 및 법적 인증 현황을 기반으로 3단계 교차 검증(기준 추출 ➔ 법규·인증 대조 ➔ 종합 보고)을 수행하며, 답변 하단의 강조 항목을 클릭하면 해당 기준서의 원문 페이지(형광펜 음영 표시)를 즉시 열람할 수 있습니다.")
    
    for msg_idx, msg in enumerate(st.session_state.chat_messages):
        with st.chat_message(msg["role"]):
            safe_content = re.sub(r'(\d)~(\d)', r'\1&#126;\2', msg["content"])
            st.markdown(safe_content, unsafe_allow_html=True)
            
            if msg["role"] == "assistant" and "안녕하십니까" not in msg["content"] and "오류" not in msg["content"]:
                highlight_terms = extract_clickable_highlights(msg["content"])
                if highlight_terms:
                    st.markdown("##### 🔎 본문 강조 항목 및 근거 규정 원문 바로가기 (클릭 시 해당 문서 페이지 및 음영 표시)")
                    btn_cols = st.columns(4)
                    for t_idx, term in enumerate(highlight_terms):
                        with btn_cols[t_idx % 4]:
                            if st.button(f"📄 {term}", key=f"chat_ref_{msg_idx}_{t_idx}", use_container_width=True):
                                with st.spinner(f"'{term}' 관련 기준서 원문 페이지 및 음영 좌표를 탐색 중입니다..."):
                                    found_ref = locate_reference_in_drive(term)
                                    if found_ref:
                                        st.session_state.chat_doc_viewer = found_ref
                                    else:
                                        st.warning(f"'{term}' 항목과 직접 매칭되는 PDF 원문을 찾지 못했습니다. 좌측 딥 서치를 이용해 주십시오.")
                                        
    if st.session_state.chat_doc_viewer:
        v_info = st.session_state.chat_doc_viewer
        st.markdown("---")
        with st.container():
            h_col1, h_col2 = st.columns([8.5, 1.5])
            with h_col1:
                st.markdown(f"#### 🖍️ 근거 원문 직행 뷰어: **{v_info['name']}** (클릭 항목: `{v_info['ref_term']}` / 매칭 페이지: **p.{v_info['page']}**)")
            with h_col2:
                if st.button("✖ 뷰어 닫기", use_container_width=True):
                    st.session_state.chat_doc_viewer = None
                    st.rerun()
                    
            if PYMUPDF_INSTALLED:
                f_bytes = get_cached_file_bytes(v_info['id'])
                img_bytes, total_p, m_pages = render_highlighted_pdf_page(f_bytes, v_info['page'], v_info['highlight_kw'])
                if img_bytes:
                    nv1, nv2, nv3, nv4 = st.columns([2, 2, 3, 3])
                    with nv1:
                        if st.button("◀ 이전 페이지", key="chat_v_prev", use_container_width=True) and v_info['page'] > 1:
                            st.session_state.chat_doc_viewer['page'] -= 1
                            st.rerun()
                    with nv2:
                        if st.button("다음 페이지 ▶", key="chat_v_next", use_container_width=True) and v_info['page'] < total_p:
                            st.session_state.chat_doc_viewer['page'] += 1
                            st.rerun()
                    with nv3:
                        if m_pages:
                            st.caption(f"🖍️ '{v_info['highlight_kw']}' 포함 페이지: p.{', p.'.join(map(str, m_pages[:8]))} (전체 {total_p}p)")
                        else:
                            st.caption(f"현재 {v_info['page']} / {total_p} 페이지")
                    with nv4:
                        st.link_button("🔗 구글 드라이브 새 창 열기", v_info['webViewLink'], use_container_width=True)
                    st.image(img_bytes, use_container_width=True)
                else:
                    st.components.v1.iframe(f"https://drive.google.com/file/d/{v_info['id']}/preview", height=600, scrolling=True)
            else:
                st.components.v1.iframe(f"https://drive.google.com/file/d/{v_info['id']}/preview", height=600, scrolling=True)
            
    if prompt := st.chat_input("공정 관리 기준, 인증 범위, 법규 준수 사항 등을 입력해 주십시오. (예: 신규 멸균 공정 추가 시 필요한 인증 및 절차 검토)"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            with st.status("🛡️ 3단계 규정 교차 검증 프로세스 가동 중...", expanded=True) as status:
                try:
                    kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False)
                    cache_name = st.session_state.get("master_cache_name")
                    
                    if cache_name:
                        try:
                            cache = genai.caching.CachedContent.get(cache_name)
                            base_model = genai.GenerativeModel.from_cached_content(cached_content=cache)
                        except Exception:
                            base_model = genai.GenerativeModel(model_name=MODEL_NAME)
                    else:
                        base_model = genai.GenerativeModel(model_name=MODEL_NAME)
                    
                    # ---------- Agent A: 정보 추출 및 분석 ----------
                    st.write("📋 **[1단계: 기준 추출]** 질의 의도 분석 및 전후 연계 공정(End-to-End) 관련 기준 추출 중...")
                    prompt_A = f"""[Agent A 임무: 사내 기준 및 공정 데이터 추출]
                    지식베이스:\n{kb_str}\n\n사용자 질의: {prompt}
                    
                    임무: 사용자의 질의에 정확히 답변하기 위한 객관적인 기준 데이터 리포트를 작성하십시오.
                    
                    [전 공정(End-to-End) 통합 추출 원칙]:
                    사용자가 특정 단일 공정(예: 살균, 여과)이나 특정 반제품(예: 원액두유, 배양액)에 국한하여 질의하더라도 해당 구간만 단편적으로 추출하지 마십시오.
                    지식베이스 및 적재된 기준서를 탐색하여 해당 품목·공정과 직결되는 [원료 수불 및 전처리 ➔ 주 가공 및 살균/멸균 ➔ 여과 ➔ 무균 충전·포장(포장지 멸균) ➔ 완제품 출하]까지의 전체 공정 체계와 이에 따른 모든 중요관리점(CCP) 및 선행요건 기준을 포괄적으로 도출하여 기술하십시오."""
                    res_A = base_model.generate_content(prompt_A).text
                    
                    # ---------- Agent B: 사내 규정 교차 검증 (범용 트랙 스위칭) ----------
                    st.write("⚖️ **[2단계: 법규·인증 검증]** 사내 매뉴얼 및 품목별 법적 인증 범위 교차 검증 중...")
                    
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
                    
                    # ---------- Agent C: 실무 맞춤형 최종 답변 ----------
                    st.write("📑 **[3단계: 종합 보고서 작성]** 경영진 및 대외 심사 대응용 공식 검토 의견 생성 중...")
                    
                    history_for_gemini = []
                    for m in st.session_state.chat_messages[-6:]:
                        if m["role"] == "assistant":
                            if "안녕하십니까" in m["content"] or "안녕하세요!" in m["content"]:
                                continue
                            history_for_gemini.append({"role": "model", "parts": [m["content"]]})
                        else:
                            history_for_gemini.append({"role": "user", "parts": [m["content"]]})
                    
                    prompt_C = f"""[Agent C 임무: 공식 심사 대응 및 경영진 보고용 최종 답변 작성]
                    [Agent B의 법규·인증 교차검증 판정 결과]:
                    {res_B}
                    
                    임무: 위 검증 결과를 바탕으로 외부 심사원(방문심사 업체, 인증기관) 및 사내 경영진·상급자가 직접 열람할 수 있는 수준의 명확하고 품격 있는 공식 답변을 작성하십시오.
                    
                    [작성 수칙 및 어조(Tone & Manner) 절대 원칙]:
                    1. **공식 비즈니스 경어체 엄수**: '숲', '나비효과', '퉁치다', '건바이건' 등 비유적 표현이나 구어체, 가벼운 수식어 사용을 전면 금지합니다. 철저히 정중하고 격식 있는 경어체(~합니다, ~입니다, ~바랍니다)와 정확한 식품안전 전문 용어(한계기준, 중요관리점, 유효성 평가, 변경관리, 교차오염 방지, 선행요건 등)만을 사용하여 신뢰감 있게 서술하십시오.
                    2. **종합 판정 결론 최상단 명시**: 답변 첫 줄에 질의 사항에 대한 최종 판정 결론(현행 기준 적합 여부, 조건부 가능, 변경인증 필수 여부 등)을 두괄식으로 명확히 선언하십시오. 특히 품목별 미인증 공정이 존재하는 경우, 현 상태로는 완제품 출하가 불가하며 관할 기관의 변경인증(공정 추가)이 선행되어야 함을 명확히 명시하십시오.
                    3. **전체 공정 체계 및 관리 기준 제시**: 해당 품목이 완제품으로 출하되기 위해 거쳐야 하는 전체 공정 흐름을 제시할 때에는 화면 우측으로 잘리는 가로형 코드블록 대신 가독성 높은 마크다운 표(Table) 또는 번호 목록으로 정리하십시오. 또한 범위 표기 시 마크다운 취소선이 발생하지 않도록 물결표(~) 대신 하이픈(-)이나 '내지'를 사용하거나 정확히 표기하십시오.
                    4. **전사적 연계 영향 및 원문 링크용 강조 표기**: 핵심 기준명(예: **작업장기준서**, **위생관리기준서**, **보관 및 운반관리 기준서**, **이물관리기준서**, **알러겐 관리기준서**, **YS-관리-P-210**)과 중요 핵심 키워드는 반드시 굵은 글씨(`**...**`)로 강조하여 사용자가 클릭 시 해당 원문 페이지로 이동할 수 있도록 작성하십시오."""
                    
                    final_chat = base_model.start_chat(history=history_for_gemini)
                    res_C = final_chat.send_message(prompt_C)
                    full_response = res_C.text
                    
                    status.update(label="✅ 규정 검증 및 검토 의견 작성 완료", state="complete", expanded=False)
                    
                    safe_full_response = re.sub(r'(\d)~(\d)', r'\1&#126;\2', full_response)
                    message_placeholder.markdown(safe_full_response, unsafe_allow_html=True)
                    st.session_state.chat_messages.append({"role": "assistant", "content": full_response})
                    st.rerun()
                    
                except Exception as e:
                    err_msg = f"⚠️ 검증 시스템 가동 중 오류가 발생하였습니다: {e}"
                    status.update(label="🚨 시스템 오류 발생", state="error", expanded=False)
                    message_placeholder.error(err_msg)
                    st.session_state.chat_messages.append({"role": "assistant", "content": err_msg})
