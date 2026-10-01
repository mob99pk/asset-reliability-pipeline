with source as (

    select * from {{ source('raw', 'work_orders') }}

),

deduped as (

    -- W1: late delta exports re-send a wo_id; the last row in the file wins
    select *
    from source
    qualify row_number() over (partition by wo_id order by _row_number desc) = 1

),

cleaned as (

    select
        trim(wo_id)                                         as wo_id,
        upper(trim(asset_id))                               as asset_id,

        -- W2: map source-system codes; unknown values pass through so tests catch them
        case upper(trim(type))
            when 'PREVENTIVE' then 'Preventive'
            when 'PM'         then 'Preventive'
            when 'CORRECTIVE' then 'Corrective'
            when 'CM'         then 'Corrective'
            when 'INSPECTION' then 'Inspection'
            when 'INSP'       then 'Inspection'
            when 'EMERGENCY'  then 'Emergency'
            when 'EM'         then 'Emergency'
            else trim(type)
        end                                                 as wo_type,

        -- W3: numeric priorities -> P1..P4; missing priority defaulted to P3 and flagged
        case
            when priority is null              then 'P3'
            when trim(priority) in ('1', '2', '3', '4') then 'P' || trim(priority)
            else upper(trim(priority))
        end                                                 as priority,
        priority is null                                    as is_priority_imputed,

        -- W4: status variants
        case upper(replace(trim(status), '_', ' '))
            when 'OPEN'        then 'Open'
            when 'IN PROGRESS' then 'In Progress'
            when 'COMPLETED'   then 'Completed'
            when 'COMPLETE'    then 'Completed'
            when 'DONE'        then 'Completed'
            when 'CANCELLED'   then 'Cancelled'
            when 'CANCELED'    then 'Cancelled'
            else trim(status)
        end                                                 as status,

        -- W5: mixed formats and invalid dates -> null
        {{ parse_date('raised_date') }}                     as raised_date,
        {{ parse_date('due_date') }}                        as due_date,
        {{ parse_date('completed_date') }}                  as completed_date,

        _source_file,
        _row_number,
        _loaded_at
    from deduped

)

select
    *,
    -- W6: keep the row, label the problem
    case
        when raised_date is null                               then 'invalid_raised_date'
        when status = 'Completed' and completed_date is null   then 'completed_without_date'
        when completed_date < raised_date                      then 'completed_before_raised'
    end                                                     as dq_issue
from cleaned
