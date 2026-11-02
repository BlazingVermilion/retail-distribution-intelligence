-- FULL JOIN also detects a missing month, an empty mart, or an unexpected extra month.
{% set fields = ['rows_n','unique_ids','stores','bottles_n','dollars_n','liters_n','bottles_sum','dollars_sum','liters_sum'] %}
with expected as (
    select date '2026-09-01' as month_start
    {% for field in fields %}, {{ var('pilot_reference')[field] }} as {{ field }}{% endfor %}
)
select coalesce(m.month_start, e.month_start) as failing_month
from {{ ref('sales_monthly_pilot') }} m
full join expected e on e.month_start = m.month_start
where m.month_start is null or e.month_start is null
{% for field in fields %}or not equal_null(m.{{ field }}, e.{{ field }})
{% endfor %}
