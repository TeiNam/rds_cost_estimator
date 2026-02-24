"""
CLI 인수 파싱 모듈.

argparse를 사용하여 커맨드라인 인수를 파싱하고
CLIArgs Pydantic 모델로 변환하여 반환합니다.
"""

from __future__ import annotations

import argparse

from rds_cost_estimator.models import CLIArgs


def parse_args(argv: list[str] | None = None) -> CLIArgs:
    """CLI 인수를 파싱하여 CLIArgs 모델로 반환합니다.

    Args:
        argv: 파싱할 인수 목록. None이면 sys.argv를 사용합니다.

    Returns:
        파싱된 인수를 담은 CLIArgs 모델 인스턴스.
    """
    parser = argparse.ArgumentParser(
        prog="rds-cost-estimator",
        description="AWS RDS 이관 비용 예측 도구 - 리포트 파일을 입력받아 비용 분석 MD 리포트를 생성합니다.",
    )

    # 리포트 파일 경로 (필수)
    parser.add_argument(
        "input_file",
        type=str,
        help="인스턴스 사양 정보가 담긴 리포트 파일 경로 (PDF/DOCX/TXT/MD)",
    )

    # AWS 리전 (기본값: 서울 리전)
    parser.add_argument(
        "--region",
        type=str,
        default="ap-northeast-2",
        help="AWS 리전 코드 (기본값: ap-northeast-2)",
    )

    # RDS 엔진 (기본값: Oracle Enterprise Edition)
    parser.add_argument(
        "--engine",
        type=str,
        default="oracle-ee",
        help="RDS 엔진 유형 (기본값: oracle-ee)",
    )

    # 온프레미스 연간 유지비용 (선택 - 문서에서 추출 가능)
    parser.add_argument(
        "--on-prem-cost",
        type=float,
        default=None,
        dest="on_prem_cost",
        help="온프레미스 연간 유지비용 (USD). 미지정 시 문서에서 추출 시도",
    )

    # 현재 인스턴스 유형 (선택 - 문서에서 추출 가능)
    parser.add_argument(
        "--current-instance",
        type=str,
        default=None,
        dest="current_instance",
        help="현재 사용 중인 RDS 인스턴스 유형 (예: db.r6i.xlarge)",
    )

    # 사이즈 기준 권장 인스턴스 (선택 - 문서에서 추출 가능)
    parser.add_argument(
        "--recommended-instance-by-size",
        type=str,
        default=None,
        dest="recommended_instance_by_size",
        help="현재 사이즈 기준 권장 RDS 인스턴스 유형",
    )

    # SGA 기준 권장 인스턴스 (선택 - 문서에서 추출 가능)
    parser.add_argument(
        "--recommended-instance-by-sga",
        type=str,
        default=None,
        dest="recommended_instance_by_sga",
        help="SGA 기준 권장 RDS 인스턴스 유형",
    )

    # 출력 디렉토리
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=".",
        dest="output_dir",
        help="결과 파일 출력 디렉토리 (기본값: 현재 디렉토리)",
    )

    # JSON 출력도 함께 생성
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="output_json",
        help="MD 리포트와 함께 JSON 파일도 생성",
    )

    # AWS CLI 프로파일
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="사용할 AWS CLI 프로파일 이름",
    )

    # Bedrock 모델 ID
    parser.add_argument(
        "--bedrock-model",
        type=str,
        default="anthropic.claude-sonnet-4-6",
        dest="bedrock_model",
        help="AWS Bedrock 모델 ID (기본값: anthropic.claude-sonnet-4-6)",
    )

    # 상세 로그 활성화 플래그
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="DEBUG 레벨 로그를 활성화합니다",
    )

    namespace = parser.parse_args(argv)

    return CLIArgs(
        region=namespace.region,
        current_instance=namespace.current_instance,
        recommended_instance_by_size=namespace.recommended_instance_by_size,
        recommended_instance_by_sga=namespace.recommended_instance_by_sga,
        on_prem_cost=namespace.on_prem_cost,
        engine=namespace.engine,
        profile=namespace.profile,
        verbose=namespace.verbose,
        output_format="json" if namespace.output_json else None,
        output_dir=namespace.output_dir,
        input_file=namespace.input_file,
        bedrock_model=namespace.bedrock_model,
    )
