# Oracle PL/SQL 복잡도 분석 결과

## 복잡도 점수 요약

- **오브젝트 타입**: PROCEDURE
- **타겟 데이터베이스**: POSTGRESQL
- **원점수 (Raw Score)**: 3.30
- **정규화 점수**: 1.65 / 10.0
- **복잡도 레벨**: 간단
- **권장사항**: 함수 대체

## 세부 점수

| 카테고리 | 점수 |
|---------|------|
| 기본 점수 | 2.50 |
| 코드 복잡도 | 0.70 |
| Oracle 특화 기능 | 0.00 |
| 비즈니스 로직 | 0.10 |
| 변환 난이도 | 0.00 |

## 분석 메타데이터

- **코드 라인 수**: 17
- **커서 개수**: 0
- **예외 블록 개수**: 1
- **중첩 깊이**: 1
- **BULK 연산 개수**: 0
- **동적 SQL 개수**: 0

## 원본 코드

```sql
-- 단순한 CRUD 프로시저 (MySQL 마이그레이션에 적합)
CREATE OR REPLACE PROCEDURE GET_CUSTOMER_INFO (
    p_customer_id IN NUMBER,
    p_name OUT VARCHAR2,
    p_email OUT VARCHAR2
)
IS
BEGIN
    SELECT name, email
    INTO p_name, p_email
    FROM customers
    WHERE customer_id = p_customer_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        p_name := NULL;
        p_email := NULL;
END GET_CUSTOMER_INFO;
/
```
