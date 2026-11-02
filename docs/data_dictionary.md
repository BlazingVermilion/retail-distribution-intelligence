# Data dictionary

Source JSON provides names and types only. Descriptions below are working interpretations; business rules must be verified.

| Source column | Source type | Target type | Interpretation |
|---|---|---|---|
| invoice_id | STRING | VARCHAR | Source identifier; business grain changes across observed periods. |
| ordered_on | DATE | DATE | Source transaction date. |
| store_no | STRING | VARCHAR | Source store code; preserve leading zeros. |
| store_name | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| store_address | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| store_city | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| store_zip_code | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| county_fips_code | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| county_name | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| category_code | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| category_name | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| vendor_number | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| vendor_name | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| item_no | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| im_desc | STRING | VARCHAR | Source attribute; preserve value and missingness. |
| pack | INTEGER | NUMBER(18,0) | Reported pack field; do not multiply into revenue without verified semantics. |
| bottle_volume_ml | FLOAT | NUMBER(18,6) | Reported container volume in milliliters. |
| state_bottle_cost | FLOAT | NUMBER(18,6) | Reported cost field; insufficient for net-profit claims. |
| state_bottle_retail | FLOAT | NUMBER(18,6) | Reported unit-price field; not necessarily realized consumer price. |
| sales_bottles | INTEGER | NUMBER(18,0) | Signed source quantity; packaging semantics require confirmation. |
| sales_dollars | FLOAT | NUMBER(18,6) | Signed reported transaction value in USD. |
| sales_liters | FLOAT | NUMBER(18,6) | Reported volume; precision varies by period. |
| sales_gallons | FLOAT | NUMBER(18,6) | Reported volume in gallons; verify conversion convention. |
