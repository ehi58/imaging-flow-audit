-- E08: the ordering NPI is present, Luhn-valid over the 80840 prefix, and an individual in the registry.
select o.accession as record_key, 'E08' as rule
from {{ ref('stg_orders') }} o
where o.control = 'NW'
  and (
    coalesce(o.ordering_npi, '') = ''
    or not regexp_matches(o.ordering_npi, '^[0-9]{10}$')
    or not {{ luhn_ok("'80840' || o.ordering_npi") }}
    or not exists (select 1 from {{ ref('stg_providers') }} p where p.npi = o.ordering_npi and p.entity_type = 1)
  )
