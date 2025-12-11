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
python main.py [options]
```
### 실행 옵션 (Options)
- `(옵션 없음)`: 단순 조회 모드 (매매 실행 X)
- `--buy`: 매수 주문 실행 활성화
- `--sell`: 매도 주문 실행 활성화
- `--mode [split|market]`: 매매 전략 선택 (기본값: `split`)
  - `split`: 분할 매매 (지정가 3분할)
  - `market`: 현재가 매매 (시장가/최근체결가 100%)

### 실행 예시 (Examples)

| 시나리오 | 명령어 | 동작 설명 |
| :--- | :--- | :--- |
| **단순 조회** | `python main.py` | 매매 없이 계좌/포트폴리오 상태만 확인합니다. |
| **매수만 실행**<br>(분할) | `python main.py --buy` | 리밸런싱 결과 '매수'가 필요한 종목만 **3분할** 주문합니다.<br>('매도' 종목은 무시됩니다) |
| **매수만 실행**<br>(현재가) | `python main.py --buy --mode market` | 리밸런싱 결과 '매수'가 필요한 종목만 **현재가로 100%** 주문합니다.<br>('매도' 종목은 무시됩니다) |
| **매도만 실행**<br>(분할) | `python main.py --sell` | 리밸런싱 결과 '매도'가 필요한 종목만 **3분할** 주문합니다. |
| **전체 실행** | `python main.py --buy --sell` | 매수와 매도 주문을 모두 실행합니다. |

## 자동 매매 로직 (Auto Trading Logic)

### 1. 분할 매매 전략 (Split Strategy) - Default
지정가 주문을 통해 체결 확률과 가격 효율을 동시에 추구합니다.
- **매수 (Buy)**: 매수 1호가(33%), 매수 2호가(33%), 매수 3호가(34%) 분할 주문
- **매도 (Sell)**: 매도 1호가(33%), 매도 2호가(33%), 매도 3호가(34%) 분할 주문

### 2. 현재가 매매 전략 (Market Strategy)
빠른 체결을 위해 현재가(최근 체결가) 기준으로 전량을 주문합니다.
- **주문 가격**: 현재가 (`stck_prpr`) 또는 최우선 호가
- **주문 수량**: 목표 수량 100%

### 3. 연금 계좌 지원 (Pension Account Support)
