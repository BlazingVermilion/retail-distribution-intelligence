select month_start from {{ ref('sales_monthly') }}
where source_records <= 0
or not (money_mismatch_records between 0 and money_evaluable_records)
or not (money_evaluable_records between 0 and source_records)
or not (volume_mismatch_records between 0 and volume_evaluable_records)
or not (volume_evaluable_records between 0 and source_records)
