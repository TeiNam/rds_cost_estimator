"""
Pydantic v2 데이터 모델 정의 모듈.

이 모듈은 RDS Cost Estimator에서 사용하는 모든 데이터 모델을 정의합니다.
- 열거형(Enum): InstanceFamily, MigrationStrategy, PricingType
- 핵심 모델: InstanceSpec, CostRecord, CostRow, CLIArgs, ParsedDocumentInfo
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class InstanceFamily(str, Enum):
    """지원하는 RDS 인스턴스 패밀리 열거형."""

    R6I = "r6i"
    R7I = "r7i"
    R7G = "r7g"


class MigrationStrategy(str, Enum):
    """이관 전략 열거형.

    - REPLATFORM: 애플리케이션 코드 변경 없이 RDS for Oracle로 이관
    - REFACTORING: Aurora PostgreSQL 등 다른 엔진으로 전환하여 비용 절감
    """

    REPLATFORM = "replatform"    # RDS for Oracle
    REFACTORING = "refactoring"  # Aurora PostgreSQL


class PricingType(str, Enum):
    """요금제 유형 열거형.

    - ON_DEMAND: 약정 없이 시간 단위로 과금
    - RI_1YR: 1년 부분 선결제(Partial Upfront) 예약 인스턴스
    - RI_3YR: 3년 부분 선결제(Partial Upfront) 예약 인스턴스
    """

    ON_DEMAND = "on_demand"
    RI_1YR = "1yr_partial_upfront"
    RI_3YR = "3yr_partial_upfront"


class InstanceSpec(BaseModel):
    """인스턴스 사양 모델 - AWS Pricing API 조회 키로 사용.

    Attributes:
        instance_type: 인스턴스 유형 (예: "db.r6i.xlarge")
        region: AWS 리전 코드 (예: "ap-northeast-2")
        engine: RDS 엔진 (예: "oracle-ee", "aurora-postgresql")
        strategy: 이관 전략 (Replatform 또는 Refactoring)
    """

    # 인스턴스 유형 (예: "db.r6i.xlarge")
    instance_type: str
    # AWS 리전 코드 (예: "ap-northeast-2")
    region: str
    # RDS 엔진 (예: "oracle-ee", "aurora-postgresql")
    engine: str
    # 이관 전략
    strategy: MigrationStrategy


class CostRecord(BaseModel):
    """단일 인스턴스의 특정 요금제 비용 정보 모델.

    Attributes:
        spec: 인스턴스 사양 정보
        pricing_type: 요금제 유형 (온디맨드, 1년 RI, 3년 RI)
        hourly_rate: 온디맨드 시간당 요금 (USD)
        upfront_fee: RI 선결제 금액 (USD)
        monthly_fee: RI 월정액 (USD)
        annual_cost: 연간 총비용 (USD) - 자동 계산 가능
        is_available: 가격 데이터 존재 여부
    """

    # 인스턴스 사양 정보
    spec: InstanceSpec
    # 요금제 유형
    pricing_type: PricingType
    # 온디맨드 시간당 요금 (USD)
    hourly_rate: Optional[float] = None
    # RI 선결제 금액 (USD)
    upfront_fee: Optional[float] = None
    # RI 월정액 (USD)
    monthly_fee: Optional[float] = None
    # 연간 총비용 (USD) - validator에서 자동 계산
    annual_cost: Optional[float] = None
    # 가격 데이터 존재 여부
    is_available: bool = True

    @model_validator(mode="after")
    def compute_annual_cost(self) -> "CostRecord":
        """annual_cost가 없으면 요금제 유형에 따라 자동 계산.

        계산 공식:
        - ON_DEMAND: hourly_rate × 24 × 365
        - RI_1YR: upfront_fee + monthly_fee × 12
        - RI_3YR: upfront_fee + monthly_fee × 36

        Returns:
            self (Pydantic v2 model_validator after 방식)
        """
        # 이미 값이 있으면 계산 생략
        if self.annual_cost is not None:
            return self

        # 요금제 유형에 따라 연간 비용 계산
        if self.pricing_type == PricingType.ON_DEMAND:
            # 온디맨드: 시간당 요금 × 24시간 × 365일
            if self.hourly_rate is not None:
                self.annual_cost = self.hourly_rate * 24 * 365
        elif self.pricing_type == PricingType.RI_1YR:
            # 1년 RI: 선결제 금액 + 월정액 × 12개월
            if self.upfront_fee is not None and self.monthly_fee is not None:
                self.annual_cost = self.upfront_fee + self.monthly_fee * 12
        elif self.pricing_type == PricingType.RI_3YR:
            # 3년 RI: 선결제 금액 + 월정액 × 36개월
            if self.upfront_fee is not None and self.monthly_fee is not None:
                self.annual_cost = self.upfront_fee + self.monthly_fee * 36

        return self


class CostRow(BaseModel):
    """비교표의 단일 행 모델 - 하나의 인스턴스 + 전략 조합.

    Attributes:
        instance_type: 인스턴스 유형 (예: "db.r6i.xlarge")
        strategy: 이관 전략
        on_demand_annual: 온디맨드 연간 비용 (USD)
        ri_1yr_annual: 1년 RI 연간 비용 (USD)
        ri_3yr_annual: 3년 RI 연간 비용 (USD)
        on_prem_annual_cost: 온프레미스 연간 유지비용 (USD)
        savings_rate_on_demand: 온프레미스 대비 온디맨드 절감률 (%)
        savings_rate_ri_1yr: 온프레미스 대비 1년 RI 절감률 (%)
        savings_rate_ri_3yr: 온프레미스 대비 3년 RI 절감률 (%)
    """

    # 인스턴스 유형
    instance_type: str
    # 이관 전략
    strategy: MigrationStrategy
    # 온디맨드 연간 비용 (USD)
    on_demand_annual: Optional[float]
    # 1년 RI 연간 비용 (USD)
    ri_1yr_annual: Optional[float]
    # 3년 RI 연간 비용 (USD)
    ri_3yr_annual: Optional[float]
    # 온프레미스 연간 유지비용 (USD)
    on_prem_annual_cost: float
    # 온프레미스 대비 온디맨드 절감률 (%)
    savings_rate_on_demand: Optional[float]
    # 온프레미스 대비 1년 RI 절감률 (%)
    savings_rate_ri_1yr: Optional[float]
    # 온프레미스 대비 3년 RI 절감률 (%)
    savings_rate_ri_3yr: Optional[float]


class CLIArgs(BaseModel):
    """CLI 인수 파싱 결과 모델.

    Attributes:
        region: AWS 리전 코드 (기본값: "ap-northeast-2")
        current_instance: 현재 사용 중인 인스턴스 유형
        recommended_instance: 권장 인스턴스 유형
        on_prem_cost: 온프레미스 연간 유지비용 (USD)
        engine: RDS 엔진 (기본값: "oracle-ee")
        profile: AWS CLI 프로파일 이름
        verbose: DEBUG 로그 활성화 여부
        output_format: 출력 형식 ("json" 또는 None)
        output_file: JSON 출력 파일 경로
        input_file: 문서 파일 경로 (PDF/DOCX/TXT)
        bedrock_model: Bedrock 모델 ID
    """

    # AWS 리전 코드 (기본값: 서울 리전)
    region: str = "ap-northeast-2"
    # 현재 사용 중인 인스턴스 유형 (예: "db.r6i.xlarge")
    current_instance: Optional[str] = None
    # 권장 인스턴스 유형
    recommended_instance: Optional[str] = None
    # 온프레미스 연간 유지비용 (USD)
    on_prem_cost: Optional[float] = None
    # RDS 엔진 (기본값: Oracle Enterprise Edition)
    engine: str = "oracle-ee"
    # AWS CLI 프로파일 이름 (None이면 기본 자격증명 사용)
    profile: Optional[str] = None
    # DEBUG 로그 활성화 여부
    verbose: bool = False
    # 출력 형식 ("json" 또는 None)
    output_format: Optional[str] = None
    # JSON 출력 파일 경로
    output_file: Optional[str] = None
    # 문서 파일 경로 (--input-file 옵션)
    input_file: Optional[str] = None
    # Bedrock 모델 ID (기본값: Claude 3.5 Sonnet)
    bedrock_model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"


class ParsedDocumentInfo(BaseModel):
    """Bedrock이 문서에서 추출한 인스턴스 사양 정보 모델.

    Attributes:
        current_instance: 현재 인스턴스 유형 (문서에서 추출)
        recommended_instance: 권장 인스턴스 유형 (문서에서 추출)
        on_prem_cost: 온프레미스 연간 유지비용 (USD, 문서에서 추출)
        engine: RDS 엔진 (문서에서 추출)
        metadata: 추가 메타데이터 (자유 형식 딕셔너리)
    """

    # 현재 인스턴스 유형 (문서에서 추출, 없으면 None)
    current_instance: Optional[str] = None
    # 권장 인스턴스 유형 (문서에서 추출, 없으면 None)
    recommended_instance: Optional[str] = None
    # 온프레미스 연간 유지비용 (USD, 문서에서 추출, 없으면 None)
    on_prem_cost: Optional[float] = None
    # RDS 엔진 (문서에서 추출, 없으면 None)
    engine: Optional[str] = None
    # 추가 메타데이터 (자유 형식)
    metadata: dict = Field(default_factory=dict)
