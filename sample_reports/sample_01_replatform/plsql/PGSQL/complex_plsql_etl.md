# Oracle PL/SQL 복잡도 분석 결과

## 복잡도 점수 요약

- **오브젝트 타입**: PACKAGE
- **타겟 데이터베이스**: POSTGRESQL
- **원점수 (Raw Score)**: 18.50
- **정규화 점수**: 9.25 / 10.0
- **복잡도 레벨**: 극도로 복잡
- **권장사항**: 완전 재설계

## 세부 점수

| 카테고리 | 점수 |
|---------|------|
| 기본 점수 | 4.00 |
| 코드 복잡도 | 3.50 |
| Oracle 특화 기능 | 5.00 |
| 비즈니스 로직 | 3.00 |
| 변환 난이도 | 3.00 |

## 분석 메타데이터

- **코드 라인 수**: 196
- **커서 개수**: 1
- **예외 블록 개수**: 6
- **중첩 깊이**: 5
- **BULK 연산 개수**: 2
- **동적 SQL 개수**: 9

## 감지된 Oracle 특화 기능

- REF CURSOR
- PRAGMA
- NESTED TABLE

## 감지된 외부 의존성

- UTL_FILE
- DBMS_SCHEDULER
- DBMS_LOB
- DBMS_OUTPUT
- DBMS_LOCK
- DBMS_STATS

## 변환 가이드

| Oracle 기능 | 대체 방법 |
|------------|----------|
| REF CURSOR | REFCURSOR 타입 (유사) |
| PRAGMA | 대부분 불필요 또는 함수 속성으로 대체 |
| NESTED TABLE | ARRAY 또는 별도 테이블 |
| UTL_FILE | COPY, pg_read_file(), pg_write_file() 또는 외부 스크립트 |
| DBMS_SCHEDULER | pg_cron 확장 |
| DBMS_LOB | bytea 타입 및 내장 함수 |
| DBMS_OUTPUT | RAISE NOTICE |

## 원본 코드

```sql
-- 복잡한 ETL 프로세스: 외부 파일 처리, 동적 SQL, 고급 예외 처리
-- Oracle 종속 패키지: UTL_FILE, DBMS_SQL, DBMS_LOB, DBMS_SCHEDULER, DBMS_LOCK
CREATE OR REPLACE PACKAGE PKG_COMPLEX_ETL_PROCESSOR AS
    -- 패키지 변수 (Package-level state)
    g_batch_id NUMBER;
    g_error_threshold CONSTANT NUMBER := 100;
    
    -- 커스텀 예외 정의
    e_file_not_found EXCEPTION;
    e_too_many_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_file_not_found, -29283);
    
    -- Public 프로시저
    PROCEDURE process_data_file(
        p_directory IN VARCHAR2,
        p_filename IN VARCHAR2,
        p_table_name IN VARCHAR2,
        p_batch_id OUT NUMBER
    );
    
    FUNCTION get_batch_status(p_batch_id IN NUMBER) RETURN VARCHAR2;
    
END PKG_COMPLEX_ETL_PROCESSOR;
/

CREATE OR REPLACE PACKAGE BODY PKG_COMPLEX_ETL_PROCESSOR AS
    
    -- Private 함수: 동적 테이블 생성
    PROCEDURE create_staging_table(p_table_name IN VARCHAR2) IS
        v_sql VARCHAR2(4000);
        v_table_exists NUMBER;
    BEGIN
        -- 테이블 존재 여부 확인
        SELECT COUNT(*) INTO v_table_exists
        FROM user_tables
        WHERE table_name = UPPER(p_table_name);
        
        IF v_table_exists = 0 THEN
            v_sql := 'CREATE TABLE ' || p_table_name || ' (
                row_id NUMBER GENERATED ALWAYS AS IDENTITY,
                data_col1 VARCHAR2(100),
                data_col2 NUMBER,
                data_col3 DATE,
                batch_id NUMBER,
                load_timestamp TIMESTAMP DEFAULT SYSTIMESTAMP,
                CONSTRAINT pk_' || p_table_name || ' PRIMARY KEY (row_id)
            )';
            EXECUTE IMMEDIATE v_sql;
            
            -- 파티션 추가 (동적 SQL)
            v_sql := 'ALTER TABLE ' || p_table_name || 
                     ' MODIFY PARTITION BY RANGE (load_timestamp) INTERVAL(NUMTOYMINTERVAL(1, ''MONTH''))';
            EXECUTE IMMEDIATE v_sql;
        END IF;
    END create_staging_table;
    
    -- Private 함수: 파일 읽기 및 파싱 (UTL_FILE 사용)
    PROCEDURE read_and_parse_file(
        p_directory IN VARCHAR2,
        p_filename IN VARCHAR2,
        p_table_name IN VARCHAR2,
        p_batch_id IN NUMBER
    ) IS
        v_file UTL_FILE.FILE_TYPE;
        v_line VARCHAR2(32767);
        v_clob CLOB;
        v_sql VARCHAR2(4000);
        v_error_count NUMBER := 0;
        v_success_count NUMBER := 0;
        
        -- BULK COLLECT용 타입
        TYPE t_data_array IS TABLE OF VARCHAR2(32767);
        v_data_batch t_data_array := t_data_array();
        
        -- 동적 커서
        TYPE t_cursor IS REF CURSOR;
        v_cursor t_cursor;
        
    BEGIN
        -- 파일 열기 (UTL_FILE)
        v_file := UTL_FILE.FOPEN(p_directory, p_filename, 'R', 32767);
        
        -- DBMS_LOB을 사용한 대용량 데이터 처리
        DBMS_LOB.CREATETEMPORARY(v_clob, TRUE);
        
        -- 파일 읽기 루프
        LOOP
            BEGIN
                UTL_FILE.GET_LINE(v_file, v_line);
                
                -- 데이터 검증 및 변환
                IF LENGTH(v_line) > 0 AND SUBSTR(v_line, 1, 1) != '#' THEN
                    v_data_batch.EXTEND;
                    v_data_batch(v_data_batch.COUNT) := v_line;
                    
                    -- 배치 크기가 1000에 도달하면 BULK INSERT
                    IF v_data_batch.COUNT >= 1000 THEN
                        FORALL i IN 1..v_data_batch.COUNT SAVE EXCEPTIONS
                            EXECUTE IMMEDIATE 
                                'INSERT INTO ' || p_table_name || 
                                ' (data_col1, data_col2, data_col3, batch_id) ' ||
                                'VALUES (SUBSTR(:1, 1, 100), TO_NUMBER(SUBSTR(:1, 101, 10)), ' ||
                                'TO_DATE(SUBSTR(:1, 111, 8), ''YYYYMMDD''), :2)'
                            USING v_data_batch(i), p_batch_id;
                        
                        v_success_count := v_success_count + v_data_batch.COUNT;
                        v_data_batch.DELETE;
                        COMMIT;
                    END IF;
                END IF;
                
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    EXIT; -- 파일 끝
                WHEN OTHERS THEN
                    v_error_count := v_error_count + 1;
                    -- 에러 로깅 (UTL_FILE로 에러 파일 작성)
                    DBMS_OUTPUT.PUT_LINE('Error parsing line: ' || SQLERRM);
                    
                    IF v_error_count > g_error_threshold THEN
                        RAISE e_too_many_errors;
                    END IF;
            END;
        END LOOP;
        
        -- 남은 데이터 처리
        IF v_data_batch.COUNT > 0 THEN
            FORALL i IN 1..v_data_batch.COUNT SAVE EXCEPTIONS
                EXECUTE IMMEDIATE 
                    'INSERT INTO ' || p_table_name || 
                    ' (data_col1, data_col2, data_col3, batch_id) ' ||
                    'VALUES (SUBSTR(:1, 1, 100), TO_NUMBER(SUBSTR(:1, 101, 10)), ' ||
                    'TO_DATE(SUBSTR(:1, 111, 8), ''YYYYMMDD''), :2)'
                USING v_data_batch(i), p_batch_id;
            COMMIT;
        END IF;
        
        UTL_FILE.FCLOSE(v_file);
        DBMS_LOB.FREETEMPORARY(v_clob);
        
        -- 통계 정보 수집 (동적 SQL)
        EXECUTE IMMEDIATE 'BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, ''' || 
                         p_table_name || '''); END;';
        
    EXCEPTION
        WHEN e_file_not_found THEN
            IF UTL_FILE.IS_OPEN(v_file) THEN
                UTL_FILE.FCLOSE(v_file);
            END IF;
            RAISE_APPLICATION_ERROR(-20001, 'File not found: ' || p_filename);
            
        WHEN e_too_many_errors THEN
            IF UTL_FILE.IS_OPEN(v_file) THEN
                UTL_FILE.FCLOSE(v_file);
            END IF;
            RAISE_APPLICATION_ERROR(-20002, 'Too many errors: ' || v_error_count);
            
        WHEN OTHERS THEN
            IF UTL_FILE.IS_OPEN(v_file) THEN
                UTL_FILE.FCLOSE(v_file);
            END IF;
            RAISE;
    END read_and_parse_file;
    
    -- Public 프로시저: 메인 처리 로직
    PROCEDURE process_data_file(
        p_directory IN VARCHAR2,
        p_filename IN VARCHAR2,
        p_table_name IN VARCHAR2,
        p_batch_id OUT NUMBER
    ) IS
        v_lock_handle VARCHAR2(128);
        v_lock_result NUMBER;
        v_job_name VARCHAR2(100);
    BEGIN
        -- 배치 ID 생성
        SELECT batch_seq.NEXTVAL INTO p_batch_id FROM dual;
        g_batch_id := p_batch_id;
        
        -- 분산 락 획득 (DBMS_LOCK)
        DBMS_LOCK.ALLOCATE_UNIQUE('ETL_PROCESS_' || p_table_name, v_lock_handle);
        v_lock_result := DBMS_LOCK.REQUEST(v_lock_handle, DBMS_LOCK.X_MODE, 10);
        
        IF v_lock_result != 0 THEN
            RAISE_APPLICATION_ERROR(-20003, 'Cannot acquire lock. Another process is running.');
        END IF;
        
        -- 스테이징 테이블 생성
        create_staging_table(p_table_name);
        
        -- 파일 처리
        read_and_parse_file(p_directory, p_filename, p_table_name, p_batch_id);
        
        -- 데이터 품질 검증 (복잡한 비즈니스 로직)
        DECLARE
            v_invalid_count NUMBER;
        BEGIN
            EXECUTE IMMEDIATE 
                'SELECT COUNT(*) FROM ' || p_table_name || 
                ' WHERE batch_id = :1 AND (data_col2 < 0 OR data_col3 > SYSDATE)'
            INTO v_invalid_count
            USING p_batch_id;
            
            IF v_invalid_count > 0 THEN
                -- 무효 데이터를 별도 테이블로 이동
                EXECUTE IMMEDIATE 
                    'INSERT INTO error_data_archive ' ||
                    'SELECT * FROM ' || p_table_name || 
                    ' WHERE batch_id = :1 AND (data_col2 < 0 OR data_col3 > SYSDATE)'
                USING p_batch_id;
                
                EXECUTE IMMEDIATE 
                    'DELETE FROM ' || p_table_name || 
                    ' WHERE batch_id = :1 AND (data_col2 < 0 OR data_col3 > SYSDATE)'
                USING p_batch_id;
                
                COMMIT;
            END IF;
        END;
        
        -- 후속 작업 스케줄링 (DBMS_SCHEDULER)
        v_job_name := 'POST_ETL_JOB_' || p_batch_id;
        DBMS_SCHEDULER.CREATE_JOB(
            job_name => v_job_name,
            job_type => 'PLSQL_BLOCK',
            job_action => 'BEGIN PKG_COMPLEX_ETL_PROCESSOR.post_process_data(' || 
                         p_batch_id || '); END;',
            start_date => SYSTIMESTAMP + INTERVAL '5' MINUTE,
            enabled => TRUE,
            auto_drop => TRUE
        );
        
        -- 락 해제
        v_lock_result := DBMS_LOCK.RELEASE(v_lock_handle);
        
    EXCEPTION
        WHEN OTHERS THEN
            -- 락 해제 시도
            BEGIN
                v_lock_result := DBMS_LOCK.RELEASE(v_lock_handle);
            EXCEPTION
                WHEN OTHERS THEN NULL;
            END;
            RAISE;
    END process_data_file;
    
    -- Public 함수: 배치 상태 조회
    FUNCTION get_batch_status(p_batch_id IN NUMBER) RETURN VARCHAR2 IS
        v_status VARCHAR2(50);
        v_count NUMBER;
    BEGIN
        -- 동적 쿼리로 여러 테이블 조회
        FOR rec IN (SELECT table_name FROM user_tables WHERE table_name LIKE 'STAGING_%') LOOP
            EXECUTE IMMEDIATE 
                'SELECT COUNT(*) FROM ' || rec.table_name || ' WHERE batch_id = :1'
            INTO v_count
            USING p_batch_id;
            
            IF v_count > 0 THEN
                RETURN 'PROCESSING - ' || v_count || ' records in ' || rec.table_name;
            END IF;
        END LOOP;
        
        RETURN 'COMPLETED';
    END get_batch_status;
    
END PKG_COMPLEX_ETL_PROCESSOR;
/
```
