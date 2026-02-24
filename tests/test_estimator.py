"""
Estimator 클래스 단위 테스트 모듈.

테스트 대상:
- on_prem_cost 유효성 검증 (0, 음수, None → InvalidInputError)
- _build_specs: 4개 InstanceSpec 생성, REPLATFORM/REFACTORING 엔진 분기
- run: PricingClient를 AsyncMock으로 대체하여 CostTable 반환 확인
- --input-file 지정 시 ParsedDocumentInfo 필드로 CLIArgs 보완 (CLI 인수 우선)
- --profile 옵션에 따른 boto3.Session 생성 확인
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rds_cost_estimator.cost_table import CostTable
from rds_cost_estimator.exceptions import InvalidInputError
from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
)


# ─────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────

def make_args(**kwargs) -> CLIArgs:
    """테스트용 CLIArgs 생성 헬퍼 함수."""
    defaults = {
        "region": "ap-northeast-2",
        "current_instance": "db.r6i.xlarge",
        "recommended_instance_by_size": "db.r7i.xlarge",
        "on_prem_cost": 100_000.0,
        "engine": "oracle-ee",
    }
    defaults.update(kwargs)
    return CLIArgs(**defaults)


def make_cost_record(instance_type: str, strategy: MigrationStrategy) -> CostRecord:
    """테스트용 CostRecord 생성 헬퍼 함수."""
    spec = InstanceSpec(
        instance_type=instance_type,
        region="ap-northeast-2",
        engine="oracle-ee" if strategy == MigrationStrategy.REPLATFORM else "aurora-postgresql",
        strategy=strategy,
    )
    return CostRecord(
        spec=spec,
        pricing_type=PricingType.ON_DEMAND,
        hourly_rate=1.0,
    )


# ─────────────────────────────────────────────
# on_prem_cost 유효성 검증 테스트
# ─────────────────────────────────────────────

class TestOnPremCostValidation:
    """on_prem_cost 유효성 검증 테스트."""

    @pytest.mark.asyncio
    async def test_on_prem_cost_zero_raises_invalid_input_error(self):
        """on_prem_cost가 0이면 InvalidInputError가 발생해야 한다."""
        args = make_args(on_prem_cost=0.0)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        with pytest.raises(InvalidInputError):
            await estimator.run()

    @pytest.mark.asyncio
    async def test_on_prem_cost_negative_raises_invalid_input_error(self):
        """on_prem_cost가 음수이면 InvalidInputError가 발생해야 한다."""
        args = make_args(on_prem_cost=-1.0)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        with pytest.raises(InvalidInputError):
            await estimator.run()

    @pytest.mark.asyncio
    async def test_on_prem_cost_none_raises_invalid_input_error(self):
        """on_prem_cost가 None이면 InvalidInputError가 발생해야 한다."""
        args = make_args(on_prem_cost=None)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        with pytest.raises(InvalidInputError):
            await estimator.run()

    @pytest.mark.asyncio
    async def test_on_prem_cost_large_negative_raises_invalid_input_error(self):
        """on_prem_cost가 매우 큰 음수이면 InvalidInputError가 발생해야 한다."""
        args = make_args(on_prem_cost=-999_999_999.0)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        with pytest.raises(InvalidInputError):
            await estimator.run()


# ─────────────────────────────────────────────
# _build_specs 테스트
# ─────────────────────────────────────────────

class TestBuildSpecs:
    """_build_specs 메서드 테스트."""

    def _make_estimator(self, args: CLIArgs):
        """boto3.Session을 모킹하여 Estimator 인스턴스 생성."""
        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            return Estimator(args)

    def test_build_specs_expands_families_for_current_instance_non_oracle(self):
        """비Oracle 엔진에서 current_instance에 대해 r6i/r7i/r7g 패밀리 변형이 생성되어야 한다."""
        args = make_args(
            current_instance="db.r6i.xlarge",
            recommended_instance_by_size=None,
            recommended_instance_by_sga=None,
            engine="mysql",
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        # Refactoring에는 r7g 포함
        refactoring_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REFACTORING}
        assert "db.r6i.xlarge" in refactoring_types
        assert "db.r7i.xlarge" in refactoring_types
        assert "db.r7g.xlarge" in refactoring_types

    def test_build_specs_oracle_replatform_excludes_graviton(self):
        """Oracle 엔진의 REPLATFORM에서 Graviton(r7g)이 제외되어야 한다."""
        args = make_args(
            current_instance="db.r6i.xlarge",
            recommended_instance_by_size=None,
            recommended_instance_by_sga=None,
            engine="oracle-ee",
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        replatform_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REPLATFORM}
        assert "db.r6i.xlarge" in replatform_types
        assert "db.r7i.xlarge" in replatform_types
        assert "db.r7g.xlarge" not in replatform_types

    def test_build_specs_refactoring_includes_graviton_for_oracle(self):
        """Oracle 엔진이라도 REFACTORING(Aurora PostgreSQL)에서는 r7g가 포함되어야 한다."""
        args = make_args(
            current_instance="db.r6i.xlarge",
            recommended_instance_by_size=None,
            recommended_instance_by_sga=None,
            engine="oracle-ee",
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        refactoring_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REFACTORING}
        assert "db.r6i.xlarge" in refactoring_types
        assert "db.r7i.xlarge" in refactoring_types
        assert "db.r7g.xlarge" in refactoring_types

    def test_build_specs_expands_families_for_recommended_by_size(self):
        """recommended_instance_by_size에 대해 패밀리 변형이 생성되어야 한다."""
        args = make_args(
            current_instance=None,
            recommended_instance_by_size="db.r6i.2xlarge",
            recommended_instance_by_sga=None,
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        refactoring_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REFACTORING}
        assert "db.r6i.2xlarge" in refactoring_types
        assert "db.r7i.2xlarge" in refactoring_types
        assert "db.r7g.2xlarge" in refactoring_types

    def test_build_specs_expands_families_for_recommended_by_sga(self):
        """recommended_instance_by_sga에 대해 패밀리 변형이 생성되어야 한다."""
        args = make_args(
            current_instance=None,
            recommended_instance_by_size=None,
            recommended_instance_by_sga="db.r6i.large",
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        refactoring_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REFACTORING}
        assert "db.r6i.large" in refactoring_types
        assert "db.r7i.large" in refactoring_types
        assert "db.r7g.large" in refactoring_types

    def test_build_specs_deduplicates_same_instance(self):
        """동일 사이즈의 current와 recommended가 겹치면 중복 제거되어야 한다."""
        args = make_args(
            current_instance="db.r6i.xlarge",
            recommended_instance_by_size="db.r7i.xlarge",  # current 확장 시 이미 포함됨
            recommended_instance_by_sga=None,
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        # Oracle(oracle-ee) 기본 엔진:
        # Replatform: r6i, r7i (Graviton 제외) = 2개
        # Refactoring: r6i, r7i, r7g = 3개
        # 총 5개 스펙
        replatform_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REPLATFORM}
        refactoring_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REFACTORING}
        assert len(replatform_types) == 2
        assert len(refactoring_types) == 3
        assert len(specs) == 5

    def test_build_specs_replatform_uses_args_engine(self):
        """REPLATFORM 전략의 InstanceSpec은 args.engine을 사용해야 한다."""
        args = make_args(engine="oracle-se2")
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        replatform_specs = [s for s in specs if s.strategy == MigrationStrategy.REPLATFORM]
        for spec in replatform_specs:
            assert spec.engine == "oracle-se2"

    def test_build_specs_refactoring_uses_aurora_postgresql(self):
        """REFACTORING 전략의 InstanceSpec은 'aurora-postgresql' 엔진을 사용해야 한다."""
        args = make_args(engine="oracle-ee")
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        refactoring_specs = [s for s in specs if s.strategy == MigrationStrategy.REFACTORING]
        for spec in refactoring_specs:
            assert spec.engine == "aurora-postgresql"

    def test_build_specs_contains_both_strategies(self):
        """결과에 REPLATFORM과 REFACTORING 전략이 모두 포함되어야 한다."""
        args = make_args()
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        strategies = {s.strategy for s in specs}
        assert MigrationStrategy.REPLATFORM in strategies
        assert MigrationStrategy.REFACTORING in strategies

    def test_build_specs_uses_correct_region(self):
        """모든 InstanceSpec은 args.region을 사용해야 한다."""
        args = make_args(region="us-east-1")
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        for spec in specs:
            assert spec.region == "us-east-1"

    def test_build_specs_with_all_three_recommendations(self):
        """current + by_size + by_sga 모두 다른 사이즈일 때 전체 조합이 생성되어야 한다."""
        args = make_args(
            current_instance="db.r6i.xlarge",
            recommended_instance_by_size="db.r6i.2xlarge",
            recommended_instance_by_sga="db.r6i.large",
        )
        estimator = self._make_estimator(args)
        specs = estimator._build_specs()

        # Oracle 엔진:
        # Replatform: 3사이즈 × 2패밀리(r6i, r7i) = 6 유니크
        # Refactoring: 3사이즈 × 3패밀리 = 9 유니크
        replatform_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REPLATFORM}
        refactoring_types = {s.instance_type for s in specs if s.strategy == MigrationStrategy.REFACTORING}
        assert len(replatform_types) == 6
        assert len(refactoring_types) == 9
        assert len(specs) == 15


# ─────────────────────────────────────────────
# run 메서드 테스트
# ─────────────────────────────────────────────

class TestRun:
    """run 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_run_returns_cost_table(self):
        """run()은 CostTable 인스턴스를 반환해야 한다."""
        args = make_args()

        # PricingClient.fetch_all을 AsyncMock으로 대체
        mock_records = [
            make_cost_record("db.r6i.xlarge", MigrationStrategy.REPLATFORM),
            make_cost_record("db.r6i.xlarge", MigrationStrategy.REFACTORING),
            make_cost_record("db.r7i.xlarge", MigrationStrategy.REPLATFORM),
            make_cost_record("db.r7i.xlarge", MigrationStrategy.REFACTORING),
        ]

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        # PricingClient.fetch_all을 AsyncMock으로 교체
        estimator._pricing_client.fetch_all = AsyncMock(return_value=mock_records[:1])

        result = await estimator.run()

        assert isinstance(result, CostTable)

    @pytest.mark.asyncio
    async def test_run_calls_fetch_all_for_each_spec(self):
        """run()은 각 InstanceSpec에 대해 fetch_all을 호출해야 한다."""
        args = make_args(
            current_instance="db.r6i.xlarge",
            recommended_instance_by_size="db.r7i.xlarge",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        # fetch_all을 AsyncMock으로 교체 (빈 리스트 반환)
        estimator._pricing_client.fetch_all = AsyncMock(return_value=[])

        await estimator.run()

        # Oracle(oracle-ee) 엔진:
        # current(r6i.xlarge) + recommended_by_size(r7i.xlarge) → 동일 사이즈
        # Replatform: r6i, r7i (Graviton 제외) = 2개
        # Refactoring: r6i, r7i, r7g = 3개
        # 총 5개 스펙
        assert estimator._pricing_client.fetch_all.call_count == 5

    @pytest.mark.asyncio
    async def test_run_cost_table_has_correct_on_prem_cost(self):
        """run()이 반환하는 CostTable의 on_prem_annual_cost가 올바르게 설정되어야 한다."""
        args = make_args(on_prem_cost=150_000.0)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        estimator._pricing_client.fetch_all = AsyncMock(return_value=[])

        result = await estimator.run()

        assert result.on_prem_annual_cost == 150_000.0


# ─────────────────────────────────────────────
# --input-file 지정 시 CLIArgs 보완 테스트
# ─────────────────────────────────────────────

class TestInputFileIntegration:
    """--input-file 지정 시 ParsedDocumentInfo로 CLIArgs 보완 테스트."""

    @pytest.mark.asyncio
    async def test_input_file_fills_missing_current_instance(self):
        """--input-file 지정 시 current_instance가 없으면 문서 파싱 결과로 보완해야 한다."""
        args = make_args(
            current_instance=None,
            recommended_instance_by_size="db.r7i.xlarge",
            on_prem_cost=100_000.0,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            current_instance="db.r6i.xlarge",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run()

        assert estimator._args.current_instance == "db.r6i.xlarge"

    @pytest.mark.asyncio
    async def test_input_file_cli_args_take_priority(self):
        """--input-file 지정 시 CLI 인수가 문서 파싱 결과보다 우선해야 한다."""
        args = make_args(
            current_instance="db.r6i.2xlarge",
            recommended_instance_by_size="db.r7i.xlarge",
            on_prem_cost=100_000.0,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            current_instance="db.r6i.xlarge",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run()

        assert estimator._args.current_instance == "db.r6i.2xlarge"

    @pytest.mark.asyncio
    async def test_input_file_fills_on_prem_cost(self):
        """--input-file 지정 시 on_prem_cost가 없으면 문서 파싱 결과로 보완해야 한다."""
        args = make_args(
            on_prem_cost=None,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            current_instance="db.r6i.xlarge",
            on_prem_cost=200_000.0,
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run()

        assert estimator._args.on_prem_cost == 200_000.0

    @pytest.mark.asyncio
    async def test_input_file_fills_recommended_by_size_and_sga(self):
        """--input-file 지정 시 두 가지 권장 인스턴스가 문서 파싱 결과로 보완되어야 한다."""
        args = make_args(
            recommended_instance_by_size=None,
            recommended_instance_by_sga=None,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            recommended_instance_by_size="db.r6i.2xlarge",
            recommended_instance_by_sga="db.r6i.large",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run()

        assert estimator._args.recommended_instance_by_size == "db.r6i.2xlarge"
        assert estimator._args.recommended_instance_by_sga == "db.r6i.large"

    @pytest.mark.asyncio
    async def test_no_input_file_uses_cli_args_directly(self):
        """--input-file이 없으면 DocumentParser를 호출하지 않아야 한다."""
        args = make_args(input_file=None)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        estimator._pricing_client.fetch_all = AsyncMock(return_value=[])

        with patch("rds_cost_estimator.estimator.DocumentParser") as mock_parser_cls:
            await estimator.run()
            mock_parser_cls.assert_not_called()


# ─────────────────────────────────────────────
# --profile 옵션에 따른 boto3.Session 생성 테스트
# ─────────────────────────────────────────────

class TestBoto3SessionCreation:
    """--profile 옵션에 따른 boto3.Session 생성 테스트."""

    def test_profile_creates_session_with_profile_name(self):
        """--profile 옵션이 있으면 profile_name을 지정하여 Session을 생성해야 한다."""
        args = make_args(profile="my-aws-profile")

        with patch("rds_cost_estimator.estimator.boto3.Session") as mock_session_cls:
            from rds_cost_estimator.estimator import Estimator
            Estimator(args)

        # profile_name 인수로 Session이 생성되어야 함
        mock_session_cls.assert_called_once_with(profile_name="my-aws-profile")

    def test_no_profile_creates_default_session(self):
        """--profile 옵션이 없으면 기본 Session을 생성해야 한다."""
        args = make_args(profile=None)

        with patch("rds_cost_estimator.estimator.boto3.Session") as mock_session_cls:
            from rds_cost_estimator.estimator import Estimator
            Estimator(args)

        # 인수 없이 기본 Session이 생성되어야 함
        mock_session_cls.assert_called_once_with()
