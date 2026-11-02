{{ config(materialized='table') }}

-- Preserve the reviewed SQL policy; changes require parity and regression tests.
WITH bounds AS (
    SELECT MIN(ordered_on) AS first_day, MAX(ordered_on) AS last_day
    FROM {{ ref('fact_sales') }}
), calendar AS (
    SELECT first_day + g.day_offset AS calendar_date
    FROM bounds
    CROSS JOIN LATERAL generate_series(0, last_day - first_day) AS g(day_offset)
)
SELECT calendar_date,
       EXTRACT(YEAR FROM calendar_date)::INTEGER AS calendar_year,
       EXTRACT(QUARTER FROM calendar_date)::INTEGER AS calendar_quarter,
       EXTRACT(MONTH FROM calendar_date)::INTEGER AS calendar_month,
       DATE_TRUNC('month', calendar_date)::DATE AS month_start,
       EXTRACT(ISODOW FROM calendar_date)::INTEGER AS iso_day_of_week,
       (EXTRACT(ISODOW FROM calendar_date) IN (6, 7)) AS is_weekend
FROM calendar
