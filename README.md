# 한국투자증권 리밸런서 (KIS Rebalancer)

한국투자증권(Korea Investment & Securities)의 Open API를 활용하여 계좌 잔고를 조회하고, 목표 포트폴리오 비중(`portfolio.yaml`)에 맞춰 리밸런싱(매수/매도) 계획을 제안해 주는 파이썬 프로그램입니다.

## 주요 기능
- **계좌 조회**: 총 자산, 예수금, 평가 금액, 총 손익 및 수익률 조회.
- **보유 종목 현황**: 종목별 수량, 평단가, 현재가, 수익률, **현재 비중(Portion %)** 표시.
- **리밸런싱 계산**: `portfolio.yaml`에 정의된 목표 비중과 현재 자산을 비교하여 추가 매수하거나 매도해야 할 수량을 자동으로 계산.
- **다중 포트폴리오 & 계좌 지원** (New):
    - 여러 개의 포트폴리오 파일(`portfolio_*.yaml`) 관리 및 선택 실행.
    - 포트폴리오별로 다른 계좌(CANO) 연동 가능.

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
   기본 자격 증명 정보를 설정합니다.
   ```bash
   cp .env.example .env
   ```
   **`.env` 내용 수정**:
   - `APP_KEY`, `APP_SECRET`: 발급받은 키.
   - `CANO`: 기본 계좌번호 (8자리).
   - `ACNT_PRDT_CD`: 상품코드 (01).
   - `URL_BASE`: 실전/모의투자 주소.

4. **포트폴리오 설정 (`portfolio.yaml`)**
   목표 종목과 비중을 설정합니다.

   **기본 형식**:
   ```yaml
   portfolio:
     - code: "005930"
       name: "삼성전자"
       portion: 0.20
   ```

   **[고급] 계좌별 포트폴리오 관리 (Multi-Account)**:
   별도의 파일(예: `portfolio_pension.yaml`, `portfolio_isa.yaml`)을 만들고, `config` 섹션을 추가하여 계좌 정보를 오버라이드할 수 있습니다.
   ```yaml
   # portfolio_isa.yaml 예시
   config:
     cano: "12345678"     # 이 포트폴리오는 이 계좌번호를 사용 (AppKey는 .env 공유)
     acnt_prdt_cd: "01"
     
   portfolio:
     - code: "..."
       name: "..."
       portion: 1.0
   ```

## 실행 (Usage)

```bash
python main.py [options]
```

### 포트폴리오 선택 (Portfolio Selection)
1. **대화형 선택**:  
   `python main.py` (또는 `--buy`, `--sell` 옵션 포함)를 실행했을 때 `portfolio*.yaml` 파일이 여러 개라면 선택 메뉴가 뜹니다.  
   **Note**: 이때 미리 입력한 `--buy` 등의 옵션은 **선택한 포트폴리오에 그대로 적용**됩니다.
2. **직접 지정**:  
   ```bash
   python main.py --portfolio portfolio_isa.yaml
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
| **단순 조회** | `python main.py` | 포트폴리오를 선택하고, 매매 없이 계좌 상태와 리밸런싱 계획만 확인합니다. |
| **특정 포트폴리오 조회** | `python main.py --portfolio portfolio_isa.yaml` | `portfolio_isa.yaml` (및 설정된 계좌)을 로드하여 조회합니다. |
| **매수만 실행**<br>(분할) | `python main.py --buy` | 리밸런싱 결과 '매수'가 필요한 종목만 **3분할** 주문합니다. |
| **ISA 계좌 전체 매매** | `python main.py --portfolio portfolio_isa.yaml --buy --sell` | ISA 포트폴리오를 기준으로 매수/매도 주문을 모두 실행합니다. |

## 웹 대시보드 (Streamlit Dashboard) [NEW]
터미널이 아닌 **웹 브라우저**에서 시각적으로 포트폴리오를 관리할 수 있습니다.

### 실행 방법
```bash
python -m streamlit run app.py
```
실행 후 브라우저가 자동으로 열리며, 로컬 주소(예: `http://localhost:8501`)로 접속됩니다.

### 주요 기능
- **시각화**: 자산 구성(Pie Chart), 보유 목록 현황판.
- **인터랙티브 테이블**: 목표 비중과 괴리율을 색상으로 구분하여 표시.
- **GUI 실행**: 복잡한 명령어 입력 없이 버튼 클릭만으로 `Buy/Sell` 실행 가능.
- **실시간 로그**: 실행 결과가 터미널에 실시간으로 출력됩니다.

> **Note**: `Streamlit` 실행 시에도 `portfolio.yaml`의 설정과 `.env`의 인증 정보를 그대로 사용합니다.

## 자동 매매 로직 (Auto Trading Logic)

### 1. 분할 매매 전략 (Split Strategy) - Default
지정가 주문을 통해 체결 확률과 가격 효율을 동시에 추구합니다.
- **매수 (Buy)**: 매수 1호가(33%), 매수 2호가(33%), 매수 3호가(34%) 분할 주문
- **매도 (Sell)**: 매도 1호가(33%), 매도 2호가(33%), 매도 3호가(34%) 분할 주문

### 2. 현재가 매매 전략 (Market Strategy)
빠른 체결을 위해 현재가(최근 체결가) 기준으로 전량을 주문합니다.
- **주문 가격**: 현재가 (`stck_prpr`) 또는 최우선 호가
- **주문 수량**: 목표 수량 100%

### 3. 미체결 주문 자동 취소 (Auto-Cancel)
리밸런싱을 위한 주문 실행(`--buy` 또는 `--sell`) 전, **기존에 남아있는 모든 미체결 주문(Open Orders)을 자동으로 조회하고 취소**합니다.
- 이를 통해 자산/자금의 이중 잠김을 방지하고, 중복 주문 없이 깔끔한 상태에서 리밸런싱을 수행합니다.

### 4. 연금/토큰 관리
- **토큰 관리**: App Key 앞자리를 사용한 별도 토큰 파일(`token_XXXXXX.json`)을 생성하여, 여러 포트폴리오/계좌 간 인증 충돌 없이 안전하게 관리됩니다.

## 주의사항 (Limitations)
- **IRP/퇴직연금 계좌 (상품코드 29)**: 현재 한국투자증권 Open API에서는 **IRP 계좌(29)에 대한 매수/매도 주문 API를 지원하지 않는 것**으로 파악됩니다 (`OPSQ0002 : 없는 서비스 코드`). 단순 잔고 조회는 가능하지만, 주문 실행 시 에러가 발생할 수 있습니다.
