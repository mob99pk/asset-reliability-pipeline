with source as (

    select * from {{ source('raw', 'assets') }}

),

flattened as (

    -- Nested JSON -> columns. No arrays per record, so path notation is enough
    -- (LATERAL FLATTEN would only be needed to explode arrays).
    select
        upper(trim(raw:asset_id::string))                          as asset_id,
        trim(raw:name::string)                                     as asset_name,
        initcap(trim(raw:classification:asset_class::string))      as asset_class,   -- A2
        initcap(trim(raw:classification:criticality::string))      as criticality,   -- A2
        coalesce(trim(raw:location:site::string), 'Unknown')       as site,          -- A3: null or missing key
        raw:location:region::string                                as region,
        {{ parse_date('raw:install_date::string') }}               as install_date,  -- A4
        try_to_timestamp_ntz(raw:updated_at::string)               as updated_at,
        _source_file,
        _row_number,
        _loaded_at
    from source

)

-- A1: keep the most recently updated version of each asset
select *
from flattened
qualify row_number() over (
    partition by asset_id order by updated_at desc, _row_number desc
) = 1
