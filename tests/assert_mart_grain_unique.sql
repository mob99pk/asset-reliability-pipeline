-- Singular test: the mart must have exactly one row per month x asset_class x site.
-- Returns offending rows; any row = failure.
select month, asset_class, site, count(*) as n
from {{ ref('asset_reliability_monthly') }}
group by 1, 2, 3
having count(*) > 1
