"""
Pydantic v2 데이터 모델 단위 테스트 모듈.

CostRecord 연간 비용 자동 계산, CLIArgs 기본값, ParsedDocumentInfo 기본값,
Enum 값 등을 검증합니다.
"""

import pytest

from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    InstanceFamily,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
)


# 테스트에서 공통으로 사용할 InstanceSpec 픽스처
@pytest.fixture
def sample_spec() -> InstanceSpec:
    """테스트용 기본 InstanceSpec 인스턴스."""
    return InstanceSpec(
        instance_type="db.r6i.xlarge",
        region="ap-northeast-2",
        engine="oracle-ee",
        strategy=MigrationStrategy.REPLATFORM,
    )


class TestCostRecordOnDemandAnnualCost:
    """CostRecord 온디맨드 연간 비용 자동 계산 테스트."""

    def test_on_demand_annual_cost_calculation(self, sample_spec: InstanceSpec) -> None:
        """온디맨드 annual_cost = hourly_rate × 24 × 365 자동 계산 확인."""
        hourly_rate = 1.0
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.ON_DEMAND,
            hourly_rate=hourly_rate,
        )
        expected = hourly_rate * 24 * 365
        assert record.annual_cost == pytest.approx(expected)

    def test_on_demand_annual_cost_with_decimal_rate(self, sample_spec: InstanceSpec) -> None:
        """소수점 hourly_rate에 대한 온디맨드 연간 비용 계산 확인."""
        hourly_rate = 0.5
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.ON_DEMAND,
            hourly_rate=hourly_rate,
        )
        assert record.annual_cost == pytest.approx(0.5 * 24 * 365)

    def test_on_demand_annual_cost_none_when_no_hourly_rate(
        self, sample_spec: InstanceSpec
    ) -> None:
        """hourly_rate가 없으면 annual_cost가 None인지 확인."""
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.ON_DEMAND,
        )
        assert record.annual_cost is None

    def test_on_demand_explicit_annual_cost_not_overwritten(
        self, sample_spec: InstanceSpec
    ) -> None:
        """명시적으로 annual_cost를 지정하면 덮어쓰지 않는지 확인."""
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.ON_DEMAND,
            hourly_rate=1.0,
            annual_cost=99999.0,
        )
        # 명시적으로 지정한 값이 유지되어야 함
        assert record.annual_cost == pytest.approx(99999.0)


class TestCostRecordRI1YrAnnualCost:
    """CostRecord 1년 RI 연간 비용 자동 계산 테스트."""

    def test_ri_1yr_annual_cost_calculation(self, sample_spec: InstanceSpec) -> None:
        """1년 RI annual_cost = upfront_fee + monthly_fee × 12 자동 계산 확인."""
        upfront_fee = 1000.0
        monthly_fee = 500.0
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.RI_1YR,
            upfront_fee=upfront_fee,
            monthly_fee=monthly_fee,
        )
        expected = upfront_fee + monthly_fee * 12
        assert record.annual_cost == pytest.approx(expected)

    def test_ri_1yr_annual_cost_with_zero_upfront(self, sample_spec: InstanceSpec) -> None:
        """선결제 0인 경우 1년 RI 연간 비용 = monthly_fee × 12 확인."""
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.RI_1YR,
            upfront_fee=0.0,
            monthly_fee=300.0,
        )
        assert record.annual_cost == pytest.approx(300.0 * 12)

    def test_ri_1yr_annual_cost_none_when_missing_fees(
        self, sample_spec: InstanceSpec
    ) -> None:
        """upfront_fee 또는 monthly_fee가 없으면 annual_cost가 None인지 확인."""
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.RI_1YR,
            upfront_fee=1000.0,
            # monthly_fee 누락
        )
        assert record.annual_cost is None


class TestCostRecordRI3YrAnnualCost:
    """CostRecord 3년 RI 연간 비용 자동 계산 테스트."""

    def test_ri_3yr_annual_cost_calculation(self, sample_spec: InstanceSpec) -> None:
        """3년 RI annual_cost = upfront_fee + monthly_fee × 36 자동 계산 확인."""
        upfront_fee = 2000.0
        monthly_fee = 400.0
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.RI_3YR,
            upfront_fee=upfront_fee,
            monthly_fee=monthly_fee,
        )
        expected = upfront_fee + monthly_fee * 36
        assert record.annual_cost == pytest.approx(expected)

    def test_ri_3yr_annual_cost_with_zero_upfront(self, sample_spec: InstanceSpec) -> None:
        """선결제 0인 경우 3년 RI 연간 비용 = monthly_fee × 36 확인."""
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.RI_3YR,
            upfront_fee=0.0,
            monthly_fee=200.0,
        )
        assert record.annual_cost == pytest.approx(200.0 * 36)

    def test_ri_3yr_annual_cost_none_when_missing_fees(
        self, sample_spec: InstanceSpec
    ) -> None:
        """monthly_fee가 없으면 annual_cost가 None인지 확인."""
        record = CostRecord(
            spec=sample_spec,
            pricing_type=PricingType.RI_3YR,
            monthly_fee=200.0,
            # upfront_fee 누락
        )
        assert record.annual_cost is None


class TestCLIArgsDefaults:
    """CLIArgs 기본값 테스트."""

    def test_region_default(self) -> None:
        """region 기본값이 'ap-northeast-2'인지 확인."""
        args = CLIArgs()
        assert args.region == "ap-northeast-2"

    def test_engine_default(self) -> None:
        """engine 기본값이 'oracle-ee'인지 확인."""
        args = CLIArgs()
        assert args.engine == "oracle-ee"

    def test_verbose_default(self) -> None:
        """verbose 기본값이 False인지 확인."""
        args = CLIArgs()
        assert args.verbose is False

    def test_bedrock_model_default(self) -> None:
        """bedrock_model 기본값이 Claude 3.5 Sonnet인지 확인."""
        args = CLIArgs()
        assert args.bedrock_model == "anthropic.claude-3-5-sonnet-20241022-v2:0"

    def test_optional_fields_default_none(self) -> None:
        """선택적 필드들의 기본값이 None인지 확인."""
        args = CLIArgs()
        assert args.current_instance is None
        assert args.recommended_instance is None
        assert args.on_prem_cost is None
        assert args.profile is None
        assert args.output_format is None
        assert args.output_file is None
        assert args.input_file is None

    def test_custom_values(self) -> None:
        """CLIArgs에 커스텀 값을 설정할 수 있는지 확인."""
        args = CLIArgs(
            region="us-east-1",
            current_instance="db.r6i.xlarge",
            recommended_instance="db.r7i.xlarge",
            on_prem_cost=150000.0,
            engine="aurora-postgresql",
            verbose=True,
        )
        assert args.region == "us-east-1"
        assert args.current_instance == "db.r6i.xlarge"
        assert args.on_prem_cost == 150000.0
        assert args.verbose is True


class TestParsedDocumentInfoDefaults:
    """ParsedDocumentInfo 기본값 테스트."""

    def test_all_fields_default_none(self) -> None:
        """모든 필드의 기본값이 None인지 확인."""
        info = ParsedDocumentInfo()
        assert info.current_instance is None
        assert info.recommended_instance is None
        assert info.on_prem_cost is None
        assert info.engine is None

    def test_metadata_default_empty_dict(self) -> None:
        """metadata 기본값이 빈 딕셔너리인지 확인."""
        info = ParsedDocumentInfo()
        assert info.metadata == {}

    def test_metadata_instances_are_independent(self) -> None:
        """서로 다른 인스턴스의 metadata가 독립적인지 확인 (mutable default 문제 방지)."""
        info1 = ParsedDocumentInfo()
        info2 = ParsedDocumentInfo()
        info1.metadata["key"] = "value"
        # info2의 metadata는 영향을 받지 않아야 함
        assert "key" not in info2.metadata

    def test_partial_fields(self) -> None:
        """일부 필드만 설정한 경우 나머지는 None인지 확인."""
        info = ParsedDocumentInfo(current_instance="db.r6i.xlarge")
        assert info.current_instance == "db.r6i.xlarge"
        assert info.recommended_instance is None
        assert info.on_prem_cost is None
        assert info.engine is None


class TestEnumValues:
    """Enum 클래스 값 테스트."""

    def test_migration_strategy_values(self) -> None:
        """MigrationStrategy Enum 값 확인."""
        assert MigrationStrategy.REPLATFORM == "replatform"
        assert MigrationStrategy.REFACTORING == "refactoring"

    def test_pricing_type_values(self) -> None:
        """PricingType Enum 값 확인."""
        assert PricingType.ON_DEMAND == "on_demand"
        assert PricingType.RI_1YR == "1yr_partial_upfront"
        assert PricingType.RI_3YR == "3yr_partial_upfront"

    def test_instance_family_values(self) -> None:
        """InstanceFamily Enum 값 확인."""
        assert InstanceFamily.R6I == "r6i"
        assert InstanceFamily.R7I == "r7i"
        assert InstanceFamily.R7G == "r7g"

    def test_migration_strategy_is_str_enum(self) -> None:
        """MigrationStrategy가 str 기반 Enum인지 확인."""
        assert isinstance(MigrationStrategy.REPLATFORM, str)

    def test_pricing_type_is_str_enum(self) -> None:
        """PricingType이 str 기반 Enum인지 확인."""
        assert isinstance(PricingType.ON_DEMAND, str)

    def test_instance_family_is_str_enum(self) -> None:
        """InstanceFamily가 str 기반 Enum인지 확인."""
        assert isinstance(InstanceFamily.R6I, str)
