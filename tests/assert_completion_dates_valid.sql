-- W6: completed work orders should have a completed_date on or after raised_date.
-- Known source-system issue, so warn rather than block the build.
{{ config(severity='warn') }}

select wo_id, status, raised_date, completed_date, dq_issue
from {{ ref('stg_work_orders') }}
where dq_issue in ('completed_without_date', 'completed_before_raised')
