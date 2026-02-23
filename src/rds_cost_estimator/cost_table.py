"""
비용 집계 및 절감률 계산 모듈.

이 모듈은 여러 CostRecord를 집계하여 인스턴스 유형 + 이관 전략 조합별
비용 비교표(CostRow 목록)를 생성합니다.
온프레미스 유지비용 대비 절감률을 계산하여 의사결정 근거 자료를 제공합니다.
"""

from __future__ import annotations

import logging
from typing import Optional

from rds_cost_estimator.models import (
    CostRecord,
    CostRow,
    MigrationStrategy,
    PricingType,
)

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)


class CostTable:
    """여러 CostRecord를 집계하여 비용 비교표를 생성하는 클래스.

    인스턴스 유형 + 이관 전략 조합별로 온디맨드, 1년 RI, 3년 RI 비용을 집계하고
    온프레미스 유지비용 대비 절감률을 계산합니다.

    Attributes:
        records: 비용 레코드 목록
        on_prem_annual_cost: 온프레미스 연간 유지비용 (USD)
    """

    def __init__(self, records: list[CostRecord], on_prem_annual_cost: float) -> None:
        """CostTable 초기화.

        Args:
            records: CostRecord 목록 (여러 인스턴스 유형 + 요금제 조합)
            on_prem_annual_cost: 온프레미스 연간 유지비용 (USD)
        """
        # CostRecord 목록 저장
        self.records = records
        # 온프레미스 연간 유지비용 저장
        self.on_prem_annual_cost = on_prem_annual_cost

    def _calc_savings_rate(self, annual_cost: Optional[float]) -> Optional[float]:
        """온프레미스 비용 대비 절감률을 계산합니다.

        Args:
            annual_cost: 연간 비용 (USD). None이면 절감률도 None 반환.

        Returns:
            절감률 (%). annual_cost가 None이거나 on_prem_annual_cost가 0이면 None.
        """
        # annual_cost가 None이면 절감률도 None
        if annual_cost is None:
            return None

        # 온프레미스 비용이 0이면 ZeroDivisionError 방지
        if self.on_prem_annual_cost == 0:
            logger.warning("온프레미스 연간 비용이 0이므로 절감률을 계산할 수 없습니다.")
            return None

        # 절감률 계산: (온프레미스 비용 - 연간 비용) / 온프레미스 비용 × 100
        return (self.on_prem_annual_cost - annual_cost) / self.on_prem_annual_cost * 100

    def compute_savings(self) -> list[CostRow]:
        """CostRecord 목록을 집계하여 CostRow 목록을 생성합니다.

        인스턴스 유형 + 이관 전략 조합으로 그룹화한 뒤,
        각 그룹에서 ON_DEMAND, RI_1YR, RI_3YR 레코드를 찾아 CostRow를 생성합니다.
        is_available=False인 레코드는 해당 비용을 None으로 처리합니다.

        Returns:
            CostRow 목록 (인스턴스 유형 + 전략 조합별 비용 비교 행)
        """
        # (instance_type, strategy) 조합을 키로 하는 그룹 딕셔너리
        # 값: {PricingType: CostRecord}
        groups: dict[tuple[str, MigrationStrategy], dict[PricingType, CostRecord]] = {}

        # 레코드를 인스턴스 유형 + 전략 조합으로 그룹화
        for record in self.records:
            key = (record.spec.instance_type, record.spec.strategy)
            if key not in groups:
                groups[key] = {}
            groups[key][record.pricing_type] = record

        # 각 그룹에서 CostRow 생성
        rows: list[CostRow] = []
        for (instance_type, strategy), pricing_map in groups.items():
            # ON_DEMAND 비용 추출 (is_available=False이면 None)
            on_demand_record = pricing_map.get(PricingType.ON_DEMAND)
            on_demand_annual: Optional[float] = None
            if on_demand_record is not None and on_demand_record.is_available:
                on_demand_annual = on_demand_record.annual_cost

            # 1년 RI 비용 추출 (is_available=False이면 None)
            ri_1yr_record = pricing_map.get(PricingType.RI_1YR)
            ri_1yr_annual: Optional[float] = None
            if ri_1yr_record is not None and ri_1yr_record.is_available:
                ri_1yr_annual = ri_1yr_record.annual_cost

            # 3년 RI 비용 추출 (is_available=False이면 None)
            ri_3yr_record = pricing_map.get(PricingType.RI_3YR)
            ri_3yr_annual: Optional[float] = None
            if ri_3yr_record is not None and ri_3yr_record.is_available:
                ri_3yr_annual = ri_3yr_record.annual_cost

            # 각 요금제별 절감률 계산
            savings_rate_on_demand = self._calc_savings_rate(on_demand_annual)
            savings_rate_ri_1yr = self._calc_savings_rate(ri_1yr_annual)
            savings_rate_ri_3yr = self._calc_savings_rate(ri_3yr_annual)

            # CostRow 생성 및 목록에 추가
            row = CostRow(
                instance_type=instance_type,
                strategy=strategy,
                on_demand_annual=on_demand_annual,
                ri_1yr_annual=ri_1yr_annual,
                ri_3yr_annual=ri_3yr_annual,
                on_prem_annual_cost=self.on_prem_annual_cost,
                savings_rate_on_demand=savings_rate_on_demand,
                savings_rate_ri_1yr=savings_rate_ri_1yr,
                savings_rate_ri_3yr=savings_rate_ri_3yr,
            )
            rows.append(row)

        logger.debug("compute_savings: %d개의 CostRow 생성 완료", len(rows))
        return rows

    def to_dict(self) -> list[dict]:
        """compute_savings() 결과를 딕셔너리 목록으로 변환합니다.

        MigrationStrategy Enum 값은 문자열로 직렬화됩니다.

        Returns:
            CostRow를 딕셔너리로 변환한 목록 (JSON 직렬화 가능)
        """
        rows = self.compute_savings()
        result: list[dict] = []

        for row in rows:
            # model_dump()로 딕셔너리 변환, Enum은 값(문자열)으로 직렬화
            row_dict = row.model_dump()
            # MigrationStrategy Enum을 문자열 값으로 변환
            if isinstance(row_dict.get("strategy"), MigrationStrategy):
                row_dict["strategy"] = row_dict["strategy"].value
            result.append(row_dict)

        return result
