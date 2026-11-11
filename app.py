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
    "수질검사": "제품수(음용수) 및 지하수는 연 2회(반기별 1회) 공인검사기관에 검사를 의뢰하며, 자체 용수 검사는 월 1회(관능, pH, 대장균 등) 실시합니다.",
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
    "수질검사_월간": {"표시명": "자체 수질검사 성적서 (월간)", "주기": 1},
    "수질검사_반기": {"표시명": "공인기관 수질검사 성적서 (반기)", "주기": 6},
    "수질검사_노로": {"표시명": "노로바이러스 검사 성적서", "주기": 12},
    "저수조청소": {"표시명": "저수조 청소필증 (상/하반기)", "주기": 6},
    "방충방서_월간": {"표시명": "방충방서 점검 리포트 (월간)", "주기": 1},
    "책임보험": {"표시명": "영업배상책임보험 / PL보험 증권", "주기": 12},
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
        except:
            pass

if "priority_keywords" not in st.session_state: st.session_state.priority_keywords = []
if "search_done" not in st.session_state: st.session_state.search_done = False
if "found_files" not in st.session_state: st.session_state.found_files = []
if "search_keyword" not in st.session_state: st.session_state.search_keyword = ""
if "search_question" not in st.session_state: st.session_state.search_question = ""
if "final_briefing" not in st.session_state: st.session_state.final_briefing = ""
if "last_file_id" not in st.session_state: st.session_state.last_file_id = ""
if "view_url" not in st.session_state: st.session_state.view_url = ""
if "preview_url" not in st.session_state: st.session_state.preview_url = ""
if "target_folder_key" not in st.session_state: st.session_state.target_folder_key = None
if "gw_keyword" not in st.session_state: st.session_state.gw_keyword = ""
if "auto_db" not in st.session_state: st.session_state.auto_db = []
if "files_to_scan" not in st.session_state: st.session_state.files_to_scan = []

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
    SHEET_ID = st.secrets.get("MASTER_SHEET_ID", "")
    genai.configure(api_key=GEMINI_API_KEY)
except:
    st.error("🚨 필수 키(secrets)가 누락되었습니다.")
    st.stop()

def get_credentials():
    try:
        return Credentials(
            token=None, refresh_token=st.secrets["google_oauth"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["google_oauth"]["client_id"], client_secret=st.secrets["google_oauth"]["client_secret"]
        )
    except:
        return None

def get_drive_service():
    creds = get_credentials()
    return build('drive', 'v3', credentials=creds) if creds else None

def get_sheets_service():
    creds = get_credentials()
    return build('sheets', 'v4', credentials=creds) if creds else None

# ==========================================
# [3] 유틸리티 및 스마트 캐싱/정렬
# ==========================================
def extract_year_string(filename, created_time=""):
    match = re.search(r'(2[4-9])(0[1-9]|1[0-2])([0-2][1-9]|3[01])', filename.replace(" ", ""))
    if match: return f"20{match.group(1)}년도"
    for yr in ["26", "25", "24", "23"]:
        if f"{yr}." in filename or f"20{yr}" in filename or f"{yr}년" in filename: return f"20{yr}년도"
    return f"{created_time[:4]}년도" if created_time else "분류 없음"

def is_blacklisted(filename, category_name=""):
    if "Thumbs.db" in filename or filename.endswith(".txt"): return True
    if "영업신고증" in category_name and any(k in filename for k in ["통신판매", "집단급식", "화장품", "지하수"]): return True
    if "인증서" in category_name and ("리스트" in filename or filename.endswith(".hwp")): return True
    return False

@st.cache_data(ttl=3600)
def get_target_folder_ids(_service, root_folder_id):
    folders = [root_folder_id]
    def fetch_children(parent_id):
        page_token = None
        while True:
            res = _service.files().list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false", 
                fields="nextPageToken, files(id)", pageSize=1000, pageToken=page_token).execute()
            for item in res.get('files', []):
                folders.append(item['id'])
                fetch_children(item['id'])
            page_token = res.get('nextPageToken')
            if not page_token: break
    try: fetch_children(root_folder_id)
    except: pass
    return folders

def extract_snippet_from_pdf(file_bytes, keyword):
    if not PYMUPDF_INSTALLED:
        return "⚠️ 본문 미리보기를 지원하려면 시스템에 PyMuPDF가 설치되어야 합니다."
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").replace("\n", " ")
            idx = text.find(keyword)
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(text), idx + 40 + len(keyword))
                snippet = text[start:end]
                return f"[페이지 {page_num + 1}] ... {snippet} ..."
        return "💡 문서 내 텍스트 매칭 없음 (이미지 스캔본일 가능성)"
    except Exception as e:
        return f"본문 스니펫 추출 실패: {e}"

def download_file_bytes(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False: _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

def execute_exact_match(display_keyword, folder_key=None, gw_keyword=None, priority_keywords=None):
    service = get_drive_service()
    if not service: return
    
    st.session_state.update({
        "search_done": True, "search_keyword": display_keyword, "search_question": display_keyword,
        "target_folder_key": folder_key, "gw_keyword": gw_keyword,
        "priority_keywords": priority_keywords or [], "last_file_id": ""
    })
    
    db_list = st.session_state.auto_db
    matched_files = []
    
    if db_list and priority_keywords:
        for row in db_list:
            kw = row.get("키워드", "")
            if any(req_kw in kw for req_kw in priority_keywords):
                matched_files.append({
                    'id': row.get("파일 ID", ""),
                    'name': row.get("파일명", ""),
                    'webViewLink': row.get("뷰어 링크", ""),
                    'createdTime': row.get("발급일", ""),
                    'mimeType': 'application/pdf'
                })
    
    if matched_files:
        st.session_state.found_files = matched_files
        st.success(f"⚡ [마스터 DB 연동] 관련 최신 문서 {len(matched_files)}건을 즉시 호출하였습니다.")
    elif folder_key and folder_key in FLAT_FOLDER_DB:
        target_id = FLAT_FOLDER_DB[folder_key]
        if not target_id.startswith("folder_id_"):
            target_folders = get_target_folder_ids(service, target_id)
            all_files = []
            for fid in target_folders:
                page_token = None
                while True:
                    res = service.files().list(
                        q=f"'{fid}' in parents and trashed = false", spaces='drive', 
                        fields='nextPageToken, files(id, name, webViewLink, mimeType, createdTime)', 
                        pageSize=1000, pageToken=page_token).execute()
                    for f in res.get('files', []):
                        if f['mimeType'] != 'application/vnd.google-apps.folder':
                            f['snippet'] = ""
                            all_files.append(f)
                    page_token = res.get('nextPageToken')
                    if not page_token: break
            st.session_state.found_files = all_files
            st.success(f"✅ 정밀 탐색 완료: 연관 문서 {len(st.session_state.found_files)}건을 확보하였습니다.")
    else:
        st.session_state.found_files = []

def execute_deep_search(query_text):
    service = get_drive_service()
    if not service: return
    
    keyword = query_text.strip()
    st.session_state.update({
        "search_done": True, "search_keyword": keyword, "search_question": query_text,
        "target_folder_key": None, "gw_keyword": None, "priority_keywords": [], "last_file_id": ""
    })
    
    with st.spinner("본문 정밀 검색 및 스니펫 추출을 진행 중입니다..."):
        all_files = []
        page_token = None
        while True:
            res = service.files().list(
                q=f"fullText contains '{keyword}' and trashed = false and '{DRIVE_FOLDER_ID}' in parents", 
                spaces='drive', fields='nextPageToken, files(id, name, webViewLink, mimeType, createdTime)', 
                pageSize=1000, pageToken=page_token).execute()
            for f in res.get('files', []):
                if f['mimeType'] != 'application/vnd.google-apps.folder':
                    f['snippet'] = ""
                    all_files.append(f)
            page_token = res.get('nextPageToken')
            if not page_token: break
            
        if PYMUPDF_INSTALLED:
            for f in all_files:
                if "pdf" in f.get('mimeType', '').lower():
                    try:
                        file_bytes = download_file_bytes(service, f['id'])
                        f['snippet'] = extract_snippet_from_pdf(file_bytes, keyword)
                    except:
                        f['snippet'] = "스니펫 추출 오류"
                else:
                    f['snippet'] = "PDF 문서가 아님"
                    
        st.session_state.found_files = all_files

# ==========================================
# [4] 사이드바 (마스터 캐싱 및 원클릭 버튼)
# ==========================================
with st.sidebar:
    st.markdown("### 🔄 마스터 지식베이스 동기화")
    st.caption("최신 사내 규정 및 인증 현황을 AI 검증 엔진에 적재합니다. (1일 1회 권장)")
    
    if st.session_state.get("master_cache_name"):
        st.success("✅ 마스터 지식베이스가 활성화되어 있습니다.")
        
    if st.button("마스터 지식베이스 갱신 및 적재", use_container_width=True):
        drive_service = get_drive_service()
        if not drive_service:
            st.error("구글 드라이브 API 인증에 실패하였습니다.")
        elif not st.session_state.auto_db:
            st.warning("⚠️ 적재 전, 우측 메인 화면의 [3. 🚨 탑다운 대시보드] 탭을 클릭하여 마스터 DB를 먼저 동기화해 주십시오.")
        else:
            with st.spinner("마스터 DB에 등록된 최신 기준서, 선행요건 및 인증서를 선별하여 메모리에 적재 중입니다..."):
                try:
                    uploaded_laws = []
                    target_pdfs = []
                    seen_fids = set()
                    
                    # 중복 파일 ID 제거 및 핵심 규정(기준서, 선행요건, FSSC, 인증서) 선별
                    for row in reversed(st.session_state.auto_db):
                        kw = row.get("키워드", "")
                        fid = row.get("파일 ID", "")
                        fname = row.get("문서_실제제목") or row.get("파일명", "")
                        if not fid or fid in seen_fids:
                            continue
                        if kw in ("매뉴얼", "기준서", "선행요건") or "HACCP" in kw or "FSSC" in kw or "FDA" in kw or "인증" in kw:
                            seen_fids.add(fid)
                            target_pdfs.append({"id": fid, "name": fname})
                    
                    if len(target_pdfs) > 45:
                        target_pdfs = target_pdfs[:45]
                        st.info("ℹ️ 시스템 처리 용량 최적화를 위해 최신 핵심 기준서 및 인증서 45건을 우선 적재합니다.")
                    
                    if not target_pdfs:
                        st.warning("⚠️ 적재할 기준서 또는 인증서 문서가 DB에 없습니다. 4번 탭에서 문서 스캔을 먼저 진행해 주십시오.")
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
                            except Exception as inner_e:
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
            st.caption("문서 본문 내 키워드를 정밀 탐색하여 해당 문맥을 미리 표시합니다.")
            manual_query = st.text_input("검색어 입력:", placeholder="예: 방충방서, 배합비", label_visibility="collapsed")
            if st.form_submit_button("본문 정밀 검색 실행 🚀", use_container_width=True) and manual_query:
                execute_deep_search(manual_query)

    with sidebar_tab1:
        st.caption("전산 및 클라우드 기반으로 즉시 열람·증빙이 가능한 심사 대응 문서 카테고리입니다.")
        
        with st.expander("📁 1. 영업 인허가 및 각종 인증서", expanded=True):
            if st.button("영업신고/공장등록/가설건축물", use_container_width=True): 
                execute_exact_match("인허가", "인허가 서류", "", [
                    "식품제조가공업", "유가공업", "집유업", "사업자등록증", "공장등록증", 
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

        with st.expander("📘 2. 사내 규정 및 절차 (매뉴얼)"):
            if st.button("선행요건 / HACCP 기준서", use_container_width=True): 
                execute_exact_match("기준서", "선행요건", "", ["선행요건", "HACCP"])
            if st.button("위생 / 해충 / 알러겐 절차", use_container_width=True): 
                execute_exact_match("위생 절차", "기준서", "", ["위생 관리", "해충", "알러겐"])
            if st.button("이물 / 식품보안 절차", use_container_width=True): 
                execute_exact_match("보안 절차", "선행요건", "", ["이물", "식품보안", "사기대응"])
            if st.button("위기대응 및 회수 절차", use_container_width=True): 
                execute_exact_match("회수 절차", "기준서", "", ["위기관리", "제품회수"])
        
        with st.expander("🧼 3. 위생·환경 평가 및 인력 점검"):
            if st.button("수질검사 성적서 / 저수조 청소", use_container_width=True): 
                execute_exact_match("수질검사", "수질검사", "용수 검사 성적서", ["수질검사", "저수조청소"])
            if st.button("방역 관리 리포트 (GW)", use_container_width=True): 
                execute_exact_match("방제 레포트", "방충방서 관련 서류", "방역 관리 리포트", ["방충방서_월간"])
            if st.button("종사자 법정/보건증 및 수료증", use_container_width=True): 
                execute_exact_match("보건증/교육", "선행요건", "", ["보건증", "법정위생교육", "HACCP정기교육", "교육"])
            if st.button("손 위생 및 낙하세균 (GW)", use_container_width=True): 
                execute_exact_match("위생 검사", "", "낙하세균 검사 결과")
            if st.button("냉장/냉동 창고 온도 일지 (GW)", use_container_width=True): 
                execute_exact_match("온도 일지", "", "냉장/냉동 창고 온도 모니터링 일지")
            
        with st.expander("⚙️ 4. CCP 공정 관리 및 설비 검증"):
            if st.button("공정관리 일보 (GW)", use_container_width=True): 
                execute_exact_match("공정관리 일보", "", "공정관리 일보")
            if st.button("상업적 무균테스트 (GW)", use_container_width=True): 
                execute_exact_match("무균테스트", "", "상업적 무균테스트 결과 보고서")
            if st.button("계측기 검·교정 이력 (GW)", use_container_width=True): 
                execute_exact_match("계측기", "", "공인기관 검·교정 결과")
            if st.button("설비 유지보수 이력", use_container_width=True): 
                execute_exact_match("설비이력", "설비이력", "")
            
        with st.expander("📦 5. 원부자재 관리 및 사후 추적성"):
            if st.button("입고 검수서 (GW)", use_container_width=True): 
                execute_exact_match("입고검수", "", "입고 검수서")
            if st.button("자가품질 및 제품검사 (GW)", use_container_width=True): 
                execute_exact_match("품질검사", "", "일반검사 일보")
            if st.button("클레임 현황 및 시정조치 (GW)", use_container_width=True): 
                execute_exact_match("클레임", "", "부적합 현황 보고")
            if st.button("모의회수 기록", use_container_width=True): 
                execute_exact_match("모의회수", "모의회수", "모의회수", ["모의회수"])
            if st.button("PL보험 및 영업배상책임보험", use_container_width=True): 
                execute_exact_match("책임보험", "인증서", "", ["책임보험"])

# ==========================================
# [5] 메인 UI 탭 구성
# ==========================================
st.markdown("## 🛡️ HACCP Agent 통합 포털")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🤖 원클릭 뷰어 & 스니펫", "📁 탐색기", "🚨 탑다운 대시보드", "⚙️ DB 자동화(관리자)", "💬 HACCP 챗봇"])

# ----------------- TAB 1: 뷰어 & 스니펫 -----------------
with tab1:
    if st.session_state.search_done:
        keyword = st.session_state.search_keyword
        st.info(f"🔍 조회 항목: **{keyword}**")
        
        raw_files = [f for f in st.session_state.found_files if not is_blacklisted(f['name'], keyword)]
        
        if not raw_files and st.session_state.target_folder_key is not None and not st.session_state.priority_keywords:
            st.warning("⚠️ 지정 폴더 내 일치하는 클라우드 문서가 없습니다. 하단의 전자결재(그룹웨어) 링크를 확인해 주십시오.")
            
        elif raw_files:
            for f in raw_files: f['year'] = extract_year_string(f['name'], f.get('createdTime', ''))
            years = ["전체보기 (최신순)"] + sorted(list(set([f['year'] for f in raw_files])), reverse=True)
            
            sel_year = st.radio("📅 연도 필터", years, horizontal=True, label_visibility="collapsed")
            f_list = raw_files if sel_year == "전체보기 (최신순)" else [f for f in raw_files if f['year'] == sel_year]
            
            if any(f.get('snippet') for f in f_list):
                st.markdown("### 🔎 본문 매칭 스니펫 (미리보기)")
                for idx, f in enumerate(f_list):
                    if f.get('snippet') and "발견 안 됨" not in f.get('snippet') and "오류" not in f.get('snippet'):
                        snippet_html = f['snippet'].replace(keyword, f"<b style='color:red; background-color:yellow;'>{keyword}</b>")
                        st.markdown(f"**{idx+1}. {f['name']}**")
                        st.markdown(f"> {snippet_html}", unsafe_allow_html=True)
                        st.markdown("---")

            opts = {f"{i+1}. {f['name']}": f for i, f in enumerate(f_list)}
            if len(f_list) > 1:
                sel_name = st.selectbox(f"📂 {sel_year} 문서 선택 (뷰어로 열기)", list(opts.keys()))
            else:
                sel_name = list(opts.keys())[0]
                st.markdown(f"**📂 {sel_year} 단일 문서 자동 선택:** {opts[sel_name]['name']}")
                
            top_file = opts[sel_name]
            
            if st.session_state.last_file_id != top_file['id']:
                st.session_state.view_url = top_file['webViewLink']
                st.session_state.preview_url = f"https://drive.google.com/file/d/{top_file['id']}/preview"
                
                with st.spinner("🤖 문서 적합성 및 관련 규정 교차 분석 중..."):
                    try:
                        file_bytes = download_file_bytes(get_drive_service(), top_file['id'])
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
                            except Exception as cache_err:
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
                        except: pass
                st.session_state.last_file_id = top_file['id']

            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"🔗 **[원본 문서 새 창에서 열기 (Ctrl+F 키워드 검색 지원)]({st.session_state.view_url})**")
                st.components.v1.iframe(st.session_state.preview_url, height=600, scrolling=True)
            with col2:
                st.write("📋 **AI 문서 검토 및 규정 연계 브리핑:**")
                if "오류" in st.session_state.final_briefing:
                    st.error(st.session_state.final_briefing)
                else:
                    st.success(st.session_state.final_briefing)

        if st.session_state.gw_keyword:
            gw_kw = st.session_state.gw_keyword
            st.info(f"💡 전자결재(그룹웨어) 연동 서류: **{gw_kw}**")
            gw_url = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?keyword={urllib.parse.quote(gw_kw)}"
            st.link_button(f"👉 그룹웨어 [{gw_kw}] 문서함 열기", gw_url, type="primary")

# ----------------- TAB 2: 수동 탐색 -----------------
with tab2:
    st.markdown("### 📁 공장 심사 서류 다이렉트 탐색기")
    
    col_major, col_minor = st.columns(2)
    with col_major:
        selected_major = st.selectbox("📂 대분류 선택", list(FLAT_FOLDER_DB.keys()))
    
    target_folder_id = FLAT_FOLDER_DB[selected_major]

    if st.button(f"'{selected_major}' 전체 문서 호출", type="primary"):
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
                                if not pt: break

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

# ----------------- TAB 3: 대시보드 -----------------
with tab3:
    st.markdown("### 🚨 실시간 법정 서류 및 인증 유효기간 대시보드")
    
    if not st.session_state.auto_db:
        sheet_service = get_sheets_service()
        if sheet_service and SHEET_ID:
            with st.spinner("구글 시트 마스터 DB와 동기화 중입니다..."):
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
                except Exception as e:
                    st.warning("⚠️ 구글 시트 연동 실패: 스캔된 데이터가 없거나 접근 권한 확인이 필요합니다.")

    latest_dash_dict = {}
    for row in st.session_state.auto_db:
        kw = row.get("키워드", "")
        if not kw or kw in ("PASS", "기타", "매뉴얼", "일반수료증"): continue
        exp_str = str(row.get("만료일", ""))
        sort_date = "9999-12-31" if exp_str == "영구" else exp_str
        if kw not in latest_dash_dict or sort_date > latest_dash_dict[kw]["sort_date"]:
            latest_dash_dict[kw] = {"entry": row, "sort_date": sort_date}
            
    db_dict = {kw: v["entry"] for kw, v in latest_dash_dict.items()}
    
    dashboard_data = []
    missing_docs = []
    today = datetime.date.today()
    processed_keys = set()
    
    allowed_dynamic_prefixes = ("가설건축물_", "수질검사_", "보건증_", "법정위생교육_", "HACCP교육_")
    
    for key, meta in MASTER_DOC_REQUIREMENTS.items():
        processed_keys.add(key)
        row_data = {
            "구분(키워드)": key,
            "서류명(마스터)": meta["표시명"],
            "법정주기(개월)": meta["주기"],
            "스캔된 파일명": "-",
            "발급일": "-",
            "만료일": "-",
            "개정(Rev)": "-",
            "D-Day": "-",
            "상태": "🚨 누락 (파일 없음)"
        }
        
        if key in db_dict:
            doc = db_dict[key]
            row_data["스캔된 파일명"] = doc.get("문서_실제제목", doc.get("파일명", ""))
            row_data["발급일"] = doc.get("발급일", "")
            exp_date_str = str(doc.get("만료일", ""))
            row_data["만료일"] = exp_date_str
            row_data["개정(Rev)"] = doc.get("개정번호", "-")
            
            if exp_date_str == "영구":
                row_data["D-Day"] = "-"
                row_data["상태"] = "✅ 영구 (갱신 불필요)"
            else:
                try:
                    expire_date = pd.to_datetime(exp_date_str).date()
                    d_day = (expire_date - today).days
                    row_data["D-Day"] = str(d_day)
                    if d_day < 0: row_data["상태"] = "🚨 기간 경과 (즉시 갱신)"
                    elif d_day <= 30: row_data["상태"] = "⚠️ 갱신 임박 (30일 이내)"
                    else: row_data["상태"] = "🟢 정상"
                except:
                    row_data["D-Day"] = "N/A"
                    row_data["상태"] = "오류"
        else:
            missing_docs.append(meta["표시명"])
        
        dashboard_data.append(row_data)

    for key, doc in db_dict.items():
        if key not in processed_keys and key.strip() != "":
            if key.startswith(allowed_dynamic_prefixes) or key == "HACCP정기교육":
                exp_date_str = str(doc.get("만료일", ""))
                cycle = str(doc.get("주기(개월)", "24"))
                if key.startswith("법정위생교육_") or key == "HACCP정기교육":
                    cycle = "12"
                
                dyn_row = {
                    "구분(키워드)": key,
                    "서류명(마스터)": f"💡 [자동감지] {doc.get('문서_실제제목', key)}",
                    "법정주기(개월)": cycle,
                    "스캔된 파일명": doc.get("파일명", ""),
                    "발급일": doc.get("발급일", ""),
                    "만료일": exp_date_str,
                    "개정(Rev)": doc.get("개정번호", "-"),
                    "D-Day": "-",
                    "상태": "-"
                }
                
                if exp_date_str == "영구":
                    dyn_row["D-Day"] = "-"
                    dyn_row["상태"] = "✅ 영구 (갱신 불필요)"
                else:
                    try:
                        expire_date = pd.to_datetime(exp_date_str).date()
                        d_day = (expire_date - today).days
                        dyn_row["D-Day"] = str(d_day)
                        if d_day < 0: dyn_row["상태"] = "🚨 기간 경과 (즉시 갱신)"
                        elif d_day <= 30: dyn_row["상태"] = "⚠️ 갱신 임박 (30일 이내)"
                        else: dyn_row["상태"] = "🟢 정상"
                    except:
                        dyn_row["D-Day"] = "N/A"
                        dyn_row["상태"] = "오류"
                
                dashboard_data.append(dyn_row)

    df_dashboard = pd.DataFrame(dashboard_data)
    
    # --- UI 개편 로직 ---
    if not df_dashboard.empty:
        expired_df = df_dashboard[df_dashboard["상태"].str.contains("경과|누락", na=False)]
        warning_df = df_dashboard[df_dashboard["상태"].str.contains("임박", na=False)]
        
        # 3개월(90일) 및 6개월(180일) 이내 만료 도래 건수 산출
        due_90_count = 0
        due_180_count = 0
        for val in df_dashboard["D-Day"]:
            try:
                d_val = int(val)
                if 0 <= d_val <= 90:
                    due_90_count += 1
                if 0 <= d_val <= 180:
                    due_180_count += 1
            except:
                pass
        
        # 1. 요약 위젯 및 긴급 알람 (5열 구성)
        cols = st.columns(5)
        cols[0].metric("전체 관리 서류", f"{len(df_dashboard)}건")
        cols[1].metric("🚨 기한경과 / 미등록", f"{len(expired_df)}건")
        cols[2].metric("⚠️ 30일 내 만료 임박", f"{len(warning_df)}건")
        cols[3].metric("📅 3개월 / 6개월 내 도래", f"{due_90_count}건 / {due_180_count}건")
        cols[4].metric("✅ 영구 / 정상 서류", f"{len(df_dashboard) - len(expired_df) - len(warning_df)}건")
        
        if not expired_df.empty:
            st.error(f"🚨 **기한 경과 또는 미등록으로 즉시 조치가 필요한 서류가 {len(expired_df)}건 있습니다.**\n\n" + ", ".join(expired_df["서류명(마스터)"].tolist()))
        if not warning_df.empty:
            st.warning(f"⚠️ **30일 이내 만료 예정인 갱신 대상 서류가 {len(warning_df)}건 있습니다.**\n\n" + ", ".join(warning_df["서류명(마스터)"].tolist()))

        st.markdown("---")
        
        # 2. 그룹핑 로직
        def style_status(val):
            if "누락" in str(val): return 'color: white; background-color: #000000; font-weight:bold'
            if "경과" in str(val): return 'color: white; background-color: #ef4444; font-weight:bold'
            if "임박" in str(val): return 'color: black; background-color: #fbbf24; font-weight:bold'
            if "정상" in str(val): return 'color: white; background-color: #22c55e'
            if "영구" in str(val): return 'color: white; background-color: #3b82f6'
            return ''

        # 정기 검사 및 교육 (주기가 있는 서류 중 인증/보험 제외)
        edu_insp_mask = df_dashboard["구분(키워드)"].apply(lambda x: any(k in x for k in ["수질", "청소", "방충방서", "회수", "보건증", "위생교육", "HACCP정기교육"]))
        df_edu_insp = df_dashboard[edu_insp_mask]
        
        # HACCP 및 특수 인증서
        cert_mask = df_dashboard["구분(키워드)"].apply(lambda x: any(k in x for k in ["HACCP_", "CHINA", "FSSC", "MILK", "무항생제", "유기", "FDA", "책임보험"]))
        df_cert = df_dashboard[cert_mask]
        
        # 인허가 및 영구 서류
        license_mask = df_dashboard["구분(키워드)"].apply(lambda x: any(k in x for k in ["사업자", "공장등록", "건축물대장", "영업", "판매업", "급식소", "지하수개발"]))
        df_license = df_dashboard[license_mask]
        
        # 기타 잔여 서류
        handled_keys = set(df_edu_insp["구분(키워드)"]).union(set(df_cert["구분(키워드)"])).union(set(df_license["구분(키워드)"]))
        df_others = df_dashboard[~df_dashboard["구분(키워드)"].isin(handled_keys)]
        
        # 3. 분할 표시
        with st.expander("📅 1. 정기 검사 및 법정 의무 교육 (주기별 갱신 대상)", expanded=True):
            st.dataframe(df_edu_insp.style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True)
            
        with st.expander("🥇 2. HACCP 및 주요 식품안전 시스템 인증서", expanded=True):
            st.dataframe(df_cert.style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True)
            
        with st.expander("📁 3. 영업 인허가 및 시설 등록증 (영구 보존 서류)", expanded=False):
            st.dataframe(df_license.style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True)
            
        if not df_others.empty:
            with st.expander("💡 4. 기타 시설 및 동적 관리 서류", expanded=False):
                st.dataframe(df_others.style.map(style_status, subset=['상태']), hide_index=True, use_container_width=True)

# ----------------- TAB 4: AI 마스터 DB -----------------
with tab4:
    st.markdown("### ⚙️ 문서 AI 일괄 스캔 및 DB 동기화 (관리자용)")
    st.markdown("유효기간 및 개정 관리가 필요한 지정 폴더의 문서를 AI가 정밀 스캔하여 마스터 DB에 자동 업데이트합니다.")
    
    if not PYMUPDF_INSTALLED:
        st.error("🚨 딥 서치(본문 스니펫 미리보기) 기능을 위해 Github의 `requirements.txt`에 `PyMuPDF`를 추가해 주십시오.")

    default_targets = ["인허가 서류", "인증서", "수질검사", "교육수료증"]
    selected_targets = st.multiselect(
        "📌 스캔할 카테고리 선택 (관리 대상 폴더 선택)",
        options=list(FLAT_FOLDER_DB.keys()),
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
                        tf_id = FLAT_FOLDER_DB[cat]
                        if tf_id.startswith("folder_id_"): continue
                        
                        t_folders = get_target_folder_ids(service, tf_id)
                        for folder_id in t_folders:
                            page_token = None
                            while True:
                                res = service.files().list(
                                    q=f"'{folder_id}' in parents and trashed = false", 
                                    fields='nextPageToken, files(id, name, mimeType, webViewLink)', 
                                    pageSize=1000, pageToken=page_token).execute()
                                for f in res.get('files', []):
                                    if f['mimeType'] != 'application/vnd.google-apps.folder':
                                        files_to_scan.append(f)
                                page_token = res.get('nextPageToken')
                                if not page_token: break
                    
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
                            if row: scanned_ids.add(row[0])
                    except Exception as e:
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
                    - 축산물유통전문판매업 -> "축산물판매업"
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
                    - FSSC 22000 -> "FSSC22000"
                    - K-MILK 인증서 -> "K-MILK"
                    - 무항생제 인증서 -> "무항생제"
                    - 유기가공식품 인증서 -> "유기가공식품"
                    - FDA 식품시설등록(FFR) -> "FDA_FFR"
                    - FDA 공장등록(FCE) -> "FDA_FCE"
                    - 책임보험/영업배상/PL -> "책임보험"
                    - 사내 규정(YS-규정 등), 품목별 HACCP 기준서/PLAN/공정설명서, 파트별 선행요건 관리기준서 등 지침서는 무조건 -> "매뉴얼"
                    
                    💡 [교육 수료증 분류 규칙] 💡
                    - 기존영업자 대상 식품/축산물 위생교육 수료증은 반드시 수료한 '업종'을 확인하여 지정하십시오. (예: "법정위생교육_식품제조가공업", "법정위생교육_유가공업", "법정위생교육_수입식품")
                    - HACCP 팀장교육 또는 HACCP 정기교육 수료증은 무조건 -> "HACCP정기교육"
                    - 위 2가지 법정 의무교육 외의 일반 직무 교육, 1회성 특강 수료증은 -> "일반수료증"
                    
                    💡 [동적 확장(Dynamic) 규칙] 💡
                    - 가설건축물, 수질검사, 보건증 등 개별 관리 대상 문서는 아래 허용된 접두사로 시작하도록 키워드를 생성하십시오.
                    - 허용 접두사: "가설건축물_", "수질검사_", "보건증_"
                    - 예시: "가설건축물_8동", "보건증_홍길동"
                    
                    🚨 [기타 문서 예외 처리] 🚨
                    - 위 분류에 해당하지 않는 일반 기안서나 기타 참고 자료는 누락시키지 말고 "기타"로 분류하십시오. (절대 PASS 금지)
                    
                    만료일이 명시되어 있지 않더라도 법정 주기가 명확한 서류는 발급일 기준으로 만료일을 산출하여 기재하고, 유효기간이 없는 영구 보존 서류나 매뉴얼은 '영구'로 기재하십시오.
                    
                    반드시 JSON 형식으로만 응답하십시오.
                    형식: {
                        "키워드": "법정위생교육_식품제조가공업", 
                        "문서_실제제목": "본문 공식 명칭", 
                        "발급일": "YYYY-MM-DD", 
                        "만료일": "YYYY-MM-DD",
                        "개정번호": "Rev.0",
                        "분류근거": "발급기관 및 본문 내용에 따른 분류 근거"
                    }"""
                    
                    allowed_dynamic_prefixes = ("가설건축물_", "수질검사_", "보건증_", "법정위생교육_", "HACCP교육_")
                    
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
                            
                            if kw not in ("PASS", "기타", "매뉴얼", "일반수료증", "HACCP정기교육") and kw not in MASTER_DOC_REQUIREMENTS and not kw.startswith(allowed_dynamic_prefixes):
                                update_log(f"🛡️ 미지정 키워드 '기타' 분류 전환: {kw}")
                                kw = "기타"
                                parsed["키워드"] = kw
                            
                            if kw != "PASS":
                                cycle = str(MASTER_DOC_REQUIREMENTS.get(kw, {}).get("주기", 0))
                                if kw.startswith("법정위생교육_") or kw == "HACCP정기교육":
                                    cycle = "12"
                                    
                                new_row = [
                                    kw, f['name'], parsed.get("문서_실제제목",""), parsed.get("발급일",""), parsed.get("만료일",""),
                                    cycle, parsed.get("개정번호","-"), parsed.get("분류근거",""), fid, f['webViewLink']
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
                                            "키워드": kw, "파일명": f['name'], "문서_실제제목": parsed.get("문서_실제제목",""),
                                            "발급일": parsed.get("발급일",""), "만료일": parsed.get("만료일",""), "주기(개월)": cycle,
                                            "개정번호": parsed.get("개정번호","-"), "분류근거": parsed.get("분류근거",""),
                                            "파일 ID": fid, "뷰어 링크": f['webViewLink']
                                        }
                                        if not st.session_state.auto_db: st.session_state.auto_db = []
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
                            for err in error_log: st.write(err)

# ----------------- TAB 5: HACCP 챗봇 (Multi-Agent System) -----------------
with tab5:
    st.markdown("### 💬 식품안전 및 HACCP 통합 검증 AI 시스템")
    st.caption("사내 기준서, 선행요건 및 법적 인증 현황을 기반으로 3단계 교차 검증(기준 추출 ➔ 법규·인증 대조 ➔ 종합 보고)을 수행하여 정확한 판정 결과를 제공합니다.")
    
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
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
                        except:
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
                            if "안녕하십니까" in m["content"] or "안녕하세요!" in m["content"]: continue
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
                    3. **전체 공정 체계 및 관리 기준 제시**: 해당 품목이 완제품으로 출하되기 위해 거쳐야 하는 전체 공정 흐름(전처리·가공 ➔ 살균·멸균 ➔ 여과 ➔ 무균포장 등)을 제시하고, 단계별 중요관리점(CCP) 한계기준과 모니터링 방법을 체계적으로 정리하십시오.
                    4. **전사적 연계 영향 및 실무 관리 포인트**: 해당 사안이 타 생산 라인, 선행요건 관리기준, CIP 세척 밸리데이션, 알레르기 유발물질 교차오염 방지, 품목제조보고 및 식약처 HACCP / FSSC 22000 사후 심사에 미치는 연계 영향을 종합적으로 짚어주십시오."""
                    
                    final_chat = base_model.start_chat(history=history_for_gemini)
                    res_C = final_chat.send_message(prompt_C)
                    full_response = res_C.text
                    
                    status.update(label="✅ 규정 검증 및 검토 의견 작성 완료", state="complete", expanded=False)
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.chat_messages.append({"role": "assistant", "content": full_response})
                    
                except Exception as e:
                    err_msg = f"⚠️ 검증 시스템 가동 중 오류가 발생하였습니다: {e}"
                    status.update(label="🚨 시스템 오류 발생", state="error", expanded=False)
                    message_placeholder.error(err_msg)
                    st.session_state.chat_messages.append({"role": "assistant", "content": err_msg})
