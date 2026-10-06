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
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# [0] AI 현장심사 대응 지식베이스 (초정밀 팩트 데이터 1~20 통합본)
# ==========================================
KNOWLEDGE_BASE = {
    # 1. 작업장 및 환경 관리 기준 (작업장 관리 기준서)
    "조도기준": "조도 측정은 바닥에서 80cm 높이에서 분기별 1회 실시합니다. 기준치는 검사실/계량실 540 Lux 이상, 제조실/포장실 220 Lux 이상, 창고 및 냉장고 등 기타 구역은 110 Lux 이상입니다.",
    "온습도기준": "작업장 온습도는 월 1회 측정합니다. 청결구역 온도는 15~35℃, 준청결구역 1~40℃, 일반구역 1~35℃이며, 모든 구역의 습도 기준은 0~70% 이하로 관리됩니다.",
    "방충방서": "해충 모니터링은 주간 포획량에 따라 3단계로 관리됩니다. 청결구역 기준 비래해충(파리/나방 등)은 1단계 6마리, 2단계 10마리, 3단계 20마리이며, 3단계 이탈 시 배수로 청소 등 2단계 이탈 조치를 실행합니다. 방역은 월 2회 이상 실시합니다.",
    "식품보안": "식품보안 위험성 평가는 심각성과 발생가능성 점수의 합이 4 이상일 때 중요관리점(CCP)으로 지정합니다. 저수조, 화학제, 원료창고 등 주요 보안 구역은 1일 1회 순회 점검 및 CCTV 관찰, 시건장치 점검을 실시합니다.",

    # 2. 개인 위생 및 복장 규정 (위생 관리 기준서)
    "작업자건강": "액상 유출(상처) 사고 발생 시 부문장 보고 후 방수 밴드를 착용하고 식품 직접 접촉 업무에서 배제합니다. 설사, 구토 등 식중독 의심 환자는 완치(48시간 이상 무증상) 시까지 작업장 출입이 통제됩니다.",
    "복장기준": "기본 복장은 구역에 따라 청결구역은 위생작업복, 준청결구역은 위생가운, 정비작업 시에는 정비작업복을 착용합니다. 작업장 온도에 따라 하절기 반팔/조끼, 동절기 점퍼 등의 추가 복장이 허용됩니다.",
    "위생소독": "손 소독은 70% 알코올을 사용하며, 위생화 소독은 포미(살균소독제)를 물과 250배(200ppm) 희석한 발판 소독조에서 실시합니다.",
    "전자기기": "휴대폰은 원칙적으로 현장 반입 금지이나, 허가된 당직자/공정관리자 등은 사무실 내에서 사용 가능합니다. 현장 내 업무용/소통용 테블릿 및 LTE 무전기는 상시 알코올 소독 조건으로 반입이 허용됩니다.",

    # 3. 장갑 관리 기준 (장갑 관리 기준서)
    "장갑구분": "식품 접촉/청소 구역에 따라 장갑을 엄격히 구분합니다. 세척/소독 시에는 적색/노란색 고무장갑을 사용하며, 원자재 투입 시에는 라텍스/니트릴(흰색) 고무장갑을 사용합니다. 설비 정비 시에는 반코팅 목장갑을 사용하며, 부자재 투입 시에는 면장갑을 착용한 후 1회 사용 뒤 정비용으로 재활용합니다.",
    "장갑위생": "장갑을 맨손으로 사용할 경우 사용 전 70% 알코올로 소독해야 합니다. 사용 후 청소용 고무장갑은 세척 후 자외선 살균소독기나 건조대에 보관하며, 원자재 투입용 장갑은 중성세제와 70% 알코올로 세척/소독하여 보관합니다.",

    # 4. 이물 관리 기준 (이물 관리 기준서)
    "이물예방": "유리, 플라스틱, 목재, 금속 등 이물질 혼입을 방지하기 위해 스냅형 칼(커터칼), 스테이플러, 압정, 핀, 클립, 철수세미의 작업장 반입을 전면 금지합니다. 유리 제품은 가능한 다른 재질로 대체하거나 보호 처리해야 합니다. 테이프는 포장실 등 지정된 장소에서만 사용 가능합니다.",
    "이물발생조치": "생산 중 이물 발견 시 즉시 생산을 중단하고 과(팀)장에게 보고합니다. 이물 및 선별된 원료는 격리 보관하며, 원인 분석 후 '부적합보고서' 또는 '시정조치요구대책서'를 발행하여 개선합니다.",
    "이물보관": "소비자로부터 클레임 접수된 이물 신고 내용은 2년간 보관합니다. 소비자가 제시한 이물 실물과 증거품(사진 등)은 6개월간 보관하는 것이 원칙이나, 부패·변질 우려가 있는 경우 2개월간 보관할 수 있습니다.",
    "칼가위관리": "생산 구역에서 사용되는 칼과 가위는 회사가 지급, 식별, 등록한(번호 부여) 물품만 사용해야 합니다. 개인 사물함이나 칼집에 보관해서는 안 되며 임시 보관만 가능합니다. 시작 및 종료 시 상태 점검을 실시해야 합니다.",

    # 5. 알러겐 관리 기준 (알러겐 관리 기준서)
    "알러겐분류": "알러겐 함유 원료(우유, 대두, 땅콩, 호두, 토마토, 밀 등)는 자재 창고에서부터 별도 구분 및 식별(색상 라벨링)하여 보관합니다.",
    "알러겐취급": "알러겐 원·부자재의 계량, 배합에 사용되는 작업 도구는 전용으로 구분하고 식별 표시를 부착하여 교차오염을 방지합니다.",
    "알러겐검증": "CIP 후 알러겐 물질 잔류 여부는 연 1회 이상 검증(Reveal 3D 등 키트 활용)하며, 양성 판정 시 CIP 효과성 증대 방안을 검토합니다.",

    # 6. 냉동원료 해동 기준 (냉동원료의 해동 기준서)
    "해동장소": "냉동원료는 냉장 창고, 원자재 보관 창고, 작업장 내 임시 보관 공간에서 선반이나 파레트 위에 포장을 유지한 채 해동해야 하며, 야외나 비위생적 공간에서의 해동은 금지됩니다.",
    "해동온도및시간": "해동은 냉장 조건(0~10℃)에서 14일 이내, 실온 조건(1~35℃)에서 2일 이내에 완료되어야 합니다.",
    "해동후관리": "해동 중인 원료는 시작/종료 시간 및 온도 조건이 기록된 명찰을 부착하여 관리해야 하며, 해동이 완료된 원료는 즉시 냉장 보관하고 최단 시간 내에 사용해야 합니다.",

    # 7. 검사 및 교정 관리 (검사 관리 기준서)
    "기기검교정": "온도계 및 비중계의 사내 교정 주기는 1회/6개월이며, 외부 공인 검사는 1회/년 실시합니다. 저울의 사내 교정은 1회/6개월, 공인 검사는 1회/2년입니다.",
    "병원성미생물검사": "중국 수출용 우유 및 원부자재는 황색포도상구균, 살모넬라 등 병원성 미생물에 대해 PCR(중합효소연쇄반응) 분석을 실시합니다.",
    "검사자숙련도": "미생물, 산도, 조지방 등의 검사자는 연 1회 이상 내부 숙련도 평가를 받으며, 평가 결과 '불만족' 시 재교육 및 재평가를 통과할 때까지 해당 검사에서 배제됩니다.",

    # 8. 제조시설 세척/소독 및 CIP 기준 (위생 및 제조시설 관리 기준서)
    "CIP세제온도": "라인별 CIP 세제(가성소다, 질산) 온도는 우유가공/발효유 45~70℃, 포장 65~75℃, 상온제품 70~80℃, 원유이송차량 45~65℃입니다. 열수 살균 온도는 95~100℃(상온제품은 125℃ 이상)로 관리됩니다.",
    "CIP검증": "CIP 완료 후에는 pH Paper를 이용하여 세제 잔류 검사를 100% 실시하며, 세척 효과성 검증은 연 1회 주기로 유기물(알러겐 키트) 및 무기물(필터링 육안 점검) 검사를 실시합니다.",
    "수세미구분": "제조 설비(식품 접촉면) 청소용 수세미와 작업장 바닥 청소용 수세미는 색상을 엄격히 구분하여 보관 및 관리합니다.",
    
    # 9. 설비 점검 및 폐기 (제조시설 관리 기준서)
    "설비시운전": "신규 설비 도입 시 시운전은 3단계로 진행됩니다. 1단계(전기/유압 작동 확인), 2단계(연속 사이클 부대설비 연계), 3단계(생산 제품 적합성 확인)를 거쳐 승인됩니다.",
    "설비폐기": "노후 설비 폐기는 부문장이 설비폐기 품의서를 작성하고, 총무부문장, 생산본부장 및 사장의 검토를 거쳐 최종적으로 법인본부장의 승인을 득한 후 폐기합니다.",

    # 10. 용수 관리 기준 (용수관리 기준서)
    "수질검사": "제품수(음용수) 및 지하수는 연 2회(반기별 1회) 공인검사기관에 검사를 의뢰하며, 자체 용수 검사는 월 1회(관능, pH, 대장균 등) 실시합니다.",
    "저수조관리": "저수조는 연 2회(6개월마다) 청소 및 소독을 실시해야 합니다.",
    "필터교체주기": "용수 처리 시설의 마이크로 필터는 3개월(또는 6개월)마다, 활성탄(카본) 필터 및 이온교환수지는 2년마다 교체 또는 재생해야 합니다.",

    # 11. 제품 회수 및 추적성 관리 기준 (제품회수 관리기준서)
    "회수등급별조치": "위해식품 발생 시, 1등급은 24시간 이내, 2등급은 48시간 이내, 3등급은 72시간 이내에 영업자에게 회수명령 공문을 전달해야 합니다. 회수명령을 받은 영업자는 1등급은 1일 이내, 2~3등급은 2일 이내에 관할 기관에 회수계획서를 보고해야 합니다.",
    "회수교육및훈련": "회수 업무와 관련하여 1회/년 이상 식품안전팀원 대상 교육을 실시하며, 2회/년 이상 모의회수(추적성) 훈련 주관합니다. 모의회수 훈련 시 원인 파악 및 추적 시간은 1시간 이내, 회수율은 100%를 목표로 합니다.",
    "추적성관리": "원부자재 입고부터 제품 출하까지 생산/작업/거래/검사 기록을 철저히 관리하여 추적성을 확보하며, 생산 및 판매 관련 서류는 2년간 보관합니다.",

    # 12. 보관 및 운반 관리 기준 (보관 및 운반 관리 기준서)
    "보관온도": "일반 원/부자재는 실온(1~35℃), 냉장 제품은 0~10℃(원유 0~4℃), 냉동 제품은 -18℃ 이하에서 보관합니다.",
    "운반온도관리": "차량 운송 시 상차 전 냉동기를 가동(10분 이상 예비냉각)하여 냉장은 0~10℃, 냉동은 -18℃ 이하를 유지해야 합니다.",
    "포장기라인정체제품": "별도 냉각 장치가 없는 포장기에서 제품이 정체될 경우, 2시간 이내에는 품질 검사 후 생산 여부를 판단하고, 2시간을 초과한 제품은 전량 폐기 조치합니다.",
    
    # 13. 가공두유 제조공정 및 HACCP PLAN
    "대두가공공정": "대두는 110~140℃(국산콩 220℃ 이상)에서 5분 이상 Heating하여 반할두로 제조하며, 70~90℃ 열수로 2분 이상 침지합니다. 1차 마쇄는 1,700rpm, 2차 마쇄는 85℃ 열수 투입 후 5,800rpm으로 진행합니다. 원심분리는 4,800rpm으로 작동합니다.",
    "CCP1B유액멸균_두유": "간접살균은 135~150℃에서 30~45초간 멸균하며, 직접살균은 143~153℃에서 3.6~4.4초간 멸균합니다. 135℃ 미만 시 자동 생산 중단, 30초 미만 살균 시 전량 폐기, 45초 초과 시 관능/이화학 검사 후 출고를 결정합니다.",
    "CCP2P여과_두유": "여과망 사이즈는 1.0Φ를 사용하며, 생산 시작 전/종료 후 여과망 사이즈 및 파손 여부를 점검합니다. 파손 확인 시 해당 생산분은 전량 폐기합니다.",
    "CCP3B포장지멸균_테트라팩": "테트라팩은 32~50% 농도의 과산화수소 침지 또는 eBeam 전류값 95~105%로 조사하여 멸균합니다. 설비(호기)별 과산화수소 Bath 통과(침지) 시간은 B호기(미드) 2.812초, C호기(프리즈마) 5.96초, D호기(미드) 2.812초입니다. 이탈 시 해당 제품은 폐기합니다.",
    "CCP3B포장지멸균_콤비팩": "콤비팩은 과산화수소 온도 250~290℃, 분사량 350~450μl/s 조건으로 분사하여 멸균합니다. 온도 및 분사량 이탈 시 생산 중단 후 점검하며 이탈된 제품은 폐기합니다.",
    "포장속도및탱크": "무균포장기 속도는 설비별로 6,000~40,000 pak/h로 다양하며, Aseptic Tank는 1.0~2.0 cm²/Hg 압력을 유지합니다.",
    "자석봉관리": "이물 제거를 위해 정선/석발 및 여과 공정에서 10,000 가우스 이상의 영구자석을 이용합니다.",

    # 14. 멸균유 제조공정 및 HACCP PLAN (우유, 강화우유, 가공유)
    "원유수유및여과": "0~4℃ 원유는 60 mesh(A2원유는 1차 40 mesh, 2차 100 mesh 타공) 여과망으로 이물을 제거하며, 1일 2회 분해 점검을 실시합니다. 원심 청정기는 5,300~6,000 rpm으로 작동합니다.",
    "유당분해우유공정": "유당분해 효소를 접종하여 4~6℃에서 24~27시간 배양하며, 튜블러 멸균 공정에서 135~150℃, 3.8초 이상 멸균합니다.",
    "저지방표준화공정": "탈지유와 원유를 혼합하여 유지방 함량을 0.8~1.2%(저지방), 3.1~3.5%(표준화)로 맞추며, 10,000 rpm의 크림분리기를 사용합니다.",
    "멸균유CCP1B_가공유": "가공유류(UHT) 유액멸균 한계기준은 멸균온도 135~150℃, 멸균시간 30~37초간입니다.",
    "멸균유CCP1B_우유강화유": "우유, 강화유, 가공유 일부제품의 UHT 한계기준은 멸균온도 135~150℃, 멸균시간 10~14초간입니다. HTST의 경우 72~75℃에서 15초 이상 멸균합니다.",
    "멸균유CCP1B_유크림": "유크림의 살균 한계기준은 92~100℃에서 30초 이상 살균(유량 500 L/hr 이하)하는 것입니다.",
    "멸균유CCP1B_중국조제유": "중국 수출용 조제유(병우유)의 한계기준은 127~130℃에서 15초 이상 살균하는 것입니다.",
    "멸균유CCP2P_여과": "여과 공정 한계기준은 포장 타입별로 우유류 카톤포장 100Mesh, 병포장 120Mesh, 유크림 80Mesh 여과망을 사용하며, 파손 여부를 확인합니다.",

    # 15. 발효유 제조공정 및 HACCP PLAN (발효유, 농후발효유)
    "발효유배양공정": "배양탱크(6,000L 등)에서 4종의 유산균과 유당분해효소를 접종하여 38~42℃(여름 38℃, 봄/가을 40℃, 겨울 42℃)에서 6~8시간 배양한 후 10℃ 이하(그릭요거트는 30℃)로 냉각합니다.",
    "발효유CCP1B_배양액살균": "배양액 살균(CCP-1B) 한계기준은 95~110℃에서 4분 15초 이상(유량 7,000 L/hr 미만)입니다. 살균온도가 정상온도로 복귀하지 못할 시 살균을 정지시키고 설비 분해 정비 후 재 CIP 및 살균합니다.",
    "발효유CCP2P_여과": "여과(CCP-2P) 한계기준은 포장 타입별로 병 포장 80Mesh, 호상발효유 60Mesh, 카톤 포장 50Mesh 여과망 사이즈 및 파손 여부입니다. 작업 개시 전/종료 후 1회씩 육안 점검합니다.",
    "발효유CCP3P_금속검출기": "호상발효유 및 병포장 라인의 금속검출기(CCP-3P) 한계기준은 Fe 1.5mm, SUS 2.5mm 이상 불검출입니다. 작업 시작 전/종료 후 및 2시간 간격으로 시편을 통과시켜 모니터링합니다.",

    # 16. 원액두유 제조공정 및 HACCP PLAN
    "원액두유CCP1P_여과": "원액두유 여과(CCP-1P) 한계기준은 여과망 사이즈 30Mesh 및 파손 여부입니다. 작업 개시 전/종료 후 육안 점검을 실시하며 파손 시 생산분을 전량 폐기합니다.",
    "원액두유CCP2B_두유액살균": "원액두유 살균(CCP-2B) 한계기준은 살균온도 100~130℃, 살균시간 3초 이상(유량 4,500 L/hr 이하)입니다. 3초 미만으로 살균된 유액은 폐기합니다.",

    # 17. 음료 제조공정 및 HACCP PLAN
    "음료균질": "균질 시 돌(파인, 망고) 및 유산균음료는 150 bar, 스위플(사과, 레드오렌지, 샤인머스캣) 제품은 200 bar의 압력으로 균질합니다.",
    "음료추출공정": "차(Tea) 추출 공정은 70~90℃ 열수로 20~50분간 추출하며, 백 필터(5μm) 및 마이크로 필터(1μm)를 사용합니다.",
    "음료CCP1B_과채음료류": "과채음료, 과채주스, 혼합음료, 유산균음료, 액상차의 유액멸균(CCP-1B) 한계기준은 90~130℃(또는 135~150℃)에서 30~37초간입니다.",
    "음료CCP1B_혼합음료특정제품": "혼합음료(스위플 레드오렌지, 샤인머스캣, 과일펀치 제외)와 커피의 경우, 멸균 온도 135~150℃, 시간 30~37초간으로 관리하며, A2프로틴 오리지널의 경우 143~153℃, 3.6~4.4초간으로 관리합니다.",
    "음료CCP1B_커피": "커피의 유액멸균(CCP-1B) 한계기준은 135~150℃에서 10~14초간입니다.",
    "음료CCP2P_여과": "음료류 여과(CCP-2P) 한계기준은 여과망 1.0Φ 사용 및 파손 여부 확인입니다.",
    "음료CCP3B_포장지멸균": "테트라팩은 과산화수소 농도 32~50% 또는 eBeam 전류값 95~105%로, 콤비블럭은 과산화수소 온도 250~290℃, 분사량 350~450μl/s(150~250μl/s 등 제품별 상이)로 포장지 멸균을 관리합니다.",

    # 18. 집유장 제조공정 및 HACCP PLAN (집유장 관리 기준서)
    "집유장원유검사": "원유 입고 시 관능, 비중(1.028~1.034), 알콜(70% 음성), 진애(2.0mg 이하), 산도(0.14% 이하), 조지방(3.2% 이상), 세균발육억제물질(음성), 가수/빙점(-508 이하) 등을 검사하며, A2 원유는 A2 단백질 100% 여부를 추가 확인합니다.",
    "집유장원유저장": "원유의 보관 및 유통 온도는 농가 0~4℃, 탱크로리 0~7℃, 저유조 0~7℃로 관리됩니다.",
    "집유장여과및청정": "수유 시 60 mesh 여과망으로 이물을 제거하며(1일 2회 분해 점검), 일반 원유는 5,300~6,000 rpm의 청정기를 거치나 A2 및 무항생제 원유는 청정 공정을 제외합니다.",
    "집유차량세척": "집유 차량은 1일 2회(오전/오후 수유 후) 열수 CIP를 실시하고, 2일에 1회 약품 CIP를 실시합니다.",
    "집유장CCP1B_원유저장": "원유저장(CCP-1B) 한계기준은 저장온도 0~7℃입니다. 2시간 간격으로 온도를 모니터링하며, 한계기준 이탈 시 냉각수 온도(6℃ 이하)를 확인하고, 알콜/산도/pH/관능검사 등을 통해 법적 기준(10℃ 이하) 적합 시 선출고 또는 폐기 여부를 결정합니다.",
    "집유장탱크수량": "집유 및 원유 보관에 운용되는 원유저장탱크는 100,000L 4기, 50,000L 4기, 30,000L 3기, 6,000L 3기로 총 14기입니다.",

    # 19. 환자용식품 제조공정 및 HACCP PLAN
    "환자용식품가공공정": "대두 Heating/탈피는 110~140℃에서 5분 이상 실시하며, 침지는 90℃ 열수로 1분 이상 진행합니다(고형분 9% 이상 제품은 예외). 마쇄는 1차 1,700 rpm, 2차 85℃ 열수 투입 후 5,800 rpm으로 실시하고, 3,500 rpm으로 원심분리합니다. 균질 시 압력은 300 bar 이하로 관리됩니다.",
    "환자용식품CCP1B_유액멸균": "간접살균은 135~150℃에서 30~37초간, 직접살균은 143~153℃에서 3.6~8.8초간 멸균합니다. 한계온도 이탈 시 자동 정지 후 CIP 및 장치 멸균을 재실시하며, 30초/3.6초 미만 살균 시 전량 폐기, 한계시간 초과 시 관능 및 이화학 검사 후 출고를 결정합니다.",
    "환자용식품CCP2P_여과": "여과(CCP-2P) 한계기준은 여과망 사이즈 1.0Φ 및 파손 여부이며, 작업 개시 전/종료 후 육안으로 점검하여 이탈 시 해당 생산분을 전량 폐기합니다.",
    "환자용식품CCP3B_포장지멸균": "테트라팩은 과산화수소 농도 32~50% 또는 eBeam 전류값 95~105%로, 콤비블럭은 과산화수소 온도 250~290℃, 분사량 350~450μl/s로 포장지를 멸균하며 이탈된 제품은 즉각 폐기 조치합니다.",

    # 20. 작업장 평면도 및 동선 관리
    "작업장동선및레이아웃": "작업장 평면도에 따르면 작업자 이동 경로(녹색), 폐수 이동 경로(청색), 원유 이송 흐름도(분홍색), 탱크로리 CIP 흐름도(보라색)가 명확히 분리되어 교차오염을 방지하고 있습니다. 주요 구역은 수유실, 수유 검사실, 원유취급실, 우유 가공, 발효유 가공 구역 등으로 철저히 구획되어 있습니다."
}

# ==========================================
# [0-1] 연세유업 사내 그룹웨어 참조/열람 문서함 키워드 맵핑 사전
# 주임님께서 제공해주신 실제 결재문서 리스트(약 50개 항목) 100% 매칭 완료
# ==========================================
GW_CATEGORY_MAP = {
    "측정기기 공인": "측정기기 공인기관 검·교정 결과",
    "자체 측정기기": "자체 측정기기 검·교정결과",
    "카톤팩 과산화수소": "카톤팩 과산화수소 잔류여부 검증 결과",
    "부적합": "품질(제품, 원·부자재) 부적합 현황 보고",
    "자력기기": "자력기기 점검 결과",
    "상업적 무균": "상업적 무균테스트 결과 보고서",
    "무균테스트": "상업적 무균테스트 결과 보고서",
    "콤비팩 과산화수소": "콤비팩 과산화수소 잔류여부 검증 결과",
    "유량계": "유량계 공인기관 교정 결과",
    "테트라팩 과산화수소": "테트라팩 과산화수소 잔류여부 검증 결과",
    "알러겐": "알러겐 및 미생물 검증 결과",
    "손 위생": "작업자 손 위생검사 결과",
    "작업자 손": "작업자 손 위생검사 결과",
    "손위생": "작업자 손 위생검사 결과",
    "배지 수불부": "병원성 미생물 배지 수불부",
    "병원성": "병원성 미생물 배지 수불부",
    "자가품질": "자가품질검사 검사결과",
    "우유 포장": "우유 포장 공정관리 일보",
    "대리점 클레임": "대리점 클레임 현황",
    "개선 대책": "문제점 개선 대책 결과 보고",
    "소비자 클레임": "소비자 클레임 현황(제조단계, 공장)",
    "시생산": "시생산 결과보고",
    "온도센서": "현장 온도센서 공인기관 검·교정 결과",
    "본생산": "본생산 결과 보고",
    "상온 OEM": "상온제품 OEM 입고 검수서",
    "발효유 포장": "발효유 포장 공정관리 일보",
    "발효유 공정": "발효유 공정관리 일보",
    "중국 수출": "중국 수출 우유 제품검사 일보",
    "음료류 일반": "음료류 일반검사 일보",
    "두유류 일반": "두유류 일반검사 일보",
    "가공유": "가공유(멸균) 일반검사 일보",
    "우유류 일반": "우유류(멸균) 일반검사 일보",
    "우유류(멸균)": "우유류(멸균) 일반검사 일보",
    "클린벤치": "클린벤치 낙하세균 검사 결과",
    "부자재": "부자재 입고 검수서",
    "소비기한 경과": "우유류 냉장 보관 소비기한 경과 후 검사 결과",
    "압축공기": "압축공기 미생물검사 결과",
    "응결수": "응결수 미생물검사 결과",
    "표면오염도": "표면오염도 검사 결과",
    "낙하세균": "낙하세균 검사 결과", 
    "탈지분유": "탈지분유 입고 검수 일보",
    "세척": "세척.소독제 농도 검증 결과",
    "소독제": "세척.소독제 농도 검증 결과",
    "소비기한 만료": "상온제품 소비기한 만료 검증 결과",
    "대두": "대두 입고 검수 일보",
    "조도": "온/습도, 조도 측정 결과",
    "온습도": "온/습도, 조도 측정 결과",
    "온/습도": "온/습도, 조도 측정 결과",
    "용수": "용수 검사 성적서",
    "수질": "용수 검사 성적서",
    "원자재": "원자재 입고 검수서",
    "미생물실": "미생물실 낙하세균 검사 결과",
    "발효유 제품": "발효유 제품검사 일보",
    "OEM 제품": "OEM 제품검사 일보",
    "미생물 검사": "미생물 검사 일보",
    "미생물검사": "미생물 검사 일보",
    "우유류 제품": "우유류 제품검사 일보",
    "두유액 일반": "두유액(원액두유) 일반 검사 일보",
    "상온 공정": "상온제품 공정 관리 일보",
    "상온제품 공정": "상온제품 공정 관리 일보",
    "상온 배양": "상온제품 배양검사 일보",
    "상온제품 배양": "상온제품 배양검사 일보",
    "두유액 공정": "두유액(원액두유) 공정관리 일보",
    "우유류 샘플": "우유류 샘플 상온검사일보",
    "병포장기": "병포장기 제품 상온검사 일보"
}

# ==========================================
# [1] 시스템 기본 설정 및 엔터프라이즈 UI CSS
# ==========================================
st.set_page_config(page_title="AI 현장심사 포털", page_icon="🛡️", layout="wide")

# 세션 상태 초기화 (화면이 다시 그려져도 검색 상태 유지)
if "search_done" not in st.session_state:
    st.session_state.search_done = False
    st.session_state.found_files = []
    st.session_state.search_keyword = ""
    st.session_state.search_question = ""
    st.session_state.query_text = ""
    st.session_state.final_briefing = ""
    st.session_state.last_file_id = ""
    st.session_state.preview_url = ""
    st.session_state.view_url = ""
    st.session_state.is_voice = False
    st.session_state.last_audio_hash = None

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

MODEL_NAME = "models/gemini-3.8-flash"
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
    manual_query = st.text_input("서류명 입력:", placeholder="예: 부자재, 살균온도", label_visibility="collapsed")
    manual_submit = st.button("AI 브리핑 및 문서검색 🚀", use_container_width=True)

# ==========================================
# [4] 속도 최적화 구글 드라이브 다중 검색 코어
# ==========================================
def get_drive_service():
    creds = get_credentials()
    if creds:
        return build('drive', 'v3', credentials=creds)
    return None

@st.cache_data(ttl=3600)
def get_target_folder_ids(_service, root_folder_id):
    folders = [root_folder_id]
    def fetch_children(parent_id):
        q = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = _service.files().list(q=q, fields="files(id)").execute()
        for item in res.get('files', []):
            folders.append(item['id'])
            fetch_children(item['id'])
    try:
        fetch_children(root_folder_id)
    except Exception as e:
        pass
    return folders

def search_multiple_drive_files(service, keyword, root_folder_id):
    try:
        target_folders = get_target_folder_ids(service, root_folder_id)
        
        if target_folders:
            parents_query = " or ".join([f"'{fid}' in parents" for fid in target_folders])
            query = f"fullText contains '{keyword}' and trashed = false and ({parents_query})"
        else:
            query = f"fullText contains '{keyword}' and trashed = false and '{root_folder_id}' in parents"

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

def execute_search_and_extract(query_text=None, audio_bytes=None, is_voice_active=False):
    service = get_drive_service()
    if not service: return

    st.session_state.search_done = True
    st.session_state.is_voice = is_voice_active
    st.session_state.query_text = query_text if query_text else ""
    st.session_state.last_file_id = "" 
    
    t_start = time.time()
    try:
        model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config={"temperature": 0.0})
    except:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config={"temperature": 0.0})

    with st.spinner("AI: 심사관 의도 정밀 분석 중..."):
        intent_prompt = """
        사용자 요청에서 구글 드라이브 문서 검색을 위한 가장 핵심적인 명사 단어 1~2개만 추출하세요. 
        '기준서', '문서'처럼 너무 포괄적인 단어는 절대 사용하지 말고, 질문의 대상을 구체적으로 지칭하는 단어(예: '클린벤치', '알러겐', '부자재', '작업자 손', '온도센서', '자력기기')를 도출하세요.
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

        st.session_state.search_keyword = keyword
        st.session_state.search_question = question

    found_files = search_multiple_drive_files(service, keyword, DRIVE_FOLDER_ID)
    st.session_state.found_files = found_files
    
    if found_files:
        st.success(f"✅ 총 **{len(found_files)}개**의 문서를 찾았습니다. (소요시간: {time.time() - t_start:.1f}초)")

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
            audio_bytes = audio_value.getvalue()
            audio_hash = hash(audio_bytes)
            if st.session_state.last_audio_hash != audio_hash:
                st.session_state.last_audio_hash = audio_hash
                execute_search_and_extract(audio_bytes=audio_bytes, is_voice_active=True)
    else:
        st.markdown("### ⌨️ 텍스트 기반 AI 검색 (정숙 모드)")
        st.info("사이드바의 '보조 텍스트 검색' 창에 검색어를 입력하고 엔터를 누르세요.")

    if manual_submit and manual_query:
        execute_search_and_extract(query_text=manual_query, is_voice_active=use_voice_mode)

    if st.session_state.search_done:
        keyword = st.session_state.search_keyword
        question = st.session_state.search_question
        found_files = st.session_state.found_files
        service = get_drive_service()
        
        st.info(f"🔍 AI 추출 키워드: **{keyword}** / 📝 추가 질문: **{question if question else '단순 열람'}**")
        
        if not found_files:
            st.warning(f"⚠️ 구글 드라이브(방문심사 폴더)에서 '{keyword}' 관련 서류를 찾지 못했습니다. 지식베이스를 기반으로만 답변합니다.")
            
            if st.session_state.last_file_id != "KB_ONLY":
                with st.spinner("🤖 AI가 규정 지식베이스를 기반으로 답변을 작성 중입니다..."):
                    kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
                    analysis_prompt = f"""
                    당신은 연세유업 아산공장 스마트 해썹(HACCP) 심사 대응 전문 AI입니다.
                    아래의 [사내 규정 초정밀 지식베이스]를 기반으로 심사관의 질문에 즉각 답변하세요.
                    [사내 규정 초정밀 지식베이스]\n{kb_str}\n
                    [심사관 요청/질문]\n{question if question else st.session_state.query_text}
                    [행동 지침]
                    1. 질문이 살균 온도/시간, 여과망 사이즈 등 수치를 묻는다면 명확한 숫자로 즉시 대답하세요.
                    2. 정중하고 전문적인 톤앤매너를 유지하세요.
                    """
                    try:
                        model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config={"temperature": 0.0})
                        response = model.generate_content([analysis_prompt])
                        st.session_state.final_briefing = response.text
                    except Exception as e:
                        st.session_state.final_briefing = f"오류 발생: {e}"
                    
                    st.session_state.last_file_id = "KB_ONLY"
                    st.session_state.preview_url = ""
                    
            st.write("🤖 **AI 브리핑 결과:**")
            st.success(st.session_state.final_briefing)

        else:
            file_options = {f['name']: f for f in found_files}
            
            if len(found_files) > 1:
                selected_file_name = st.selectbox("📂 조회할 문서를 선택하세요:", list(file_options.keys()))
            else:
                selected_file_name = list(file_options.keys())[0]
                st.markdown(f"**📂 자동 선택된 문서:** {selected_file_name}")
                
            top_file = file_options[selected_file_name]
            file_id = top_file['id']
            
            if st.session_state.last_file_id != file_id:
                st.session_state.preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
                st.session_state.view_url = top_file['webViewLink']
                
                with st.spinner(f"📥 '{top_file['name']}' 문서를 다운로드 및 AI 분석 장전 중..."):
                    gemini_file = None
                    tmp_doc_path = ""
                    try:
                        file_bytes = download_file_bytes(service, file_id)
                        file_ext = ".pdf" if "pdf" in top_file.get('mimeType', '').lower() else ".txt"
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_doc:
                            tmp_doc.write(file_bytes)
                            tmp_doc_path = tmp_doc.name
                        
                        gemini_file = genai.upload_file(path=tmp_doc_path)
                        kb_str = json.dumps(KNOWLEDGE_BASE, ensure_ascii=False, indent=2)
                        
                        analysis_prompt = f"""
                        당신은 연세유업 아산공장 스마트 해썹(HACCP) 심사 대응 전문 AI입니다.
                        [사내 규정 초정밀 지식베이스]\n{kb_str}\n
                        [심사관 요청/질문]\n{question if question else st.session_state.query_text}
                        [행동 지침]
                        1. 수치를 묻는 질문은 지식베이스의 팩트를 최우선 인용하여 명확한 숫자로 대답하세요.
                        2. 첨부된 문서 내용을 바탕으로 심사관 질문에 부합하는 요약을 덧붙이세요.
                        3. 정중하고 전문적인 톤앤매너를 유지하세요.
                        """
                        model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config={"temperature": 0.0})
                        response = model.generate_content([gemini_file, analysis_prompt])
                        st.session_state.final_briefing = response.text
                        
                    except Exception as e:
                        st.session_state.final_briefing = f"AI 분석 중 오류가 발생했습니다: {str(e)}"
                    finally:
                        if gemini_file:
                            genai.delete_file(gemini_file.name)
                            os.remove(tmp_doc_path)
                            
                st.session_state.last_file_id = file_id 

            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"🔗 **[원본 새창에서 열기]({st.session_state.view_url})**")
                st.components.v1.iframe(st.session_state.preview_url, height=600, scrolling=True)
            with col2:
                st.write("🤖 **AI 브리핑 결과:**")
                st.success(st.session_state.final_briefing)

        # 3. 사내 그룹웨어 참조/열람 문서함 키워드 매칭 검색 링크 생성 (URL 롤백 완료)
        st.markdown("---")
        st.markdown("### 🏢 사내 그룹웨어(전자결재) 연동 검색")
        
        gw_search_keyword = keyword
        
        # 사내 공식 키워드 매칭 로직
        for key, official_name in GW_CATEGORY_MAP.items():
            if key in keyword or key in st.session_state.query_text:
                gw_search_keyword = official_name
                break
                
        encoded_keyword = urllib.parse.quote(gw_search_keyword)
        
        # 💡 주임님께서 알려주신 '참조/열람 문서함' 전체 검색 URL 방식으로 완벽 롤백
        gw_search_url = f"https://gw.yonseidairy.com/app/approval/doclist/viewer/all?page=0&offset=20&property=document.draftedAt&direction=desc&searchtype=title&keyword={encoded_keyword}&fromDate=&toDate=&duration=all"
            
        st.info(f"💡 그룹웨어 문서함에서 **'{gw_search_keyword}'** 관련 결재 문서를 확인하시겠습니까?")
        st.markdown(f"🔗 **[연세유업 전자결재함 '{gw_search_keyword}' 검색 결과 바로가기 (클릭)]({gw_search_url})**")

        if st.session_state.is_voice:
            autoplay_audio(st.session_state.final_briefing)
            st.session_state.is_voice = False 

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
        st.warning(f"⚠ [갱신 안내] 30일 이내에 만료되는 서류가 {warning_docs}건 있습니다.")

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
