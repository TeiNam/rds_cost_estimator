"""
핵심 오케스트레이션 로직 모듈.

CLI 인수를 받아 InstanceSpec 목록을 생성하고,
AWS Pricing API를 병렬로 호출하여 비용 데이터를 수집합니다.
템플릿 v2에 필요한 스토리지/네트워크 비용도 계산합니다.
DuckDB를 통해 파싱 데이터를 저장하고 리포트 데이터를 추출합니다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import boto3

from rds_cost_estimator.bedrock_client import BedrockClient
from rds_cost_estimator.cost_table import CostTable
from rds_cost_estimator.db_store import DuckDBStore
from rds_cost_estimator.document_parser import DocumentParser
from rds_cost_estimator.exceptions import InvalidInputError
from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    InstanceFamily,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
)
from rds_cost_estimator.pricing_client import PricingClient

logger = logging.getLogger(__name__)

REFACTORING_ENGINE = "aurora-postgresql"

_INSTANCE_PATTERN = re.compile(r"^db\.([a-z0-9]+)\.(.+)$")
ORACLE_ENGINES = {"oracle-ee", "oracle-se2"}
GRAVITON_FAMILIES = {"r7g", "r6g", "r8g"}

# gp3 스토리지 요금 (ap-northeast-2 기준, USD)
GP3_STORAGE_PER_GB = 0.08
GP3_IOPS_PER_UNIT = 0.02  # 3000 초과분
GP3_THROUGHPUT_PER_MBPS = 0.04  # 125 MB/s 초과분
GP3_BASE_IOPS = 3000
GP3_BASE_THROUGHPUT = 125  # MB/s

# Aurora 클러스터 스토리지 요금 (ap-northeast-2 기준, USD)
# Aurora Standard: I/O 요청당 과금, 스토리지 $0.10/GB-월
# Aurora I/O-Optimized: I/O 무료, 스토리지 $0.13/GB-월 (30% 할증)
# Aurora는 3AZ 6카피 복제가 기본 포함 → Multi-AZ 스토리지 추가 비용 없음
AURORA_STORAGE_PER_GB = 0.10  # Aurora Standard 기준
AURORA_IO_PER_MILLION = 0.20  # I/O 요청 100만 건당 (Aurora Standard)
AURORA_BACKUP_PER_GB = 0.021  # 백업 스토리지 (보관 기간 초과분)

# Aurora 엔진 목록 (클러스터 스토리지 사용)
AURORA_ENGINES = {"aurora-postgresql", "aurora-mysql"}

# 네트워크 비용 상수
NET_CROSS_AZ_PER_GB = 0.01
NET_CROSS_REGION_PER_GB = 0.02

# r6i/r7i 인스턴스 사양 테이블
INSTANCE_SPECS = {
    "db.r6i.large": {"vcpu": 2, "memory_gb": 16, "network_gbps": 12.5},
    "db.r6i.xlarge": {"vcpu": 4, "memory_gb": 32, "network_gbps": 12.5},
    "db.r6i.2xlarge": {"vcpu": 8, "memory_gb": 64, "network_gbps": 12.5},
    "db.r6i.4xlarge": {"vcpu": 16, "memory_gb": 128, "network_gbps": 12.5},
    "db.r6i.8xlarge": {"vcpu": 32, "memory_gb": 256, "network_gbps": 12.5},
    "db.r6i.12xlarge": {"vcpu": 48, "memory_gb": 384, "network_gbps": 18.75},
    "db.r6i.16xlarge": {"vcpu": 64, "memory_gb": 512, "network_gbps": 25.0},
    "db.r6i.24xlarge": {"vcpu": 96, "memory_gb": 768, "network_gbps": 37.5},
    "db.r7i.large": {"vcpu": 2, "memory_gb": 16, "network_gbps": 12.5},
    "db.r7i.xlarge": {"vcpu": 4, "memory_gb": 32, "network_gbps": 12.5},
    "db.r7i.2xlarge": {"vcpu": 8, "memory_gb": 64, "network_gbps": 12.5},
    "db.r7i.4xlarge": {"vcpu": 16, "memory_gb": 128, "network_gbps": 12.5},
    "db.r7i.8xlarge": {"vcpu": 32, "memory_gb": 256, "network_gbps": 12.5},
    "db.r7i.12xlarge": {"vcpu": 48, "memory_gb": 384, "network_gbps": 18.75},
    "db.r7i.16xlarge": {"vcpu": 64, "memory_gb": 512, "network_gbps": 25.0},
    "db.r7i.24xlarge": {"vcpu": 96, "memory_gb": 768, "network_gbps": 37.5},
}


def expand_instance_families(
    instance_type: str,
    exclude_graviton: bool = False,
) -> list[str]:
    """하나의 인스턴스 유형에서 동일 사이즈의 r6i/r7i/r7g 변형을 생성."""
    match = _INSTANCE_PATTERN.match(instance_type)
    if not match:
        return [instance_type]

    size = match.group(2)
    variants: list[str] = []
    seen: set[str] = set()

    for family in InstanceFamily.all_families():
        if exclude_graviton and family in GRAVITON_FAMILIES:
            continue
        variant = f"db.{family}.{size}"
        if variant not in seen:
            seen.add(variant)
            variants.append(variant)

    return variants


def find_matching_instance(memory_gb: float, family: str = "r6i") -> Optional[str]:
    """메모리 기준으로 적합한 인스턴스 타입을 찾습니다."""
    prefix = f"db.{family}."
    candidates = [
        (k, v) for k, v in INSTANCE_SPECS.items()
        if k.startswith(prefix)
    ]
    candidates.sort(key=lambda x: x[1]["memory_gb"])

    for inst_type, specs in candidates:
        if specs["memory_gb"] >= memory_gb:
            return inst_type

    if candidates:
        return candidates[-1][0]
    return None


def calc_storage_costs(
    db_size_gb: float,
    provisioned_iops: int = 0,
    provisioned_throughput_mbps: float = 0,
) -> dict:
    """gp3 스토리지 월간 비용 계산."""
    storage_cost = db_size_gb * GP3_STORAGE_PER_GB
    extra_iops = max(0, provisioned_iops - GP3_BASE_IOPS) if provisioned_iops else 0
    iops_cost = extra_iops * GP3_IOPS_PER_UNIT
    extra_tp = max(0, provisioned_throughput_mbps - GP3_BASE_THROUGHPUT) if provisioned_throughput_mbps else 0
    throughput_cost = extra_tp * GP3_THROUGHPUT_PER_MBPS

    return {
        "storage": round(storage_cost, 2),
        "iops": round(iops_cost, 2),
        "throughput": round(throughput_cost, 2),
        "total": round(storage_cost + iops_cost + throughput_cost, 2),
    }

def calc_aurora_storage_costs(db_size_gb: float) -> dict:
    """Aurora 클러스터 스토리지 월간 비용 계산.

    Aurora는 gp3와 달리:
    - IOPS/처리량 프로비저닝 개념 없음 (자동 확장)
    - 3AZ 6카피 복제가 기본 포함 → Multi-AZ 추가 스토리지 비용 없음
    - I/O 비용은 워크로드에 따라 달라지므로 별도 표기
    """
    storage_cost = db_size_gb * AURORA_STORAGE_PER_GB

    return {
        "storage": round(storage_cost, 2),
        "iops": 0.0,       # Aurora는 IOPS 프로비저닝 없음
        "throughput": 0.0,  # Aurora는 처리량 프로비저닝 없음
        "total": round(storage_cost, 2),
    }



class Estimator:
    """비용 예측기 핵심 오케스트레이션 클래스."""

    def __init__(self, args: CLIArgs) -> None:
        self._args = args
        if args.profile:
            self._session = boto3.Session(profile_name=args.profile)
        else:
            self._session = boto3.Session()
        self._pricing_client = PricingClient(self._session, cache={})
        self._db_store: Optional[DuckDBStore] = None

    def _build_specs(self, deployment: str = "Single-AZ") -> list[InstanceSpec]:
        """InstanceSpec 목록 생성 (Single-AZ 또는 Multi-AZ)."""
        specs: list[InstanceSpec] = []
        args = self._args
        is_oracle = args.engine in ORACLE_ENGINES

        source_instances: list[str] = []
        if args.current_instance:
            source_instances.append(args.current_instance)
        if args.recommended_instance_by_size:
            source_instances.append(args.recommended_instance_by_size)
        if args.recommended_instance_by_sga:
            source_instances.append(args.recommended_instance_by_sga)

        replatform_instances: list[str] = []
        seen_rp: set[str] = set()
        for inst in source_instances:
            for variant in expand_instance_families(inst, exclude_graviton=is_oracle):
                if variant not in seen_rp:
                    seen_rp.add(variant)
                    replatform_instances.append(variant)

        refactoring_instances: list[str] = []
        seen_rf: set[str] = set()
        for inst in source_instances:
            for variant in expand_instance_families(inst, exclude_graviton=False):
                if variant not in seen_rf:
                    seen_rf.add(variant)
                    refactoring_instances.append(variant)

        for instance_type in replatform_instances:
            specs.append(InstanceSpec(
                instance_type=instance_type,
                region=args.region,
                engine=args.engine,
                strategy=MigrationStrategy.REPLATFORM,
                deployment_option=deployment,
            ))

        for instance_type in refactoring_instances:
            specs.append(InstanceSpec(
                instance_type=instance_type,
                region=args.region,
                engine=REFACTORING_ENGINE,
                strategy=MigrationStrategy.REFACTORING,
                deployment_option=deployment,
            ))

        return specs

    def _merge_parsed_info(self, parsed: ParsedDocumentInfo) -> None:
        """ParsedDocumentInfo의 필드로 CLIArgs의 누락 필드를 보완."""
        if self._args.current_instance is None and parsed.current_instance is not None:
            self._args.current_instance = parsed.current_instance
        if (
            self._args.recommended_instance_by_size is None
            and parsed.recommended_instance_by_size is not None
        ):
            self._args.recommended_instance_by_size = parsed.recommended_instance_by_size
        if (
            self._args.recommended_instance_by_sga is None
            and parsed.recommended_instance_by_sga is not None
        ):
            self._args.recommended_instance_by_sga = parsed.recommended_instance_by_sga
        if self._args.on_prem_cost is None and parsed.on_prem_cost is not None:
            self._args.on_prem_cost = parsed.on_prem_cost
        # 타겟 엔진 결정: target_engine > engine (소스 엔진은 무시)
        if parsed.target_engine is not None:
            self._args.engine = parsed.target_engine
        elif parsed.engine is not None and self._args.engine == "oracle-ee":
            # target_engine이 없으면 기존 로직 유지 (소스 엔진 사용)
            self._args.engine = parsed.engine

    async def run(self) -> CostTable:
        """비용 예측 실행 (하위 호환용)."""
        args = self._args

        if args.input_file is not None:
            logger.info("문서 파일 파싱 시작: %s", args.input_file)
            bedrock_client = BedrockClient(
                session=self._session, model_id=args.bedrock_model,
            )
            parser = DocumentParser(bedrock_client=bedrock_client)
            parsed_info = parser.parse(args.input_file)
            self._merge_parsed_info(parsed_info)
            logger.info("문서 파싱 완료")

        if args.on_prem_cost is None or args.on_prem_cost <= 0:
            raise InvalidInputError(
                f"온프레미스 연간 유지비용은 0보다 커야 합니다. 입력값: {args.on_prem_cost}"
            )

        specs = self._build_specs()
        logger.info("InstanceSpec %d개 생성, 병렬 가격 조회 시작", len(specs))

        results = await asyncio.gather(
            *[self._pricing_client.fetch_all(spec) for spec in specs]
        )
        records = [r for spec_records in results for r in spec_records]
        logger.info("가격 조회 완료: 총 %d개의 CostRecord 수집", len(records))

        return CostTable(records=records, on_prem_annual_cost=args.on_prem_cost)

    async def run_v2(self) -> dict:
        """템플릿 v2 기반 비용 예측 실행. DuckDB에 데이터를 저장하고 리포트 데이터를 추출."""
        args = self._args
        parsed_info: Optional[ParsedDocumentInfo] = None

        # DuckDB 저장소 초기화
        self._db_store = DuckDBStore()

        # 문서 파싱
        if args.input_file is not None:
            logger.info("문서 파일 파싱 시작: %s", args.input_file)
            bedrock_client = BedrockClient(
                session=self._session, model_id=args.bedrock_model,
            )
            parser = DocumentParser(bedrock_client=bedrock_client)
            parsed_info = parser.parse(args.input_file)
            self._merge_parsed_info(parsed_info)
            logger.info("문서 파싱 완료")

        if parsed_info is None:
            parsed_info = ParsedDocumentInfo()

        # DuckDB에 파싱 데이터 저장
        self._db_store.store_parsed_info(parsed_info)

        # 인스턴스 사양 매칭
        spec_r6i = args.recommended_instance_by_size or args.current_instance
        spec_r7i = spec_r6i.replace("r6i", "r7i") if spec_r6i else None
        sga_r6i = args.recommended_instance_by_sga
        sga_r7i = sga_r6i.replace("r6i", "r7i") if sga_r6i else None

        # 가격 조회 대상 인스턴스
        target_instances = {i for i in [spec_r6i, spec_r7i, sga_r6i, sga_r7i] if i}

        # Single-AZ + Multi-AZ 스펙 생성
        all_specs: list[InstanceSpec] = []
        for inst in target_instances:
            for deploy in ["Single-AZ", "Multi-AZ"]:
                all_specs.append(InstanceSpec(
                    instance_type=inst,
                    region=args.region,
                    engine=args.engine,
                    strategy=MigrationStrategy.REPLATFORM,
                    deployment_option=deploy,
                ))

        logger.info("v2 InstanceSpec %d개 생성, 병렬 가격 조회 시작", len(all_specs))

        # 병렬 가격 조회
        results = await asyncio.gather(
            *[self._pricing_client.fetch_all(spec) for spec in all_specs]
        )
        all_records = [r for spec_records in results for r in spec_records]

        # DuckDB에 가격 데이터 저장
        self._db_store.store_pricing_records(all_records)

        # RI 폴백: is_available=False인 RI 레코드에 대해 RDS API로 조회
        await self._apply_ri_fallback()

        # 레코드를 인덱싱
        price_index: dict[tuple[str, str, PricingType], CostRecord] = {}
        for rec in all_records:
            key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
            price_index[key] = rec

        # 폴백 적용된 레코드 반영
        self._sync_fallback_to_index(price_index, all_records)

        # 템플릿 데이터 구성
        data = self._build_template_data(
            parsed_info, price_index, spec_r6i, spec_r7i, sga_r6i, sga_r7i
        )

        # DuckDB 연결 종료
        self._db_store.close()

        return data


    async def _apply_ri_fallback(self) -> None:
        """RI 가격이 없는 레코드에 대해 DescribeReservedDBInstancesOfferings API로 조회합니다."""
        if not self._db_store:
            return

        unavailable = self._db_store.get_unavailable_ri_records()
        if not unavailable:
            return

        logger.info(
            "RI 폴백 대상 %d건 발견, DescribeReservedDBInstancesOfferings API 조회 시작",
            len(unavailable),
        )

        for rec in unavailable:
            spec = InstanceSpec(
                instance_type=rec["instance_type"],
                region=rec["region"],
                engine=rec["engine"],
                strategy=MigrationStrategy.REPLATFORM,
                deployment_option=rec["deployment_option"],
            )
            pt_val = rec["pricing_type"]

            result = await self._pricing_client.fetch_ri_offering(spec, pt_val)
            if result and result.monthly_cost is not None:
                self._db_store.update_pricing_record(
                    rec["instance_type"],
                    rec["deployment_option"],
                    pt_val,
                    round(result.monthly_cost, 2),
                    round(result.annual_cost or 0, 2),
                )
                logger.info(
                    "RI 폴백 적용: %s / %s / %s → $%.2f/월",
                    rec["instance_type"], rec["deployment_option"],
                    pt_val, result.monthly_cost,
                )
            else:
                logger.warning(
                    "RI 폴백 실패: %s / %s / %s",
                    rec["instance_type"], rec["deployment_option"], pt_val,
                )

    def _sync_fallback_to_index(
        self,
        price_index: dict[tuple[str, str, PricingType], CostRecord],
        all_records: list[CostRecord],
    ) -> None:
        """DuckDB에서 폴백 적용된 레코드를 price_index에 반영합니다."""
        if not self._db_store:
            return

        for rec in all_records:
            if rec.is_available:
                continue

            pt_val = rec.pricing_type.value
            updated = self._db_store.get_pricing(
                rec.spec.instance_type, rec.spec.deployment_option, pt_val
            )
            if updated and updated.get("is_available"):
                # 폴백으로 업데이트된 레코드 반영
                rec.is_available = True
                rec.monthly_fee = updated["monthly_cost"]
                rec.annual_cost = updated["annual_cost"]
                key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
                price_index[key] = rec

    def _build_template_data(
        self,
        parsed: ParsedDocumentInfo,
        price_index: dict,
        spec_r6i: Optional[str],
        spec_r7i: Optional[str],
        sga_r6i: Optional[str],
        sga_r7i: Optional[str],
    ) -> dict:
        """템플릿 v2 플레이스홀더 데이터를 구성합니다."""
        from datetime import datetime

        args = self._args
        data: dict = {}

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

        # CPU 사용률: 퍼센트 값이 있으면 그대로 사용, 없으면 CPU/s 값을 표시
        avg_cpu = awr.avg_cpu_percent
        peak_cpu = awr.peak_cpu_percent

        data["avg_cpu"] = avg_cpu or "N/A"
        data["peak_cpu"] = peak_cpu or "N/A"

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

        # 스토리지 비용 계산 (iops_cost, throughput_cost 등 설정)
        self._fill_storage_costs(data, db_size, growth_rate, prov_iops, prov_tp)

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

        # 인스턴스 권장 사양
        self._fill_instance_specs(data, spec_r6i, spec_r7i, "spec")
        self._fill_instance_specs(data, sga_r6i, sga_r7i, "sga")

        # 인스턴스 + 스토리지 + 네트워크 통합 비용
        self._fill_pricing(data, price_index, spec_r6i, spec_r7i, "spec")
        self._fill_pricing(data, price_index, sga_r6i, sga_r7i, "sga")

        # 비교 요약 + TCO
        self._fill_comparison(data)
        self._fill_tco(data, db_size, growth_rate, prov_iops, prov_tp)

        return data

    def _fill_storage_costs(self, data: dict, db_size: float, growth_rate: float,
                            prov_iops: int, prov_tp: float) -> None:
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
                costs = calc_storage_costs(size, prov_iops, prov_tp)

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

        # AWR 기반 네트워크 트래픽 (일별/월별)
        sent_daily = net["sent_daily_gb"]
        recv_daily = net["recv_daily_gb"]
        redo_daily = net["redo_daily_gb"]
        # dblink은 AWR에서 별도 추출이 어려우므로 0으로 처리
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

        # 시나리오별 월 네트워크 비용
        # Cross-AZ: 클라이언트 트래픽 × $0.01 × 2(양방향)
        cross_az_cost = client_monthly * NET_CROSS_AZ_PER_GB * 2
        data["net_cost_cross_az"] = f"{cross_az_cost:,.2f}"
        data["net_cost_cross_az_yearly"] = f"{cross_az_cost * 12:,.2f}"

        # Multi-AZ (Cross-AZ App): 클라이언트 트래픽만 (복제는 무료)
        data["net_cost_maz_cross_az"] = f"{cross_az_cost:,.2f}"
        data["net_cost_maz_cross_az_yearly"] = f"{cross_az_cost * 12:,.2f}"

        # + Read Replica (Cross-AZ): 위 + redo × $0.01
        redo_monthly = redo_daily * 30
        rr_cross_az_cost = cross_az_cost + redo_monthly * NET_CROSS_AZ_PER_GB
        data["net_cost_rr_cross_az"] = f"{rr_cross_az_cost:,.2f}"
        data["net_cost_rr_cross_az_yearly"] = f"{rr_cross_az_cost * 12:,.2f}"

        # + Read Replica (Cross-Region): 위 + redo × $0.02
        rr_cross_region_cost = cross_az_cost + redo_monthly * NET_CROSS_REGION_PER_GB
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
        net_keys = [
            "sqlnet_recv_daily", "sqlnet_sent_daily",
            "sqlnet_recv_monthly", "sqlnet_sent_monthly",
            "dblink_daily", "dblink_monthly",
            "redo_daily", "redo_monthly",
            "net_total_daily", "net_total_monthly",
            "net_cost_cross_az", "net_cost_cross_az_yearly",
            "net_cost_maz_cross_az", "net_cost_maz_cross_az_yearly",
            "net_cost_rr_cross_az", "net_cost_rr_cross_az_yearly",
            "net_cost_rr_cross_region", "net_cost_rr_cross_region_yearly",
            "net_monthly", "net_maz_monthly",
        ]
        for k in net_keys:
            data[k] = "0.00"
        data["net_scenario"] = "N/A"
        for yr in range(1, 4):
            data[f"net_total_monthly_{yr}y"] = "0.00"
            data[f"net_cost_cross_az_{yr}y"] = "0.00"
            data[f"net_cost_cross_az_yearly_{yr}y"] = "0.00"


    def _fill_instance_specs(self, data: dict, r6i_inst: Optional[str],
                              r7i_inst: Optional[str], prefix: str) -> None:
        """인스턴스 사양 정보를 data에 채웁니다."""
        for family, inst in [("r6i", r6i_inst), ("r7i", r7i_inst)]:
            key_prefix = f"{prefix}_{family}"
            data[f"{key_prefix}_instance"] = inst or "N/A"
            if inst and inst in INSTANCE_SPECS:
                specs = INSTANCE_SPECS[inst]
                data[f"{key_prefix}_vcpu"] = specs["vcpu"]
                data[f"{key_prefix}_memory"] = specs["memory_gb"]
                data[f"{key_prefix}_network"] = specs["network_gbps"]
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
                      r6i_inst: Optional[str], r7i_inst: Optional[str],
                      prefix: str) -> None:
        """인스턴스 + 스토리지 + 네트워크 통합 비용을 data에 채웁니다."""
        stor_monthly = float(data.get("stor_total_0y", "0").replace(",", ""))
        stor_maz_monthly = float(data.get("stor_maz_total_0y", "0").replace(",", ""))
        net_monthly = float(data.get("net_monthly", "0").replace(",", ""))
        net_maz_monthly = float(data.get("net_maz_monthly", "0").replace(",", ""))

        pricing_options = [
            ("od", PricingType.ON_DEMAND),
            ("ri1au", PricingType.RI_1YR_ALL_UPFRONT),
            ("ri3au", PricingType.RI_3YR_ALL_UPFRONT),
        ]

        for family, inst in [("r6i", r6i_inst), ("r7i", r7i_inst)]:
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

    def _fill_comparison(self, data: dict) -> None:
        """전체 비용 비교 요약 (섹션 7) 데이터를 채웁니다."""
        combos = [
            ("spec", "r6i"), ("spec", "r7i"),
            ("sga", "r6i"), ("sga", "r7i"),
        ]
        options = [
            ("od", "od"), ("ri1au", "ri1au"),
            ("ri3au", "ri3au"),
        ]
        for prefix, family in combos:
            for comp_key, opt_key in options:
                src = f"{prefix}_{family}_{opt_key}_total_yearly"
                dst = f"comp_{prefix}_{family}_{comp_key}"
                data[dst] = data.get(src, "N/A")

    def _fill_tco(self, data: dict, db_size: float, growth_rate: float,
                  prov_iops: int, prov_tp: float) -> None:
        """3년 TCO 비교 데이터를 채웁니다."""
        is_aurora = self._args.engine in AURORA_ENGINES

        # 연도별 스토리지 비용
        yearly_stor: list[float] = []
        for year in range(3):
            size = db_size * (1 + growth_rate) ** year if db_size else 0
            if is_aurora:
                costs = calc_aurora_storage_costs(size)
            else:
                costs = calc_storage_costs(size, prov_iops, prov_tp)
            yearly_stor.append(costs["total"] * 12)

        stor_3yr_total = sum(yearly_stor)

        # 연도별 네트워크 비용
        net_monthly_base = float(data.get("net_monthly", "0").replace(",", ""))
        yearly_net: list[float] = []
        for year in range(3):
            factor = (1 + growth_rate) ** year
            yearly_net.append(net_monthly_base * factor * 12)
        net_3yr_total = sum(yearly_net)

        combos = [
            ("spec", "r6i"), ("spec", "r7i"),
            ("sga", "r6i"), ("sga", "r7i"),
        ]

        for prefix, family in combos:
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
        for family in ["r6i", "r7i"]:
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
