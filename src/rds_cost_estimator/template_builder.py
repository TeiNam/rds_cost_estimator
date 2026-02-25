"""
템플릿 v2 데이터 구성 모듈.

_fill_* 메서드들을 TemplateBuilder 클래스로 모아
estimator.py에서 위임 호출합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from rds_cost_estimator.db_store import DuckDBStore
from rds_cost_estimator.instance_utils import (
    AURORA_ENGINES,
    NET_CROSS_AZ_PER_GB,
    NET_CROSS_REGION_PER_GB,
    ORACLE_ENGINES,
    _NETWORK_STATIC_KEYS,
    _NETWORK_YEARLY_KEY_PATTERNS,
    calc_aurora_storage_costs,
    calc_storage_costs,
    get_instance_specs,
    get_region_pricing,
)
from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    ParsedDocumentInfo,
    PricingType,
)


class TemplateBuilder:
    """템플릿 v2 플레이스홀더 데이터를 구성하는 클래스."""

    def __init__(self, db_store: Optional[DuckDBStore], args: CLIArgs) -> None:
        self._db_store = db_store
        self._args = args

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def build(
        self,
        parsed: ParsedDocumentInfo,
        price_index: dict,
        refac_price_index: dict,
        spec_instances: dict[str, str],
        sga_instances: dict[str, str],
        family_a: str,
        family_b: Optional[str],
    ) -> dict:
        """전체 템플릿 데이터를 구성합니다."""
        args = self._args
        data: dict = {}
        families = [family_a]
        if family_b:
            families.append(family_b)

        # 패밀리 이름 주입
        data["family_a"] = family_a
        data["family_b"] = family_b or "N/A"

        # 리포트 개요
        data["db_name"] = parsed.db_name or "Unknown"
        data["oracle_version"] = parsed.oracle_version or "N/A"
        data["aws_region"] = args.region
        data["report_date"] = datetime.now().strftime("%Y-%m-%d")
        data["pricing_date"] = datetime.now().strftime("%Y-%m-%d")

        # 현재 서버 사양
        data["cpu_cores"] = parsed.cpu_cores or "N/A"
        data["physical_memory"] = parsed.physical_memory_gb or "N/A"
        data["db_size"] = parsed.db_size_gb or "N/A"
        data["instance_config"] = parsed.instance_config or "N/A"

        # AWR 성능 메트릭
        awr = parsed.awr_metrics
        data["avg_cpu"] = awr.avg_cpu_percent or "N/A"
        data["peak_cpu"] = awr.peak_cpu_percent or "N/A"

        # CPU/s (초당 DB CPU 사용량) - 참고 메트릭으로 추가
        data["avg_cpu_per_s"] = awr.avg_cpu_per_s or "N/A"
        data["peak_cpu_per_s"] = awr.peak_cpu_per_s or "N/A"
        data["avg_iops"] = awr.avg_iops or "N/A"
        data["peak_iops"] = awr.peak_iops or "N/A"
        data["avg_memory"] = awr.avg_memory_gb or "N/A"
        data["peak_memory"] = awr.peak_memory_gb or "N/A"

        # SGA 분석
        sga = parsed.sga_analysis
        data["current_sga"] = sga.current_sga_gb or "N/A"
        data["recommended_sga"] = sga.recommended_sga_gb or "N/A"
        if sga.current_sga_gb and sga.recommended_sga_gb and sga.current_sga_gb > 0:
            data["sga_increase_rate"] = round(
                (sga.recommended_sga_gb - sga.current_sga_gb) / sga.current_sga_gb * 100, 1
            )
        else:
            data["sga_increase_rate"] = sga.sga_increase_rate_percent or "N/A"

        data["buffer_rate"] = 20

        # 스토리지 증가 추이
        sg = parsed.storage_growth
        db_size = parsed.db_size_gb or 0
        growth_rate = (sg.yearly_growth_rate_percent or 15) / 100
        yearly_growth_gb = sg.yearly_growth_gb or (db_size * growth_rate)

        data["yearly_growth"] = round(yearly_growth_gb, 1) if yearly_growth_gb else "N/A"
        data["yearly_growth_rate"] = round(growth_rate * 100, 1)

        # 연도별 DB 크기 예측
        data["db_size_1y"] = round(db_size * (1 + growth_rate), 1) if db_size else "N/A"
        data["db_size_2y"] = round(db_size * (1 + growth_rate) ** 2, 1) if db_size else "N/A"
        data["db_size_3y"] = round(db_size * (1 + growth_rate) ** 3, 1) if db_size else "N/A"

        # 스토리지 비용
        prov_iops = parsed.provisioned_iops or 0
        prov_tp = parsed.provisioned_throughput_mbps or 0

        if args.engine in AURORA_ENGINES:
            # Aurora: 클러스터 스토리지 (IOPS/처리량 프로비저닝 없음)
            data["storage_type"] = "Aurora 클러스터 스토리지"
            data["storage_price_per_gb"] = "$0.10/GB-월"
            data["storage_pricing_detail"] = "Aurora I/O-Optimized 선택 시 $0.13/GB-월 (I/O 무료)."
            data["provisioned_iops"] = "해당 없음"
            data["provisioned_throughput"] = "해당 없음"
            data["storage_note"] = "Aurora는 3AZ 6카피 복제가 기본 포함되어 Multi-AZ 추가 스토리지 비용이 없습니다."
            data["maz_storage_note"] = (
                "Aurora는 3AZ 6카피 복제가 기본 포함되어 스토리지 추가 비용이 없습니다. "
                "네트워크는 복제 트래픽 무료이나 Cross-AZ App 비용은 동일 적용."
            )
            data["storage_config_rows"] = (
                "| 스토리지 단가 | $0.10/GB-월 (Aurora Standard) |\n"
                "| I/O 과금 | Aurora Standard: $0.20/100만 요청, I/O-Optimized: 무료 |\n"
                "| 복제 | 3AZ 6카피 자동 복제 (추가 비용 없음) |"
            )
            data["storage_extra_cost_rows"] = ""
        else:
            data["storage_type"] = "gp3 (범용 SSD)"
            data["storage_price_per_gb"] = "$0.08/GB-월"
            data["storage_pricing_detail"] = "추가 IOPS: $0.02/IOPS-월 (3,000 초과분). 추가 처리량: $0.04/MB/s-월 (125 MB/s 초과분)."
            data["provisioned_iops"] = prov_iops if prov_iops else "없음"
            data["provisioned_throughput"] = prov_tp if prov_tp else "없음"
            data["storage_note"] = ""
            data["maz_storage_note"] = "스토리지 2배, 네트워크는 복제 트래픽 무료이나 Cross-AZ App 비용은 동일 적용."
            data["storage_config_rows"] = (
                "| 기본 IOPS | 3,000 (gp3 기본 제공) |\n"
                "| 기본 처리량 | 125 MB/s (gp3 기본 제공) |\n"
                f"| 프로비저닝 IOPS | {prov_iops if prov_iops else '없음'} (추가 필요 시) |\n"
                f"| 프로비저닝 처리량 | {prov_tp if prov_tp else '없음'} MB/s (추가 필요 시) |"
            )

        self._fill_storage_costs(data, db_size, growth_rate, prov_iops, prov_tp, args.region)

        # gp3 추가 비용 행은 _fill_storage_costs 이후에 설정 (iops_cost/throughput_cost 참조)
        if args.engine not in AURORA_ENGINES:
            data["storage_extra_cost_rows"] = (
                f"| 추가 IOPS 비용 | ${data['iops_cost']}/월 | ${data['iops_cost']}/월 "
                f"| ${data['iops_cost']}/월 | ${data['iops_cost']}/월 |\n"
                f"| 추가 처리량 비용 | ${data['throughput_cost']}/월 | ${data['throughput_cost']}/월 "
                f"| ${data['throughput_cost']}/월 | ${data['throughput_cost']}/월 |\n"
            )

        # 네트워크 비용 (DuckDB에서 조회)
        self._fill_network_costs(data, growth_rate)

        # 인스턴스 권장 사양 (동적 패밀리)
        self._fill_instance_specs(data, spec_instances, families, "spec")
        self._fill_instance_specs(data, sga_instances, families, "sga")

        # 인스턴스 + 스토리지 + 네트워크 통합 비용 (동적 패밀리)
        self._fill_pricing(data, price_index, spec_instances, families, "spec")
        self._fill_pricing(data, price_index, sga_instances, families, "sga")

        # 비교 요약 + TCO (동적 패밀리)
        self._fill_comparison(data, families)
        self._fill_tco(data, families, db_size, growth_rate, prov_iops, prov_tp, args.region)

        # Replatform vs Refactoring 비용 비교 (Oracle 엔진 전용)
        if args.engine in ORACLE_ENGINES and refac_price_index:
            self._fill_refactoring_comparison(
                data, refac_price_index, sga_instances, families,
            )
            data["refac_section_visible"] = True
        else:
            self._fill_refactoring_defaults(data, families)
            data["refac_section_visible"] = False

        return data

    # ------------------------------------------------------------------
    # 비공개 메서드: 스토리지/네트워크
    # ------------------------------------------------------------------

    def _fill_storage_costs(self, data: dict, db_size: float, growth_rate: float,
                            prov_iops: int, prov_tp: float,
                            region: str = "ap-northeast-2") -> None:
        """연도별 스토리지 비용을 계산하여 data에 채웁니다.

        Aurora 엔진인 경우 클러스터 스토리지 요금을 적용하고,
        그 외 엔진은 gp3 스토리지 요금을 적용합니다.
        """
        is_aurora = self._args.engine in AURORA_ENGINES

        for year in range(4):
            size = db_size * (1 + growth_rate) ** year if db_size else 0

            if is_aurora:
                costs = calc_aurora_storage_costs(size)
            else:
                costs = calc_storage_costs(size, prov_iops, prov_tp, region=region)

            suffix = f"_{year}y"
            data[f"stor_cost{suffix}"] = f"{costs['storage']:,.2f}"
            data["iops_cost"] = f"{costs['iops']:,.2f}"
            data["throughput_cost"] = f"{costs['throughput']:,.2f}"
            data[f"stor_total{suffix}"] = f"{costs['total']:,.2f}"
            data[f"stor_yearly{suffix}"] = f"{costs['total'] * 12:,.2f}"

            if is_aurora:
                # Aurora는 3AZ 6카피 복제가 기본 포함 → Multi-AZ 추가 스토리지 비용 없음
                data[f"stor_maz_total{suffix}"] = f"{costs['total']:,.2f}"
            else:
                # RDS: Multi-AZ 스토리지 2배
                data[f"stor_maz_total{suffix}"] = f"{costs['total'] * 2:,.2f}"

    def _fill_network_costs(self, data: dict, growth_rate: float) -> None:
        """DuckDB에서 네트워크 트래픽을 조회하여 비용을 계산합니다."""
        if not self._db_store:
            self._fill_network_defaults(data)
            return

        net = self._db_store.get_network_traffic_summary()

        # 리전별 네트워크 요금 조회
        rp = get_region_pricing(self._args.region)
        cross_az_rate = rp["cross_az_per_gb"]
        cross_region_rate = rp["cross_region_per_gb"]

        # AWR 기반 네트워크 트래픽 (일별/월별)
        sent_daily = net["sent_daily_gb"]
        recv_daily = net["recv_daily_gb"]
        redo_daily = net["redo_daily_gb"]
        dblink_daily = 0.0

        data["sqlnet_recv_daily"] = f"{recv_daily:,.2f}"
        data["sqlnet_sent_daily"] = f"{sent_daily:,.2f}"
        data["sqlnet_recv_monthly"] = f"{recv_daily * 30:,.2f}"
        data["sqlnet_sent_monthly"] = f"{sent_daily * 30:,.2f}"
        data["dblink_daily"] = f"{dblink_daily:,.2f}"
        data["dblink_monthly"] = f"{dblink_daily * 30:,.2f}"
        data["redo_daily"] = f"{redo_daily:,.2f}"
        data["redo_monthly"] = f"{redo_daily * 30:,.2f}"

        total_daily = sent_daily + recv_daily + dblink_daily + redo_daily
        total_monthly = total_daily * 30
        data["net_total_daily"] = f"{total_daily:,.2f}"
        data["net_total_monthly"] = f"{total_monthly:,.2f}"

        # 클라이언트 트래픽 (송수신 합계)
        client_monthly = (sent_daily + recv_daily) * 30

        # Cross-AZ: 클라이언트 트래픽 × 리전별 요금 × 2(양방향)
        cross_az_cost = client_monthly * cross_az_rate * 2
        data["net_cost_cross_az"] = f"{cross_az_cost:,.2f}"
        data["net_cost_cross_az_yearly"] = f"{cross_az_cost * 12:,.2f}"

        # Multi-AZ (Cross-AZ App): 클라이언트 트래픽만 (복제는 무료)
        data["net_cost_maz_cross_az"] = f"{cross_az_cost:,.2f}"
        data["net_cost_maz_cross_az_yearly"] = f"{cross_az_cost * 12:,.2f}"

        # + Read Replica (Cross-AZ)
        redo_monthly = redo_daily * 30
        rr_cross_az_cost = cross_az_cost + redo_monthly * cross_az_rate
        data["net_cost_rr_cross_az"] = f"{rr_cross_az_cost:,.2f}"
        data["net_cost_rr_cross_az_yearly"] = f"{rr_cross_az_cost * 12:,.2f}"

        # + Read Replica (Cross-Region)
        rr_cross_region_cost = cross_az_cost + redo_monthly * cross_region_rate
        data["net_cost_rr_cross_region"] = f"{rr_cross_region_cost:,.2f}"
        data["net_cost_rr_cross_region_yearly"] = f"{rr_cross_region_cost * 12:,.2f}"

        # 기본 시나리오: Cross-AZ
        data["net_monthly"] = f"{cross_az_cost:,.2f}"
        data["net_maz_monthly"] = f"{cross_az_cost:,.2f}"
        data["net_scenario"] = "Single-AZ (Cross-AZ App)"

        # 연도별 네트워크 비용 예측 (스토리지 증가율 적용)
        for yr in range(1, 4):
            factor = (1 + growth_rate) ** yr
            yr_total_monthly = total_monthly * factor
            yr_cross_az = cross_az_cost * factor
            yr_cross_az_yearly = yr_cross_az * 12

            data[f"net_total_monthly_{yr}y"] = f"{yr_total_monthly:,.2f}"
            data[f"net_cost_cross_az_{yr}y"] = f"{yr_cross_az:,.2f}"
            data[f"net_cost_cross_az_yearly_{yr}y"] = f"{yr_cross_az_yearly:,.2f}"

    def _fill_network_defaults(self, data: dict) -> None:
        """네트워크 데이터가 없을 때 기본값으로 채웁니다."""
        for k in _NETWORK_STATIC_KEYS:
            data[k] = "0.00"
        data["net_scenario"] = "N/A"
        for yr in range(1, 4):
            for pattern in _NETWORK_YEARLY_KEY_PATTERNS:
                data[pattern.format(yr=yr)] = "0.00"

    # ------------------------------------------------------------------
    # 비공개 메서드: 인스턴스 사양 및 가격
    # ------------------------------------------------------------------

    def _fill_instance_specs(self, data: dict, instances: dict[str, str],
                              families: list[str], prefix: str) -> None:
        """인스턴스 사양 정보를 data에 채웁니다 (동적 패밀리)."""
        for family in families:
            inst = instances.get(family)
            key_prefix = f"{prefix}_{family}"
            data[f"{key_prefix}_instance"] = inst or "N/A"
            if inst:
                specs = get_instance_specs(inst)
                if specs:
                    data[f"{key_prefix}_vcpu"] = specs["vcpu"]
                    data[f"{key_prefix}_memory"] = specs["memory_gb"]
                    data[f"{key_prefix}_network"] = specs["network_gbps"]
                else:
                    data[f"{key_prefix}_vcpu"] = "N/A"
                    data[f"{key_prefix}_memory"] = "N/A"
                    data[f"{key_prefix}_network"] = "N/A"
            else:
                data[f"{key_prefix}_vcpu"] = "N/A"
                data[f"{key_prefix}_memory"] = "N/A"
                data[f"{key_prefix}_network"] = "N/A"

    def _get_monthly(self, price_index: dict, inst: str, deploy: str,
                     pt: PricingType) -> Optional[float]:
        """price_index에서 월간 비용을 조회합니다."""
        rec = price_index.get((inst, deploy, pt))
        if rec and rec.is_available and rec.monthly_cost is not None:
            return round(rec.monthly_cost, 2)
        return None

    def _fill_pricing(self, data: dict, price_index: dict,
                      instances: dict[str, str], families: list[str],
                      prefix: str) -> None:
        """인스턴스 + 스토리지 + 네트워크 통합 비용을 data에 채웁니다 (동적 패밀리)."""
        stor_monthly = float(data.get("stor_total_0y", "0").replace(",", ""))
        stor_maz_monthly = float(data.get("stor_maz_total_0y", "0").replace(",", ""))
        net_monthly = float(data.get("net_monthly", "0").replace(",", ""))
        net_maz_monthly = float(data.get("net_maz_monthly", "0").replace(",", ""))

        pricing_options = [
            ("od", PricingType.ON_DEMAND),
            ("ri1nu", PricingType.RI_1YR_NO_UPFRONT),
            ("ri1au", PricingType.RI_1YR_ALL_UPFRONT),
            ("ri3nu", PricingType.RI_3YR_NO_UPFRONT),
            ("ri3au", PricingType.RI_3YR_ALL_UPFRONT),
        ]

        for family in families:
            inst = instances.get(family)
            if not inst:
                continue
            key_base = f"{prefix}_{family}"

            # Single-AZ
            for opt_key, pt in pricing_options:
                monthly = self._get_monthly(price_index, inst, "Single-AZ", pt)
                k = f"{key_base}_{opt_key}_monthly"
                data[k] = f"{monthly:,.2f}" if monthly else "N/A"

                if monthly is not None:
                    total_m = monthly + stor_monthly + net_monthly
                    total_y = total_m * 12
                    data[f"{key_base}_{opt_key}_total_monthly"] = f"{total_m:,.2f}"
                    data[f"{key_base}_{opt_key}_total_yearly"] = f"{total_y:,.2f}"
                else:
                    data[f"{key_base}_{opt_key}_total_monthly"] = "N/A"
                    data[f"{key_base}_{opt_key}_total_yearly"] = "N/A"

            # Multi-AZ
            for opt_key, pt in pricing_options:
                monthly = self._get_monthly(price_index, inst, "Multi-AZ", pt)
                k = f"{key_base}_maz_{opt_key}_monthly"
                data[k] = f"{monthly:,.2f}" if monthly else "N/A"

                if monthly is not None:
                    total_m = monthly + stor_maz_monthly + net_maz_monthly
                    total_y = total_m * 12
                    data[f"{key_base}_maz_{opt_key}_total_monthly"] = f"{total_m:,.2f}"
                    data[f"{key_base}_maz_{opt_key}_total_yearly"] = f"{total_y:,.2f}"
                else:
                    data[f"{key_base}_maz_{opt_key}_total_monthly"] = "N/A"
                    data[f"{key_base}_maz_{opt_key}_total_yearly"] = "N/A"

    # ------------------------------------------------------------------
    # 비공개 메서드: 비교 및 TCO
    # ------------------------------------------------------------------

    def _fill_comparison(self, data: dict, families: list[str]) -> None:
        """전체 비용 비교 요약 (섹션 7) 데이터를 채웁니다 (동적 패밀리)."""
        options = [
            ("od", "od"), ("ri1nu", "ri1nu"), ("ri1au", "ri1au"),
            ("ri3nu", "ri3nu"), ("ri3au", "ri3au"),
        ]
        for prefix in ["spec", "sga"]:
            for family in families:
                for comp_key, opt_key in options:
                    src = f"{prefix}_{family}_{opt_key}_total_yearly"
                    dst = f"comp_{prefix}_{family}_{comp_key}"
                    data[dst] = data.get(src, "N/A")

    def _fill_tco(self, data: dict, families: list[str], db_size: float,
                  growth_rate: float, prov_iops: int, prov_tp: float,
                  region: str = "ap-northeast-2") -> None:
        """3년 TCO 비교 데이터를 채웁니다 (동적 패밀리)."""
        # 연도별 스토리지 비용 (1년차~3년차, 증가율 반영)
        is_aurora = self._args.engine in AURORA_ENGINES
        yearly_stor: list[float] = []
        for year in range(1, 4):
            size = db_size * (1 + growth_rate) ** year if db_size else 0
            if is_aurora:
                costs = calc_aurora_storage_costs(size)
            else:
                costs = calc_storage_costs(size, prov_iops, prov_tp, region=region)
            yearly_stor.append(costs["total"] * 12)

        stor_3yr_total = sum(yearly_stor)

        # 연도별 네트워크 비용 (1년차~3년차, 증가율 반영)
        net_monthly_base = float(data.get("net_monthly", "0").replace(",", ""))
        yearly_net: list[float] = []
        for year in range(1, 4):
            factor = (1 + growth_rate) ** year
            yearly_net.append(net_monthly_base * factor * 12)
        net_3yr_total = sum(yearly_net)

        for prefix in ["spec", "sga"]:
            for family in families:
                # On-Demand 3년
                inst_monthly_str = data.get(f"{prefix}_{family}_od_monthly", "N/A")
                if inst_monthly_str != "N/A":
                    inst_yearly = float(inst_monthly_str.replace(",", "")) * 12
                    tco_od = inst_yearly * 3 + stor_3yr_total + net_3yr_total
                    data[f"tco_{prefix}_{family}_od"] = f"{tco_od:,.2f}"
                else:
                    data[f"tco_{prefix}_{family}_od"] = "N/A"

                # 1년 RI × 3회 (All Upfront 기준)
                inst_monthly_str = data.get(f"{prefix}_{family}_ri1au_monthly", "N/A")
                if inst_monthly_str != "N/A":
                    inst_yearly = float(inst_monthly_str.replace(",", "")) * 12
                    tco_ri1 = inst_yearly * 3 + stor_3yr_total + net_3yr_total
                    data[f"tco_{prefix}_{family}_ri1"] = f"{tco_ri1:,.2f}"
                else:
                    data[f"tco_{prefix}_{family}_ri1"] = "N/A"

                # 3년 RI 1회 (All Upfront 기준)
                inst_monthly_str = data.get(f"{prefix}_{family}_ri3au_monthly", "N/A")
                if inst_monthly_str != "N/A":
                    inst_yearly = float(inst_monthly_str.replace(",", "")) * 12
                    tco_ri3 = inst_yearly * 3 + stor_3yr_total + net_3yr_total
                    data[f"tco_{prefix}_{family}_ri3"] = f"{tco_ri3:,.2f}"
                else:
                    data[f"tco_{prefix}_{family}_ri3"] = "N/A"

        # TCO 상세 (최적 시나리오: SGA 최적화 + 3년 RI)
        for family in families:
            inst_monthly_str = data.get(f"sga_{family}_ri3au_monthly", "N/A")
            for yr_idx in range(3):
                yr = yr_idx + 1
                stor_yr = yearly_stor[yr_idx] if yr_idx < len(yearly_stor) else 0
                net_yr = yearly_net[yr_idx] if yr_idx < len(yearly_net) else 0

                if inst_monthly_str != "N/A":
                    inst_yr = float(inst_monthly_str.replace(",", "")) * 12
                    data[f"tco_detail_{family}_inst_{yr}y"] = f"{inst_yr:,.2f}"
                    data[f"tco_detail_stor_{yr}y"] = f"{stor_yr:,.2f}"
                    data[f"tco_detail_net_{yr}y"] = f"{net_yr:,.2f}"
                    data[f"tco_detail_{family}_{yr}y"] = f"{inst_yr + stor_yr + net_yr:,.2f}"
                else:
                    data[f"tco_detail_{family}_inst_{yr}y"] = "N/A"
                    data[f"tco_detail_stor_{yr}y"] = f"{stor_yr:,.2f}"
                    data[f"tco_detail_net_{yr}y"] = f"{net_yr:,.2f}"
                    data[f"tco_detail_{family}_{yr}y"] = "N/A"

            # 3년 합계
            if inst_monthly_str != "N/A":
                inst_3yr = float(inst_monthly_str.replace(",", "")) * 12 * 3
                data[f"tco_detail_{family}_inst_total"] = f"{inst_3yr:,.2f}"
                data[f"tco_detail_stor_total"] = f"{stor_3yr_total:,.2f}"
                data[f"tco_detail_net_total"] = f"{net_3yr_total:,.2f}"
                data[f"tco_detail_{family}_total"] = f"{inst_3yr + stor_3yr_total + net_3yr_total:,.2f}"
            else:
                data[f"tco_detail_{family}_inst_total"] = "N/A"
                data[f"tco_detail_stor_total"] = f"{stor_3yr_total:,.2f}"
                data[f"tco_detail_net_total"] = f"{net_3yr_total:,.2f}"
                data[f"tco_detail_{family}_total"] = "N/A"

    # ------------------------------------------------------------------
    # Replatform vs Refactoring 비용 비교 (요구사항 16)
    # ------------------------------------------------------------------

    def _fill_refactoring_comparison(
        self,
        data: dict,
        refac_price_index: dict,
        sga_instances: dict[str, str],
        families: list[str],
    ) -> None:
        """SGA 최적화 인스턴스 기준 Replatform vs Refactoring(Aurora PostgreSQL) 비용 비교."""
        stor_monthly = float(data.get("stor_total_0y", "0").replace(",", ""))
        net_monthly = float(data.get("net_monthly", "0").replace(",", ""))

        pricing_options = [
            ("od", PricingType.ON_DEMAND),
            ("ri1nu", PricingType.RI_1YR_NO_UPFRONT),
            ("ri1au", PricingType.RI_1YR_ALL_UPFRONT),
            ("ri3nu", PricingType.RI_3YR_NO_UPFRONT),
            ("ri3au", PricingType.RI_3YR_ALL_UPFRONT),
        ]

        for family in families:
            inst = sga_instances.get(family)
            if not inst:
                for opt_key, _ in pricing_options:
                    data[f"refac_{family}_{opt_key}_monthly"] = "N/A"
                    data[f"refac_{family}_{opt_key}_total_yearly"] = "N/A"
                    data[f"refac_{family}_{opt_key}_savings"] = "N/A"
                    data[f"refac_{family}_{opt_key}_savings_rate"] = "N/A"
                continue

            for opt_key, pt in pricing_options:
                refac_monthly = self._get_monthly(refac_price_index, inst, "Single-AZ", pt)

                if refac_monthly is not None:
                    refac_total_m = refac_monthly + stor_monthly + net_monthly
                    refac_total_y = refac_total_m * 12
                    data[f"refac_{family}_{opt_key}_monthly"] = f"{refac_monthly:,.2f}"
                    data[f"refac_{family}_{opt_key}_total_yearly"] = f"{refac_total_y:,.2f}"

                    replat_key = f"sga_{family}_{opt_key}_total_yearly"
                    replat_yearly_str = data.get(replat_key, "N/A")

                    if replat_yearly_str != "N/A":
                        replat_y = float(replat_yearly_str.replace(",", ""))
                        savings = replat_y - refac_total_y
                        savings_rate = (savings / replat_y * 100) if replat_y > 0 else 0
                        data[f"refac_{family}_{opt_key}_savings"] = f"{savings:,.2f}"
                        data[f"refac_{family}_{opt_key}_savings_rate"] = f"{savings_rate:.1f}"
                    else:
                        data[f"refac_{family}_{opt_key}_savings"] = "N/A"
                        data[f"refac_{family}_{opt_key}_savings_rate"] = "N/A"
                else:
                    data[f"refac_{family}_{opt_key}_monthly"] = "N/A"
                    data[f"refac_{family}_{opt_key}_total_yearly"] = "N/A"
                    data[f"refac_{family}_{opt_key}_savings"] = "N/A"
                    data[f"refac_{family}_{opt_key}_savings_rate"] = "N/A"

    def _fill_refactoring_defaults(self, data: dict, families: list[str]) -> None:
        """비Oracle 엔진 또는 Refactoring 조회 실패 시 기본값을 설정합니다."""
        pricing_options = ["od", "ri1nu", "ri1au", "ri3nu", "ri3au"]

        for family in families:
            for opt_key in pricing_options:
                data[f"refac_{family}_{opt_key}_monthly"] = "N/A"
                data[f"refac_{family}_{opt_key}_total_yearly"] = "N/A"
                data[f"refac_{family}_{opt_key}_savings"] = "N/A"
                data[f"refac_{family}_{opt_key}_savings_rate"] = "N/A"
