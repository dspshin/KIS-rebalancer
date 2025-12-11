# 한국투자증권 리밸런서 (KIS Rebalancer)

한국투자증권(Korea Investment & Securities)의 Open API를 활용하여 계좌 잔고를 조회하고, 목표 포트폴리오 비중(`portfolio.yaml`)에 맞춰 리밸런싱(매수/매도) 계획을 제안해 주는 파이썬 프로그램입니다.

## 주요 기능
- **계좌 조회**: 총 자산, 예수금, 평가 금액, 총 손익 및 수익률 조회.
- **보유 종목 현황**: 종목별 수량, 평단가, 현재가, 수익률, **현재 비중(Portion %)** 표시.
- **리밸런싱 계산**: `portfolio.yaml`에 정의된 목표 비중과 현재 자산을 비교하여 추가 매수하거나 매도해야 할 수량을 자동으로 계산.

## 사전 준비
1. **Python 3.10+** 설치.
2. **한국투자증권 Open API 신청** (App Key, App Secret 발급).
   - [KIS Developers](https://apiportal.koreainvestment.com/) 참조.
   - 실전투자 또는 모의투자 계좌 필요.

## 설치 및 설정 (Installation & Setup)

1. **프로젝트 클론 및 이동**
   ```bash
   git clone <repository-url>
   cd hantu_rebalancer
   ```

2. **가상환경 생성 및 패키지 설치**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **환경 변수 설정 (`.env`)**
   `.env.example` 파일을 복사하여 `.env` 파일을 생성하고 정보를 입력합니다.
   ```bash
   cp .env.example .env
   ```
   **`.env` 내용 수정**:
   - `APP_KEY`: 발급받은 App Key
   - `APP_SECRET`: 발급받은 App Secret
   - `CANO`: 계좌번호 8자리 (하이픈 제외)
   - `ACNT_PRDT_CD`: 상품코드 2자리 (보통 01)
   - `URL_BASE`: 실전/모의투자 주소 확인

4. **포트폴리오 설정 (`portfolio.yaml`)**
   본인이 목표로 하는 종목과 비중을 설정합니다.
   ```yaml
   portfolio:
     - code: "005930"
       name: "삼성전자"
       portion: 0.20  # 20% 비중
     # ...
   ```

## 실행 (Usage)
```bash
python main.py
```

## 실행 결과 예시
```text
[Account Summary] : 12345678-01
Total Asset: 10,000,000 KRW
Deposit: 5,000,000 KRW
...

[Holdings]
... (보유 종목 테이블) ...

[Rebalancing Plan]
+--------+----------+----------+------------+------------+---------+--------+----------+
|  Code  |   Name   | Target % | Target Amt | Current Amt|   Diff  | Action | Est. Qty |
+--------+----------+----------+------------+------------+---------+--------+----------+
| 005930 | 삼성전자 |   20.0%  | 2,000,000  | 1,500,000  | 500,000 |  BUY   |  7 qty   |
+--------+----------+----------+------------+------------+---------+--------+----------+
```

## 자동 매매 로직 및 파라미터 (Auto Trading Logic & Parameters)

이 프로그램은 `--trade` 옵션 사용 시 다음과 같은 로직으로 자동 매매를 수행합니다.

### 1. 분할 매수 전략 (Split Buying)
매수 주문 시 체결 확률을 높이고 시장 충격을 완화하기 위해 **매수 1~3호가**에 나누어 주문을 접수합니다.
- **1차 (33%)**: 매수 1호가 (최우선 매수대기 가격)
- **2차 (33%)**: 매수 1호가 - 1틱 (매수 2호가)
- **3차 (34%)**: 매수 1호가 - 2틱 (매수 3호가)

### 2. 연금 계좌 지원 (Pension Account Support)
본 프로그램은 일반 주식 계좌뿐만 아니라 **개인연금/퇴직연금** 계좌의 조회 및 주문을 지원합니다.
연금 계좌는 일반 계좌와 다른 별도의 API 파라미터를 사용하며, 코드 내에서 계좌 타입에 따라 자동으로 처리됩니다.

- **미체결 내역 조회 (TR_ID: TTTC2201R)**
  - `USER_DVSN_CD`: **"01"** (개인 고객 구분)
  - `CCLD_NCCS_DVSN`: **"02"** (미체결 내역만 조회)
  - 조회 기간은 **최근 30일**로 자동 설정됩니다.

### 3. 현재가 매수 전략 (Market Price Buy)
`--trade` 대신 `--market-buy` 옵션을 사용하면 분할 매수 없이 **현재가(최근 체결가)** 기준으로 목표 수량 100%를 한 번에 주문합니다.
- **주문 가격**: 현재가 (`stck_prpr`)
- **주문 수량**: 목표 수량 100%

## 주의사항
- `--trade` 또는 `--market-buy` 옵션을 붙여 실행할 경우 **실제 매수/매도 주문이 전송**됩니다.
- 토큰은 `token.json`에 임시 저장되어 재사용됩니다.
