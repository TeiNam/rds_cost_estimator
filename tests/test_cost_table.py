"""
CostTable 클래스 단위 테스트.

테스트 항목:
- compute_savings: 온디맨드/1년RI/3년RI 비용이 올바르게 CostRow에 매핑되는지 확인
- compute_savings: 절감률 계산 공식 (on_prem - annual) / on_prem × 100 정확성 확인
- compute_savings: is_available=False 레코드는 해당 비용이 None인지 확인
- to_dict: 반환값이 딕셔너리 목록인지 확인
- to_dict: strategy 필드가 문자열로 직렬화되는지 확인
"""

from __future__ import annotations

import pytest

from rds_cost_estimator.cost_table import CostTable
from rds_cost_estimator.models import (
    CostRecord,
    InstanceSpec,
    MigrationStrategy,
    PricingType,
)


# ─── 공통 픽스처 ────────────────────────────────────────────────────────────────

def make_spec(
    instance_type: str = "db.r6i.xlarge",
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
) -> InstanceSpec:
    """테스트용 InstanceSpec 생성 헬퍼."""
    return InstanceSpec(
        instance_type=instance_type,
        region="ap-northeast-2",
        engine="oracle-ee",
        strategy=strategy,
    )


def make_on_demand_record(
    instance_type: str = "db.r6i.xlarge",
    hourly_rate: float = 2.0,
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
    is_available: bool = True,
) -> CostRecord:
    """온디맨드 CostRecord 생성 헬퍼."""
    return CostRecord(
        spec=make_spec(instance_type, strategy),
        pricing_type=PricingType.ON_DEMAND,
        hourly_rate=hourly_rate,
        is_available=is_available,
    )


def make_ri_1yr_record(
    instance_type: str = "db.r6i.xlarge",
    upfront_fee: float = 5000.0,
    monthly_fee: float = 1000.0,
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
    is_available: bool = True,
) -> CostRecord:
    """1년 RI CostRecord 생성 헬퍼."""
    return CostRecord(
        spec=make_spec(instance_type, strategy),
        pricing_type=PricingType.RI_1YR,
        upfront_fee=upfront_fee,
        monthly_fee=monthly_fee,
        is_available=is_available,
    )


def make_ri_3yr_record(
    instance_type: str = "db.r6i.xlarge",
    upfront_fee: float = 8000.0,
    monthly_fee: float = 700.0,
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
    is_available: bool = True,
) -> CostRecord:
    """3년 RI CostRecord 생성 헬퍼."""
    return CostRecord(
        spec=make_spec(instance_type, strategy),
        pricing_type=PricingType.RI_3YR,
        upfront_fee=upfront_fee,
        monthly_fee=monthly_fee,
        is_available=is_available,
    )


# ─── compute_savings 테스트 ──────────────────────────────────────────────────────

class TestComputeSavings:
    """compute_savings 메서드 테스트."""

    def test_on_demand_annual_cost_mapped_correctly(self) -> None:
        """온디맨드 연간 비용이 CostRow.on_demand_annual에 올바르게 매핑되는지 확인."""
        # hourly_rate=2.0 → annual = 2.0 × 24 × 365 = 17520.0
        record = make_on_demand_record(hourly_rate=2.0)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert len(rows) == 1
        assert rows[0].on_demand_annual == pytest.approx(2.0 * 24 * 365)

    def test_ri_1yr_annual_cost_mapped_correctly(self) -> None:
        """1년 RI 연간 비용이 CostRow.ri_1yr_annual에 올바르게 매핑되는지 확인."""
        # upfront=5000, monthly=1000 → annual = 5000 + 1000 × 12 = 17000.0
        record = make_ri_1yr_record(upfront_fee=5000.0, monthly_fee=1000.0)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert len(rows) == 1
        assert rows[0].ri_1yr_annual == pytest.approx(5000.0 + 1000.0 * 12)

    def test_ri_3yr_annual_cost_mapped_correctly(self) -> None:
        """3년 RI 연간 비용이 CostRow.ri_3yr_annual에 올바르게 매핑되는지 확인."""
        # upfront=8000, monthly=700 → annual = 8000 + 700 × 36 = 33200.0
        record = make_ri_3yr_record(upfront_fee=8000.0, monthly_fee=700.0)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert len(rows) == 1
        assert rows[0].ri_3yr_annual == pytest.approx(8000.0 + 700.0 * 36)

    def test_all_three_pricing_types_in_one_row(self) -> None:
        """온디맨드/1년RI/3년RI 세 레코드가 하나의 CostRow로 합쳐지는지 확인."""
        records = [
            make_on_demand_record(),
            make_ri_1yr_record(),
            make_ri_3yr_record(),
        ]
        table = CostTable(records=records, on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        # 동일한 (instance_type, strategy) 조합이므로 행 1개
        assert len(rows) == 1
        row = rows[0]
        assert row.on_demand_annual is not None
        assert row.ri_1yr_annual is not None
        assert row.ri_3yr_annual is not None

    def test_savings_rate_on_demand_formula(self) -> None:
        """온디맨드 절감률 계산 공식 (on_prem - annual) / on_prem × 100 정확성 확인."""
        # hourly_rate=1.0 → annual = 8760.0
        # on_prem = 50000.0
        # savings_rate = (50000 - 8760) / 50000 × 100 = 82.48
        record = make_on_demand_record(hourly_rate=1.0)
        on_prem = 50000.0
        table = CostTable(records=[record], on_prem_annual_cost=on_prem)

        rows = table.compute_savings()
        annual = 1.0 * 24 * 365
        expected_rate = (on_prem - annual) / on_prem * 100

        assert rows[0].savings_rate_on_demand == pytest.approx(expected_rate)

    def test_savings_rate_ri_1yr_formula(self) -> None:
        """1년 RI 절감률 계산 공식 정확성 확인."""
        # upfront=5000, monthly=1000 → annual = 17000.0
        # on_prem = 50000.0
        # savings_rate = (50000 - 17000) / 50000 × 100 = 66.0
        record = make_ri_1yr_record(upfront_fee=5000.0, monthly_fee=1000.0)
        on_prem = 50000.0
        table = CostTable(records=[record], on_prem_annual_cost=on_prem)

        rows = table.compute_savings()
        annual = 5000.0 + 1000.0 * 12
        expected_rate = (on_prem - annual) / on_prem * 100

        assert rows[0].savings_rate_ri_1yr == pytest.approx(expected_rate)

    def test_savings_rate_ri_3yr_formula(self) -> None:
        """3년 RI 절감률 계산 공식 정확성 확인."""
        # upfront=8000, monthly=700 → annual = 33200.0
        # on_prem = 50000.0
        # savings_rate = (50000 - 33200) / 50000 × 100 = 33.6
        record = make_ri_3yr_record(upfront_fee=8000.0, monthly_fee=700.0)
        on_prem = 50000.0
        table = CostTable(records=[record], on_prem_annual_cost=on_prem)

        rows = table.compute_savings()
        annual = 8000.0 + 700.0 * 36
        expected_rate = (on_prem - annual) / on_prem * 100

        assert rows[0].savings_rate_ri_3yr == pytest.approx(expected_rate)

    def test_is_available_false_on_demand_returns_none(self) -> None:
        """is_available=False인 온디맨드 레코드는 on_demand_annual이 None인지 확인."""
        record = make_on_demand_record(is_available=False)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert rows[0].on_demand_annual is None

    def test_is_available_false_ri_1yr_returns_none(self) -> None:
        """is_available=False인 1년 RI 레코드는 ri_1yr_annual이 None인지 확인."""
        record = make_ri_1yr_record(is_available=False)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert rows[0].ri_1yr_annual is None

    def test_is_available_false_ri_3yr_returns_none(self) -> None:
        """is_available=False인 3년 RI 레코드는 ri_3yr_annual이 None인지 확인."""
        record = make_ri_3yr_record(is_available=False)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert rows[0].ri_3yr_annual is None

    def test_is_available_false_savings_rate_is_none(self) -> None:
        """is_available=False인 레코드의 절감률도 None인지 확인."""
        record = make_on_demand_record(is_available=False)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert rows[0].savings_rate_on_demand is None

    def test_multiple_instance_types_create_separate_rows(self) -> None:
        """서로 다른 인스턴스 유형은 별도의 CostRow로 생성되는지 확인."""
        records = [
            make_on_demand_record(instance_type="db.r6i.xlarge"),
            make_on_demand_record(instance_type="db.r7i.xlarge"),
        ]
        table = CostTable(records=records, on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert len(rows) == 2
        instance_types = {row.instance_type for row in rows}
        assert instance_types == {"db.r6i.xlarge", "db.r7i.xlarge"}

    def test_multiple_strategies_create_separate_rows(self) -> None:
        """서로 다른 이관 전략은 별도의 CostRow로 생성되는지 확인."""
        records = [
            make_on_demand_record(strategy=MigrationStrategy.REPLATFORM),
            make_on_demand_record(strategy=MigrationStrategy.REFACTORING),
        ]
        table = CostTable(records=records, on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert len(rows) == 2
        strategies = {row.strategy for row in rows}
        assert strategies == {MigrationStrategy.REPLATFORM, MigrationStrategy.REFACTORING}

    def test_empty_records_returns_empty_list(self) -> None:
        """레코드가 없으면 빈 목록을 반환하는지 확인."""
        table = CostTable(records=[], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert rows == []

    def test_missing_pricing_type_returns_none_for_that_field(self) -> None:
        """특정 요금제 레코드가 없으면 해당 필드가 None인지 확인."""
        # 온디맨드 레코드만 있고 RI 레코드는 없음
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        rows = table.compute_savings()

        assert rows[0].on_demand_annual is not None
        assert rows[0].ri_1yr_annual is None
        assert rows[0].ri_3yr_annual is None


# ─── to_dict 테스트 ──────────────────────────────────────────────────────────────

class TestToDict:
    """to_dict 메서드 테스트."""

    def test_returns_list_of_dicts(self) -> None:
        """to_dict 반환값이 딕셔너리 목록인지 확인."""
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        result = table.to_dict()

        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_strategy_serialized_as_string(self) -> None:
        """strategy 필드가 문자열로 직렬화되는지 확인."""
        record = make_on_demand_record(strategy=MigrationStrategy.REPLATFORM)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        result = table.to_dict()

        assert len(result) == 1
        # Enum 값이 아닌 문자열이어야 함
        assert isinstance(result[0]["strategy"], str)
        assert result[0]["strategy"] == "replatform"

    def test_refactoring_strategy_serialized_as_string(self) -> None:
        """REFACTORING 전략도 문자열로 직렬화되는지 확인."""
        record = make_on_demand_record(strategy=MigrationStrategy.REFACTORING)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        result = table.to_dict()

        assert result[0]["strategy"] == "refactoring"

    def test_dict_contains_expected_keys(self) -> None:
        """딕셔너리에 필요한 키가 모두 포함되는지 확인."""
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        result = table.to_dict()

        expected_keys = {
            "instance_type",
            "strategy",
            "on_demand_annual",
            "ri_1yr_annual",
            "ri_3yr_annual",
            "on_prem_annual_cost",
            "savings_rate_on_demand",
            "savings_rate_ri_1yr",
            "savings_rate_ri_3yr",
        }
        assert set(result[0].keys()) == expected_keys

    def test_empty_records_returns_empty_list(self) -> None:
        """레코드가 없으면 빈 목록을 반환하는지 확인."""
        table = CostTable(records=[], on_prem_annual_cost=50000.0)

        result = table.to_dict()

        assert result == []

    def test_on_prem_annual_cost_in_dict(self) -> None:
        """딕셔너리에 on_prem_annual_cost 값이 올바르게 포함되는지 확인."""
        record = make_on_demand_record()
        on_prem = 150000.0
        table = CostTable(records=[record], on_prem_annual_cost=on_prem)

        result = table.to_dict()

        assert result[0]["on_prem_annual_cost"] == on_prem
