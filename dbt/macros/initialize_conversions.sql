{% macro initialize_conversions() %}
{% if target.type != 'postgres' or target.schema != 'dbt_dev' %}
  {{ exceptions.raise_compiler_error('This migration supports PostgreSQL dbt_dev only.') }}
{% endif %}
CREATE OR REPLACE FUNCTION {{ target.schema }}.try_iowa_numeric(value TEXT)
RETURNS NUMERIC
LANGUAGE plpgsql STABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$
BEGIN
    -- Enforce finite decimal syntax before PostgreSQL numeric validation.
    IF value !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' THEN
        RETURN NULL;
    END IF;
    IF NOT pg_input_is_valid(value, 'numeric') THEN
        RETURN NULL;
    END IF;
    RETURN value::NUMERIC;
END;
$$;

CREATE OR REPLACE FUNCTION {{ target.schema }}.try_iowa_bigint(value TEXT)
RETURNS BIGINT
LANGUAGE plpgsql STABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$
BEGIN
    IF value !~ '^[+-]?[0-9]+$' THEN
        RETURN NULL;
    END IF;
    -- Test the BIGINT range before reaching the cast statement.
    IF NOT pg_input_is_valid(value, 'bigint') THEN
        RETURN NULL;
    END IF;
    RETURN value::BIGINT;
END;
$$;

CREATE OR REPLACE FUNCTION {{ target.schema }}.try_iowa_date(value TEXT)
RETURNS DATE
LANGUAGE plpgsql STABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$
BEGIN
    IF value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
        RETURN NULL;
    END IF;
    IF NOT pg_input_is_valid(value, 'date') THEN
        RETURN NULL;
    END IF;
    RETURN value::DATE;
END;
$$
{% endmacro %}
