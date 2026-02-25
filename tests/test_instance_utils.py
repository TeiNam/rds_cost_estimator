"""
instance_utils 모듈 단위 테스트.

인스턴스 사양 조회, 패밀리 확장, 스토리지 비용 계산 등을 검증합니다.
"""

import pytest

from rds_cost_estimator.instance_utils import (
    ORACLE_ENGINES,
    GRAVITON_FAMILIES,
    REFACTORING_ENGINE,
    REGION_PRICING,
    get_all_network_keys,
    get_instance_specs,
    extract_family_and_size,
    expand_instance_families,
    find_matching_instance,
    calc_storage_costs,
    get_region_pricing,
)


class TestGetInstanceSpecs:
    """get_instance_specs 함수 테스트."""

    def test_r6i_2xlarge(self):
        specs = get_instance_specs("db.r6i.2xlarge")
        assert specs is not None
        assert specs["vcpu"] == 8
        assert specs["memory_gb"] == 64

    def test_t3_micro(self):
        specs = get_instance_specs("db.t3.micro")
        assert specs is not None
        assert specs["vcpu"] == 2
        assert specs["memory_gb"] == 1

    def test_m6i_large(self):
        specs = get_instance_specs("db.m6i.large")
        assert specs is not None
        assert specs["vcpu"] == 2
        assert specs["memory_gb"] == 8

    def test_invalid_format_returns_none(self):
        assert get_instance_specs("invalid") is None

    def test_r_family_no_micro(self):
        """r 계열에서 micro 사이즈는 제거되어 None을 반환합니다."""
        assert get_instance_specs("db.r6i.micro") is None


class TestExtractFamilyAndSize:
    """extract_family_and_size 함수 테스트."""

    def test_normal_instance(self):
        result = extract_family_and_size("db.r6i.2xlarge")
        assert result == ("r6i", "2xlarge")

    def test_invalid_returns_none(self):
        assert extract_family_and_size("not-an-instance") is None


class TestExpandInstanceFamilies:
    """expand_instance_families 함수 테스트."""

    def test_r6i_expands(self):
        variants = expand_instance_families("db.r6i.2xlarge")
        assert "db.r6i.2xlarge" in variants
        assert len(variants) >= 2

    def test_exclude_graviton(self):
        variants = expand_instance_families("db.r6i.2xlarge", exclude_graviton=True)
        for v in variants:
            family = extract_family_and_size(v)
            if family:
                assert family[0] not in GRAVITON_FAMILIES


class TestFindMatchingInstance:
    """find_matching_instance 함수 테스트."""

    def test_exact_match(self):
        result = find_matching_instance(64.0, "r6i")
        assert result == "db.r6i.2xlarge"

    def test_rounds_up(self):
        result = find_matching_instance(50.0, "r6i")
        assert result == "db.r6i.2xlarge"

    def test_t_family(self):
        result = find_matching_instance(1.0, "t3")
        assert result == "db.t3.micro"

    def test_exceeds_max_returns_largest(self):
        result = find_matching_instance(9999.0, "r6i")
        assert result == "db.r6i.24xlarge"


class TestCalcStorageCosts:
    """calc_storage_costs 함수 테스트."""

    def test_basic_storage(self):
        costs = calc_storage_costs(100.0)
        assert costs["storage"] == 8.0
        assert costs["iops"] == 0
        assert costs["throughput"] == 0
        assert costs["total"] == 8.0

    def test_with_extra_iops(self):
        costs = calc_storage_costs(100.0, provisioned_iops=5000)
        # 5000 - 3000 = 2000 extra × $0.02 = $40
        assert costs["iops"] == 40.0

    def test_region_affects_cost(self):
        costs_seoul = calc_storage_costs(100.0, region="ap-northeast-2")
        costs_tokyo = calc_storage_costs(100.0, region="ap-northeast-1")
        assert costs_tokyo["total"] > costs_seoul["total"]


class TestConstants:
    """상수 값 검증 테스트."""

    def test_oracle_engines(self):
        assert "oracle-ee" in ORACLE_ENGINES
        assert "oracle-se2" in ORACLE_ENGINES

    def test_refactoring_engine(self):
        assert REFACTORING_ENGINE == "aurora-postgresql"

    def test_region_pricing_has_default(self):
        assert "ap-northeast-2" in REGION_PRICING

    def test_network_keys_not_empty(self):
        keys = get_all_network_keys()
        assert len(keys) > 0
        assert "net_scenario" in keys
