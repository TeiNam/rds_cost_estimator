"""
DuckDB 기반 데이터 저장소 모듈.

Bedrock에서 파싱한 데이터를 DuckDB 인메모리 DB에 저장하고,
리포트 생성에 필요한 데이터를 쿼리하여 반환합니다.
"""

from __future__ import annotations

import logging
from typing import Optional

import duckdb

from rds_cost_estimator.models import CostRecord, ParsedDocumentInfo, PricingType

logger = logging.getLogger(__name__)


class DuckDBStore:
    """DuckDB 인메모리 데이터 저장소.

    Bedrock 파싱 결과와 Pricing API 조회 결과를 DuckDB에 저장하고,
    리포트 생성에 필요한 집계 쿼리를 제공합니다.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """DuckDB 연결 초기화 및 테이블 생성.

        Args:
            db_path: DB 파일 경로. 기본값 ":memory:" (인메모리)
        """
        self._conn = duckdb.connect(db_path)
        self._create_tables()
        logger.info("DuckDB 저장소 초기화 완료: %s", db_path)

    def __enter__(self) -> "DuckDBStore":
        """컨텍스트 매니저 진입. 인스턴스 자체를 반환합니다."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """컨텍스트 매니저 종료. 연결을 안전하게 닫고 예외는 전파하지 않습니다."""
        self.close()


    def _create_tables(self) -> None:
        """분석에 필요한 테이블들을 생성합니다."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS server_specs (
                db_name VARCHAR,
                oracle_version VARCHAR,
                cpu_cores INTEGER,
                physical_memory_gb DOUBLE,
                db_size_gb DOUBLE,
                instance_config VARCHAR
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS awr_metrics (
                avg_cpu_percent DOUBLE,
                peak_cpu_percent DOUBLE,
                avg_iops DOUBLE,
                peak_iops DOUBLE,
                avg_memory_gb DOUBLE,
                peak_memory_gb DOUBLE,
                sqlnet_bytes_sent_per_day DOUBLE,
                sqlnet_bytes_received_per_day DOUBLE,
                redo_bytes_per_day DOUBLE
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sga_analysis (
                current_sga_gb DOUBLE,
                recommended_sga_gb DOUBLE,
                sga_increase_rate_percent DOUBLE
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS storage_growth (
                current_db_size_gb DOUBLE,
                yearly_growth_gb DOUBLE,
                yearly_growth_rate_percent DOUBLE
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pricing_records (
                instance_type VARCHAR,
                region VARCHAR,
                engine VARCHAR,
                deployment_option VARCHAR,
                pricing_type VARCHAR,
                hourly_rate DOUBLE,
                upfront_fee DOUBLE,
                monthly_fee DOUBLE,
                annual_cost DOUBLE,
                monthly_cost DOUBLE,
                is_available BOOLEAN
            )
        """)

    def store_parsed_info(self, info: ParsedDocumentInfo) -> None:
        """ParsedDocumentInfo를 DuckDB 테이블에 저장합니다."""
        # 서버 사양
        self._conn.execute(
            "INSERT INTO server_specs VALUES (?, ?, ?, ?, ?, ?)",
            [
                info.db_name,
                info.oracle_version,
                info.cpu_cores,
                info.physical_memory_gb,
                info.db_size_gb,
                info.instance_config,
            ],
        )

        # AWR 메트릭
        awr = info.awr_metrics
        self._conn.execute(
            "INSERT INTO awr_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                awr.avg_cpu_percent,
                awr.peak_cpu_percent,
                awr.avg_iops,
                awr.peak_iops,
                awr.avg_memory_gb,
                awr.peak_memory_gb,
                awr.sqlnet_bytes_sent_per_day,
                awr.sqlnet_bytes_received_per_day,
                awr.redo_bytes_per_day,
            ],
        )

        # SGA 분석
        sga = info.sga_analysis
        self._conn.execute(
            "INSERT INTO sga_analysis VALUES (?, ?, ?)",
            [sga.current_sga_gb, sga.recommended_sga_gb, sga.sga_increase_rate_percent],
        )

        # 스토리지 증가 추이
        sg = info.storage_growth
        self._conn.execute(
            "INSERT INTO storage_growth VALUES (?, ?, ?)",
            [sg.current_db_size_gb, sg.yearly_growth_gb, sg.yearly_growth_rate_percent],
        )

        logger.info("ParsedDocumentInfo 저장 완료: db_name=%s", info.db_name)

    def store_pricing_records(self, records: list[CostRecord]) -> None:
        """CostRecord 목록을 DuckDB에 저장합니다."""
        for rec in records:
            self._conn.execute(
                "INSERT INTO pricing_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    rec.spec.instance_type,
                    rec.spec.region,
                    rec.spec.engine,
                    rec.spec.deployment_option,
                    rec.pricing_type.value,
                    rec.hourly_rate,
                    rec.upfront_fee,
                    rec.monthly_fee,
                    rec.annual_cost,
                    rec.monthly_cost,
                    rec.is_available,
                ],
            )
        logger.info("CostRecord %d건 저장 완료", len(records))

    def get_server_specs(self) -> Optional[dict]:
        """서버 사양 조회."""
        result = self._conn.execute(
            "SELECT * FROM server_specs LIMIT 1"
        ).fetchone()
        if not result:
            return None
        cols = ["db_name", "oracle_version", "cpu_cores",
                "physical_memory_gb", "db_size_gb", "instance_config"]
        return dict(zip(cols, result))

    def get_awr_metrics(self) -> Optional[dict]:
        """AWR 메트릭 조회."""
        result = self._conn.execute(
            "SELECT * FROM awr_metrics LIMIT 1"
        ).fetchone()
        if not result:
            return None
        cols = [
            "avg_cpu_percent", "peak_cpu_percent",
            "avg_iops", "peak_iops",
            "avg_memory_gb", "peak_memory_gb",
            "sqlnet_bytes_sent_per_day", "sqlnet_bytes_received_per_day",
            "redo_bytes_per_day",
        ]
        return dict(zip(cols, result))

    def get_sga_analysis(self) -> Optional[dict]:
        """SGA 분석 결과 조회."""
        result = self._conn.execute(
            "SELECT * FROM sga_analysis LIMIT 1"
        ).fetchone()
        if not result:
            return None
        cols = ["current_sga_gb", "recommended_sga_gb", "sga_increase_rate_percent"]
        return dict(zip(cols, result))

    def get_storage_growth(self) -> Optional[dict]:
        """스토리지 증가 추이 조회."""
        result = self._conn.execute(
            "SELECT * FROM storage_growth LIMIT 1"
        ).fetchone()
        if not result:
            return None
        cols = ["current_db_size_gb", "yearly_growth_gb", "yearly_growth_rate_percent"]
        return dict(zip(cols, result))

    def get_pricing(
        self,
        instance_type: str,
        deployment: str,
        pricing_type: str,
    ) -> Optional[dict]:
        """특정 인스턴스/배포/요금제의 가격 정보 조회."""
        result = self._conn.execute(
            """
            SELECT monthly_cost, annual_cost, is_available,
                   hourly_rate, upfront_fee, monthly_fee
            FROM pricing_records
            WHERE instance_type = ?
              AND deployment_option = ?
              AND pricing_type = ?
            LIMIT 1
            """,
            [instance_type, deployment, pricing_type],
        ).fetchone()
        if not result:
            return None
        cols = ["monthly_cost", "annual_cost", "is_available",
                "hourly_rate", "upfront_fee", "monthly_fee"]
        return dict(zip(cols, result))

    def get_network_traffic_summary(self) -> dict:
        """AWR 기반 네트워크 트래픽 요약 (GB 단위)."""
        result = self._conn.execute("""
            SELECT
                COALESCE(sqlnet_bytes_sent_per_day, 0) / (1024.0*1024*1024) AS sent_daily_gb,
                COALESCE(sqlnet_bytes_received_per_day, 0) / (1024.0*1024*1024) AS recv_daily_gb,
                COALESCE(redo_bytes_per_day, 0) / (1024.0*1024*1024) AS redo_daily_gb,
                -- 월간 (×30)
                COALESCE(sqlnet_bytes_sent_per_day, 0) * 30 / (1024.0*1024*1024) AS sent_monthly_gb,
                COALESCE(sqlnet_bytes_received_per_day, 0) * 30 / (1024.0*1024*1024) AS recv_monthly_gb,
                COALESCE(redo_bytes_per_day, 0) * 30 / (1024.0*1024*1024) AS redo_monthly_gb
            FROM awr_metrics
            LIMIT 1
        """).fetchone()

        if not result:
            return {
                "sent_daily_gb": 0, "recv_daily_gb": 0, "redo_daily_gb": 0,
                "sent_monthly_gb": 0, "recv_monthly_gb": 0, "redo_monthly_gb": 0,
                "total_daily_gb": 0, "total_monthly_gb": 0,
            }

        cols = [
            "sent_daily_gb", "recv_daily_gb", "redo_daily_gb",
            "sent_monthly_gb", "recv_monthly_gb", "redo_monthly_gb",
        ]
        data = dict(zip(cols, result))
        data["total_daily_gb"] = (
            data["sent_daily_gb"] + data["recv_daily_gb"]
            + data["redo_daily_gb"]
        )
        data["total_monthly_gb"] = (
            data["sent_monthly_gb"] + data["recv_monthly_gb"]
            + data["redo_monthly_gb"]
        )
        return data

    def get_unavailable_ri_records(self) -> list[dict]:
        """is_available=False인 RI 레코드 목록 조회 (Bedrock 폴백 대상)."""
        results = self._conn.execute("""
            SELECT instance_type, region, engine, deployment_option, pricing_type
            FROM pricing_records
            WHERE is_available = FALSE
              AND pricing_type != 'on_demand'
        """).fetchall()
        cols = ["instance_type", "region", "engine", "deployment_option", "pricing_type"]
        return [dict(zip(cols, row)) for row in results]

    def update_pricing_record(
        self,
        instance_type: str,
        deployment: str,
        pricing_type_val: str,
        monthly_cost: float,
        annual_cost: float,
    ) -> None:
        """가격 레코드를 업데이트합니다 (Bedrock 폴백 결과 반영)."""
        self._conn.execute(
            """
            UPDATE pricing_records
            SET monthly_cost = ?, annual_cost = ?, is_available = TRUE
            WHERE instance_type = ?
              AND deployment_option = ?
              AND pricing_type = ?
            """,
            [monthly_cost, annual_cost, instance_type, deployment, pricing_type_val],
        )

    def close(self) -> None:
        """DB 연결 종료."""
        self._conn.close()
        logger.info("DuckDB 연결 종료")
