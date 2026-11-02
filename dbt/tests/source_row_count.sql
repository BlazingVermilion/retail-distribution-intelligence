select 1 where (select count(*) from {{ ref('fact_sales') }}) = 0 or (select count(*) from {{ ref('fact_sales') }}) <> (select count(*) from {{ source('iowa','sales_exact') }})
