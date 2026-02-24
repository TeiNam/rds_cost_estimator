"""
Pydantic v2 데이터 모델 정의 모듈.

이 모듈은 RDS Cost Estimator에서 사용하는 모든 데이터 모델을 정의합니다.
- 열거형(Enum): InstanceFamily, MigrationStrategy, PricingType
- 핵심 모델: InstanceSpec, CostRecord, CostRow, CLIArgs, ParsedDocumentInfo
- 템플릿 모델: AWRMetrics, SGAAnalysis, StorageGrowth, InstanceRecommendation, TemplateData
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

    @classmethod
    def all_families(cls) -> list[str]:
        """모든 인스턴스 패밀리 값을 리스트로 반환."""
        return [f.value for f in cls]


class MigrationStrategy(str, Enum):
    """이관 전략 열거형."""

    REPLATFORM = "replatform"
    REFACTORING = "refactoring"


class PricingType(str, Enum):
    """요금제 유형 열거형 - 템플릿 v2에 맞게 확장."""

    ON_DEMAND = "on_demand"
    RI_1YR_NO_UPFRONT = "1yr_no_upfront"
    RI_1YR_ALL_UPFRONT = "1yr_all_upfront"
    RI_3YR_NO_UPFRONT = "3yr_no_upfront"
    RI_3YR_ALL_UPFRONT = "3yr_all_upfront"
    # 하위 호환용 (Partial Upfront)
    RI_1YR = "1yr_partial_upfront"
    RI_3YR = "3yr_partial_upfront"


class InstanceSpec(BaseModel):
    """인스턴스 사양 모델 - AWS Pricing API 조회 키로 사용."""

    instance_type: str
    region: str
    engine: str
    strategy: MigrationStrategy
    deployment_option: str = "Single-AZ"


class CostRecord(BaseModel):
    """단일 인스턴스의 특정 요금제 비용 정보 모델."""

    spec: InstanceSpec
    pricing_type: PricingType
    hourly_rate: Optional[float] = None
    upfront_fee: Optional[float] = None
    monthly_fee: Optional[float] = None
    annual_cost: Optional[float] = None
    is_available: bool = True

    @model_validator(mode="after")
    def compute_annual_cost(self) -> "CostRecord":
        """annual_cost가 없으면 요금제 유형에 따라 자동 계산."""
        if self.annual_cost is not None:
            return self

        if self.pricing_type == PricingType.ON_DEMAND:
            if self.hourly_rate is not None:
                self.annual_cost = self.hourly_rate * 730 * 12
        elif self.pricing_type in (
            PricingType.RI_1YR, PricingType.RI_1YR_NO_UPFRONT, PricingType.RI_1YR_ALL_UPFRONT
        ):
            if self.upfront_fee is not None and self.monthly_fee is not None:
                self.annual_cost = self.upfront_fee + self.monthly_fee * 12
        elif self.pricing_type in (
            PricingType.RI_3YR, PricingType.RI_3YR_NO_UPFRONT, PricingType.RI_3YR_ALL_UPFRONT
        ):
            if self.upfront_fee is not None and self.monthly_fee is not None:
                total_3yr = self.upfront_fee + self.monthly_fee * 36
                self.annual_cost = total_3yr / 3

        return self

    @property
    def monthly_cost(self) -> Optional[float]:
        """월간 비용 계산."""
        if self.annual_cost is not None:
            return self.annual_cost / 12
        return None


class CostRow(BaseModel):
    """비교표의 단일 행 모델."""

    instance_type: str
    strategy: MigrationStrategy
    on_demand_annual: Optional[float]
    ri_1yr_annual: Optional[float]
    ri_3yr_annual: Optional[float]
    on_prem_annual_cost: float
    savings_rate_on_demand: Optional[float]
    savings_rate_ri_1yr: Optional[float]
    savings_rate_ri_3yr: Optional[float]


class CLIArgs(BaseModel):
    """CLI 인수 파싱 결과 모델."""

    region: str = "ap-northeast-2"
    current_instance: Optional[str] = None
    recommended_instance: Optional[str] = None
    recommended_instance_by_size: Optional[str] = None
    recommended_instance_by_sga: Optional[str] = None
    on_prem_cost: Optional[float] = None
    engine: str = "oracle-ee"
    profile: Optional[str] = None
    verbose: bool = False
    output_format: Optional[str] = None
    output_dir: str = "."
    input_file: Optional[str] = None
    bedrock_model: str = "anthropic.claude-sonnet-4-6"

    @model_validator(mode="after")
    def migrate_recommended_instance(self) -> "CLIArgs":
        """하위 호환: recommended_instance → recommended_instance_by_size 마이그레이션."""
        if self.recommended_instance and not self.recommended_instance_by_size:
            self.recommended_instance_by_size = self.recommended_instance
        return self


# ─── 템플릿 v2 전용 모델 ───


class AWRMetrics(BaseModel):
    """AWR 성능 메트릭 모델."""

    avg_cpu_percent: Optional[float] = None
    peak_cpu_percent: Optional[float] = None
    avg_iops: Optional[float] = None
    peak_iops: Optional[float] = None
    avg_memory_gb: Optional[float] = None
    peak_memory_gb: Optional[float] = None
    # 네트워크 비용 산정용
    sqlnet_bytes_sent_per_day: Optional[float] = None  # bytes/일
    sqlnet_bytes_received_per_day: Optional[float] = None  # bytes/일
    redo_bytes_per_day: Optional[float] = None  # bytes/일


class SGAAnalysis(BaseModel):
    """SGA 분석 결과 모델."""

    current_sga_gb: Optional[float] = None
    recommended_sga_gb: Optional[float] = None
    sga_increase_rate_percent: Optional[float] = None


class StorageGrowth(BaseModel):
    """스토리지 증가 추이 모델."""

    current_db_size_gb: Optional[float] = None
    yearly_growth_gb: Optional[float] = None
    yearly_growth_rate_percent: float = 15.0  # 기본값 15%


class InstanceRecommendation(BaseModel):
    """인스턴스 권장 사양 모델 (r6i/r7i 쌍)."""

    r6i_instance: Optional[str] = None
    r6i_vcpu: Optional[int] = None
    r6i_memory_gb: Optional[float] = None
    r6i_network_gbps: Optional[float] = None
    r7i_instance: Optional[str] = None
    r7i_vcpu: Optional[int] = None
    r7i_memory_gb: Optional[float] = None
    r7i_network_gbps: Optional[float] = None


class ParsedDocumentInfo(BaseModel):
    """Bedrock이 문서에서 추출한 정보 모델 - 템플릿 v2 확장."""

    # 기본 정보
    db_name: Optional[str] = None
    oracle_version: Optional[str] = None
    current_instance: Optional[str] = None
    recommended_instance: Optional[str] = None
    recommended_instance_by_size: Optional[str] = None
    recommended_instance_by_sga: Optional[str] = None
    on_prem_cost: Optional[float] = None
    engine: Optional[str] = None

    # 서버 사양
    cpu_cores: Optional[int] = None
    physical_memory_gb: Optional[float] = None
    db_size_gb: Optional[float] = None
    instance_config: Optional[str] = None  # 예: "2 (RAC)"

    # AWR 성능 메트릭
    awr_metrics: AWRMetrics = Field(default_factory=AWRMetrics)

    # SGA 분석
    sga_analysis: SGAAnalysis = Field(default_factory=SGAAnalysis)

    # 스토리지 증가 추이
    storage_growth: StorageGrowth = Field(default_factory=StorageGrowth)

    # 스토리지 IOPS/처리량 (gp3 추가 프로비저닝)
    provisioned_iops: Optional[int] = None  # 3000 초과분만
    provisioned_throughput_mbps: Optional[float] = None  # 125 초과분만

    # 추가 메타데이터
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def migrate_recommended_instance(self) -> "ParsedDocumentInfo":
        """하위 호환: recommended_instance → recommended_instance_by_size 마이그레이션."""
        if self.recommended_instance and not self.recommended_instance_by_size:
            self.recommended_instance_by_size = self.recommended_instance
        return self

    @model_validator(mode="after")
    def sync_db_size(self) -> "ParsedDocumentInfo":
        """db_size_gb와 storage_growth.current_db_size_gb 동기화."""
        if self.db_size_gb and not self.storage_growth.current_db_size_gb:
            self.storage_growth.current_db_size_gb = self.db_size_gb
        elif self.storage_growth.current_db_size_gb and not self.db_size_gb:
            self.db_size_gb = self.storage_growth.current_db_size_gb
        return self
