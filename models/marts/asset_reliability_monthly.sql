-- Grain: one row per month x asset_class x site.
-- Each metric is attributed to the month its own event happened:
--   raised / missing_due_date -> month raised
--   completed                 -> month completed
--   due / on_time / overdue   -> month due, once the deadline has passed (as_of)
-- Override the as-of date for reproducible reruns:
--   dbt build --vars "{as_of_date: '2026-09-30'}"
{%- set as_of = "'" ~ var('as_of_date') ~ "'::date" if var('as_of_date', none) else 'current_date()' %}

with work_orders as (

    select
        wo.*,
        coalesce(a.asset_class, 'Unknown') as asset_class,   -- W7: orphans stay visible
        coalesce(a.site, 'Unknown')        as site
    from {{ ref('stg_work_orders') }} as wo
    left join {{ ref('stg_assets') }} as a
        on wo.asset_id = a.asset_id
    where wo.raised_date is not null

),

events as (

    select
        date_trunc('month', raised_date)                            as month,
        asset_class,
        site,
        1                                                           as raised,
        0                                                           as completed,
        0                                                           as due,
        0                                                           as on_time,
        0                                                           as overdue,
        iff(due_date is null and status != 'Cancelled', 1, 0)       as missing_due_date
    from work_orders

    union all

    select date_trunc('month', completed_date), asset_class, site, 0, 1, 0, 0, 0, 0
    from work_orders
    where status = 'Completed' and completed_date is not null

    union all

    select
        date_trunc('month', due_date),
        asset_class,
        site,
        0,
        0,
        1,
        iff(status = 'Completed' and completed_date <= due_date, 1, 0),
        iff(completed_date > due_date or status in ('Open', 'In Progress'), 1, 0),
        0
    from work_orders
    where status != 'Cancelled'
      and due_date < {{ as_of }}

)

select
    month::date                                                     as month,
    asset_class,
    site,
    sum(raised)                                                     as raised,
    sum(completed)                                                  as completed,
    sum(due)                                                        as due,
    sum(on_time)                                                    as completed_on_time,
    sum(overdue)                                                    as overdue,
    sum(missing_due_date)                                           as missing_due_date,
    round(100 * sum(on_time) / nullif(sum(due), 0), 1)              as compliance_pct
from events
group by 1, 2, 3
