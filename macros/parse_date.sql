{#- Parse a messy date string: ISO first, then Australian DD/MM/YYYY.
    Anything unparseable (e.g. '2024-13-45', 'N/A') becomes null. -#}
{% macro parse_date(expr) -%}
    coalesce(
        try_to_date(trim({{ expr }}), 'YYYY-MM-DD'),
        try_to_date(trim({{ expr }}), 'DD/MM/YYYY')
    )
{%- endmacro %}
