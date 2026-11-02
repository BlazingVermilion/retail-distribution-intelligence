select 1 where {{ target.schema }}.try_iowa_numeric('12.345') IS DISTINCT FROM 12.345::NUMERIC
       OR {{ target.schema }}.try_iowa_numeric('NaN') IS NOT NULL
       OR {{ target.schema }}.try_iowa_numeric('Infinity') IS NOT NULL
       OR {{ target.schema }}.try_iowa_numeric('bad') IS NOT NULL
       OR {{ target.schema }}.try_iowa_numeric('') IS NOT NULL
       OR {{ target.schema }}.try_iowa_bigint('2.5') IS NOT NULL
       OR {{ target.schema }}.try_iowa_bigint('9223372036854775808') IS NOT NULL
       OR {{ target.schema }}.try_iowa_bigint('-9223372036854775809') IS NOT NULL
       OR {{ target.schema }}.try_iowa_bigint('9223372036854775807') IS DISTINCT FROM 9223372036854775807::BIGINT
       OR {{ target.schema }}.try_iowa_bigint('-9223372036854775808') IS DISTINCT FROM '-9223372036854775808'::BIGINT
       OR {{ target.schema }}.try_iowa_bigint(NULL) IS NOT NULL
       OR {{ target.schema }}.try_iowa_bigint('-2') IS DISTINCT FROM (-2)::BIGINT
       OR {{ target.schema }}.try_iowa_date('2025-02-30') IS NOT NULL
       OR {{ target.schema }}.try_iowa_date('2024-02-29') IS DISTINCT FROM DATE '2024-02-29'
