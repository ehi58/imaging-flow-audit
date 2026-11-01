-- One row per vocabulary entry, so a rule reads the committed vocabulary and
-- never a literal of its own: an allowlist typed into a rule is a second,
-- unchecked declaration of the vocabulary.
select 'payer' as kind, payer_id as code, name as label, member_id_prefix as prefix, try_cast(member_id_digits as integer) as digits, cast(null as integer) as views
from {{ source('warehouse', 'vocab_payers') }}
union all
select 'procedure', cpt, body_part_examined, cast(null as varchar), cast(null as integer), try_cast(views as integer)
from {{ source('warehouse', 'vocab_procedures') }}
union all
select 'body_part', term, term, cast(null as varchar), cast(null as integer), cast(null as integer)
from {{ source('warehouse', 'vocab_body_part_terms') }}
