"""
CLI 인수 파싱 모듈.

argparse를 사용하여 커맨드라인 인수를 파싱하고
CLIArgs Pydantic 모델로 변환하여 반환합니다.
"""

from __future__ import annotations

import argparse
from typing import Optional

from rds_cost_estimator.models import CLIArgs


def parse_args(argv: list[str] | None = None) -> CLIArgs:
    """CLI 인수를 파싱하여 CLIArgs 모델로 반환합니다.

    Args:
        argv: 파싱할 인수 목록. None이면 sys.argv를 사용합니다.

    Returns:
        파싱된 인수를 담은 CLIArgs 모델 인스턴스.

    Raises:
        SystemExit(1): 필수 인수가 누락된 경우 사용법 안내 후 종료.
    """
    parser = argparse.ArgumentParser(
        prog="rds-cost-estimator",
        description="AWS RDS 이관 비용 예측 도구 - 온프레미스에서 RDS로 이관 시 예상 비용을 분석합니다.",
    )

    # AWS 리전 (기본값: 서울 리전)
    parser.add_argument(
        "--region",
        type=str,
        default="ap-northeast-2",
        help="AWS 리전 코드 (기본값: ap-northeast-2)",
    )

    # 현재 인스턴스 유형
    parser.add_argument(
        "--current-instance",
        type=str,
        default=None,
        dest="current_instance",
        help="현재 사용 중인 RDS 인스턴스 유형 (예: db.r6i.xlarge)",
    )

    # 권장 인스턴스 유형
    parser.add_argument(
        "--recommended-instance",
        type=str,
        default=None,
        dest="recommended_instance",
        help="권장 RDS 인스턴스 유형 (예: db.r7i.xlarge)",
    )

    # 온프레미스 연간 유지비용
    parser.add_argument(
        "--on-prem-cost",
        type=float,
        default=None,
        dest="on_prem_cost",
        help="온프레미스 연간 유지비용 (USD)",
    )

    # RDS 엔진 (기본값: Oracle Enterprise Edition)
    parser.add_argument(
        "--engine",
        type=str,
        default="oracle-ee",
        help="RDS 엔진 유형 (기본값: oracle-ee)",
    )

    # AWS CLI 프로파일
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="사용할 AWS CLI 프로파일 이름",
    )

    # 상세 로그 활성화 플래그
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="DEBUG 레벨 로그를 활성화합니다",
    )

    # 출력 형식 (json 지원)
    parser.add_argument(
        "--output-format",
        type=str,
        default=None,
        dest="output_format",
        choices=["json"],
        help="출력 형식 (현재 지원: json)",
    )

    # JSON 출력 파일 경로
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        dest="output_file",
        help="JSON 결과를 저장할 파일 경로",
    )

    # 문서 파일 경로 (PDF/DOCX/TXT)
    parser.add_argument(
        "--input-file",
        type=str,
        default=None,
        dest="input_file",
        help="인스턴스 사양 정보가 담긴 문서 파일 경로 (PDF/DOCX/TXT)",
    )

    # Bedrock 모델 ID
    parser.add_argument(
        "--bedrock-model",
        type=str,
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        dest="bedrock_model",
        help="AWS Bedrock 모델 ID (기본값: anthropic.claude-3-5-sonnet-20241022-v2:0)",
    )

    # 인수 파싱 실행
    namespace = parser.parse_args(argv)

    # --input-file이 없을 때 필수 인수 검증
    if namespace.input_file is None:
        missing: list[str] = []

        if namespace.current_instance is None:
            missing.append("--current-instance")
        if namespace.recommended_instance is None:
            missing.append("--recommended-instance")
        if namespace.on_prem_cost is None:
            missing.append("--on-prem-cost")

        if missing:
            # 누락된 필수 인수 목록을 포함한 오류 메시지 출력 후 종료 코드 1로 종료
            parser.error(
                f"--input-file이 지정되지 않은 경우 다음 인수가 필수입니다: "
                f"{', '.join(missing)}"
            )

    # CLIArgs Pydantic 모델로 변환하여 반환
    return CLIArgs(
        region=namespace.region,
        current_instance=namespace.current_instance,
        recommended_instance=namespace.recommended_instance,
        on_prem_cost=namespace.on_prem_cost,
        engine=namespace.engine,
        profile=namespace.profile,
        verbose=namespace.verbose,
        output_format=namespace.output_format,
        output_file=namespace.output_file,
        input_file=namespace.input_file,
        bedrock_model=namespace.bedrock_model,
    )
