select npi, try_cast(entity_type as integer) as entity_type, role, family, given, organization_name, taxonomy_code
from {{ source('warehouse', 'providers') }}
