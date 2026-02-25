"""
인스턴스 사양 및 스토리지 비용 유틸리티 모듈.

인스턴스 타입 파싱, 패밀리 확장, 사양 조회, 스토리지 비용 계산 등
순수 함수와 상수를 제공합니다.
"""

from __future__ import annotations

import re
from typing import Optional

from rds_cost_estimator.models import InstanceFamily

# 인스턴스 타입 파싱 패턴
_INSTANCE_PATTERN = re.compile(r"^db\.([a-z0-9]+)\.(.+)$")

# Oracle 엔진 및 Graviton 패밀리 상수
ORACLE_ENGINES = {"oracle-ee", "oracle-se2"}
GRAVITON_FAMILIES = {"r6g", "r7g", "r8g", "m6g", "m7g", "t4g"}
REFACTORING_ENGINE = "aurora-postgresql"

# Aurora 클러스터 스토리지 요금 (ap-northeast-2 기준, USD)
# Aurora Standard: I/O 요청당 과금, 스토리지 $0.10/GB-월
# Aurora I/O-Optimized: I/O 무료, 스토리지 $0.13/GB-월 (30% 할증)
# Aurora는 3AZ 6카피 복제가 기본 포함 → Multi-AZ 스토리지 추가 비용 없음
AURORA_STORAGE_PER_GB = 0.10  # Aurora Standard 기준
AURORA_IO_PER_MILLION = 0.20  # I/O 요청 100만 건당 (Aurora Standard)
AURORA_BACKUP_PER_GB = 0.021  # 백업 스토리지 (보관 기간 초과분)

# Aurora 엔진 목록 (클러스터 스토리지 사용)
AURORA_ENGINES = {"aurora-postgresql", "aurora-mysql"}

# gp3 스토리지 요금 (ap-northeast-2 기준, USD) — 기본값
GP3_STORAGE_PER_GB = 0.08
GP3_IOPS_PER_UNIT = 0.02  # 3000 초과분
GP3_THROUGHPUT_PER_MBPS = 0.04  # 125 MB/s 초과분
GP3_BASE_IOPS = 3000
GP3_BASE_THROUGHPUT = 125  # MB/s

# 네트워크 비용 상수 (기본값)
NET_CROSS_AZ_PER_GB = 0.01
NET_CROSS_REGION_PER_GB = 0.02

# 리전별 스토리지/네트워크 요금 딕셔너리 (MVP: 주요 리전만)
REGION_PRICING: dict[str, dict[str, float]] = {
    "ap-northeast-2": {
        "gp3_per_gb": 0.08, "iops_per_unit": 0.02, "throughput_per_mbps": 0.04,
        "cross_az_per_gb": 0.01, "cross_region_per_gb": 0.02,
    },
    "us-east-1": {
        "gp3_per_gb": 0.08, "iops_per_unit": 0.02, "throughput_per_mbps": 0.04,
        "cross_az_per_gb": 0.01, "cross_region_per_gb": 0.02,
    },
    "us-west-2": {
        "gp3_per_gb": 0.08, "iops_per_unit": 0.02, "throughput_per_mbps": 0.04,
        "cross_az_per_gb": 0.01, "cross_region_per_gb": 0.02,
    },
    "eu-west-1": {
        "gp3_per_gb": 0.088, "iops_per_unit": 0.022, "throughput_per_mbps": 0.044,
        "cross_az_per_gb": 0.01, "cross_region_per_gb": 0.02,
    },
    "ap-northeast-1": {
        "gp3_per_gb": 0.096, "iops_per_unit": 0.024, "throughput_per_mbps": 0.048,
        "cross_az_per_gb": 0.01, "cross_region_per_gb": 0.02,
    },
    "ap-southeast-1": {
        "gp3_per_gb": 0.088, "iops_per_unit": 0.022, "throughput_per_mbps": 0.044,
        "cross_az_per_gb": 0.01, "cross_region_per_gb": 0.02,
    },
}

# 기본 리전 (REGION_PRICING에 없는 리전일 때 폴백)
DEFAULT_REGION = "ap-northeast-2"


def get_region_pricing(region: str) -> dict[str, float]:
    """리전별 요금을 반환합니다. 미지원 리전은 기본값(ap-northeast-2)으로 폴백."""
    return REGION_PRICING.get(region, REGION_PRICING[DEFAULT_REGION])

# 인스턴스 사이즈별 사양 테이블 (r 계열 및 기타 메모리 최적화)
_SIZE_SPECS: dict[str, dict[str, float | int]] = {
    # r 계열은 large 이상만 AWS RDS에서 제공 (micro/small/medium 제거)
    "large": {"vcpu": 2, "memory_gb": 16, "network_gbps": 12.5},
    "xlarge": {"vcpu": 4, "memory_gb": 32, "network_gbps": 12.5},
    "2xlarge": {"vcpu": 8, "memory_gb": 64, "network_gbps": 12.5},
    "4xlarge": {"vcpu": 16, "memory_gb": 128, "network_gbps": 12.5},
    "8xlarge": {"vcpu": 32, "memory_gb": 256, "network_gbps": 12.5},
    "12xlarge": {"vcpu": 48, "memory_gb": 384, "network_gbps": 18.75},
    "16xlarge": {"vcpu": 64, "memory_gb": 512, "network_gbps": 25.0},
    "24xlarge": {"vcpu": 96, "memory_gb": 768, "network_gbps": 37.5},
}

# 범용(m) 계열은 메모리가 r 계열의 절반
_M_SIZE_SPECS: dict[str, dict[str, float | int]] = {
    "large": {"vcpu": 2, "memory_gb": 8, "network_gbps": 12.5},
    "xlarge": {"vcpu": 4, "memory_gb": 16, "network_gbps": 12.5},
    "2xlarge": {"vcpu": 8, "memory_gb": 32, "network_gbps": 12.5},
    "4xlarge": {"vcpu": 16, "memory_gb": 64, "network_gbps": 12.5},
    "8xlarge": {"vcpu": 32, "memory_gb": 128, "network_gbps": 12.5},
    "12xlarge": {"vcpu": 48, "memory_gb": 192, "network_gbps": 18.75},
    "16xlarge": {"vcpu": 64, "memory_gb": 256, "network_gbps": 25.0},
    "24xlarge": {"vcpu": 96, "memory_gb": 384, "network_gbps": 37.5},
}

# 버스터블(t) 계열 사양
_T_SIZE_SPECS: dict[str, dict[str, float | int]] = {
    "micro": {"vcpu": 2, "memory_gb": 1, "network_gbps": 0.5},
    "small": {"vcpu": 2, "memory_gb": 2, "network_gbps": 0.5},
    "medium": {"vcpu": 2, "memory_gb": 4, "network_gbps": 0.5},
    "large": {"vcpu": 2, "memory_gb": 8, "network_gbps": 0.5},
    "xlarge": {"vcpu": 4, "memory_gb": 16, "network_gbps": 0.5},
    "2xlarge": {"vcpu": 8, "memory_gb": 32, "network_gbps": 0.5},
}

# 패밀리 카테고리 판별
_R_FAMILIES = {"r6i", "r7i", "r6g", "r7g", "r8g", "x2idn"}
_M_FAMILIES = {"m6i", "m7i", "m6g", "m7g"}
_T_FAMILIES = {"t3", "t4g"}

# _fill_network_costs / _fill_network_defaults 에서 공유하는 키 목록
_NETWORK_STATIC_KEYS: list[str] = [
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

# 연도별 네트워크 키 패턴 (1y, 2y, 3y)
_NETWORK_YEARLY_KEY_PATTERNS: list[str] = [
    "net_total_monthly_{yr}y",
    "net_cost_cross_az_{yr}y",
    "net_cost_cross_az_yearly_{yr}y",
]


def get_all_network_keys() -> list[str]:
    """_fill_network_costs에서 설정하는 모든 네트워크 키 목록을 반환합니다."""
    keys = list(_NETWORK_STATIC_KEYS) + ["net_scenario"]
    for yr in range(1, 4):
        for pattern in _NETWORK_YEARLY_KEY_PATTERNS:
            keys.append(pattern.format(yr=yr))
    return keys


def get_instance_specs(instance_type: str) -> dict[str, float | int] | None:
    """인스턴스 타입에서 사양(vCPU, 메모리, 네트워크)을 반환합니다."""
    match = _INSTANCE_PATTERN.match(instance_type)
    if not match:
        return None
    family = match.group(1)
    size = match.group(2)

    if family in _T_FAMILIES:
        return _T_SIZE_SPECS.get(size)
    if family in _M_FAMILIES:
        return _M_SIZE_SPECS.get(size)
    return _SIZE_SPECS.get(size)


def extract_family_and_size(instance_type: str) -> tuple[str, str] | None:
    """인스턴스 타입에서 패밀리와 사이즈를 추출합니다."""
    match = _INSTANCE_PATTERN.match(instance_type)
    if not match:
        return None
    return match.group(1), match.group(2)


def expand_instance_families(
    instance_type: str,
    exclude_graviton: bool = False,
) -> list[str]:
    """하나의 인스턴스 유형에서 동일 카테고리의 패밀리 변형을 생성."""
    parsed = extract_family_and_size(instance_type)
    if not parsed:
        return [instance_type]

    family, size = parsed
    same_cat = InstanceFamily.same_category_families(family)

    variants: list[str] = []
    seen: set[str] = set()

    for fam in same_cat:
        if exclude_graviton and fam in GRAVITON_FAMILIES:
            continue
        variant = f"db.{fam}.{size}"
        if variant not in seen:
            seen.add(variant)
            variants.append(variant)

    return variants


def find_matching_instance(memory_gb: float, family: str = "r6i") -> Optional[str]:
    """메모리 기준으로 적합한 인스턴스 타입을 찾습니다."""
    if family in _T_FAMILIES:
        specs_table = _T_SIZE_SPECS
    elif family in _M_FAMILIES:
        specs_table = _M_SIZE_SPECS
    else:
        specs_table = _SIZE_SPECS

    candidates = [
        (f"db.{family}.{size}", specs)
        for size, specs in specs_table.items()
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
    region: str = DEFAULT_REGION,
) -> dict:
    """gp3 스토리지 월간 비용 계산. 리전별 요금을 적용합니다."""
    rp = get_region_pricing(region)
    storage_cost = db_size_gb * rp["gp3_per_gb"]
    extra_iops = max(0, provisioned_iops - GP3_BASE_IOPS) if provisioned_iops else 0
    iops_cost = extra_iops * rp["iops_per_unit"]
    extra_tp = max(0, provisioned_throughput_mbps - GP3_BASE_THROUGHPUT) if provisioned_throughput_mbps else 0
    throughput_cost = extra_tp * rp["throughput_per_mbps"]

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
