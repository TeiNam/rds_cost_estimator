"""
공통 pytest 픽스처 모음
moto를 활용한 AWS API 모킹 및 boto3 세션 픽스처를 제공합니다.
"""

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """가짜 AWS 자격증명을 환경변수로 설정합니다. (moto 사용 시 필수)"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def boto3_session(aws_credentials: None) -> boto3.Session:
    """테스트용 boto3 세션을 반환합니다. (us-east-1 리전 고정)"""
    return boto3.Session(region_name="us-east-1")


@pytest.fixture
def mock_aws_env(aws_credentials: None):
    """moto mock_aws 컨텍스트를 활성화한 상태로 테스트를 실행합니다."""
    with mock_aws():
        yield


@pytest.fixture
def pricing_boto3_session(aws_credentials: None) -> boto3.Session:
    """AWS Pricing API 테스트용 boto3 세션을 반환합니다.
    Pricing API는 us-east-1 엔드포인트만 지원합니다.
    """
    return boto3.Session(region_name="us-east-1")
