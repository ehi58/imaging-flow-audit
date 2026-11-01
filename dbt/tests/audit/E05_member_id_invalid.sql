-- E05: the member ID on a claim must fit its payer's scheme (prefix, length,
-- Luhn check digit) and belong to one patient only.
with lines as (select * from {{ ref('stg_claim_lines') }} where payer_id <> 'SELF'),
payers as (select code as payer_id, prefix, digits from {{ ref('stg_vocab') }} where kind = 'payer'),
shared as (
  select member_id from {{ ref('stg_coverage') }} group by member_id having count(distinct mrn) > 1
)
select l.claim_line_id as record_key, 'E05' as rule
from lines l join payers p on p.payer_id = l.payer_id
where l.member_id is null
   or l.member_id = ''
   or left(l.member_id, length(p.prefix)) <> p.prefix
   or length(l.member_id) <> length(p.prefix) + p.digits
   or not {{ luhn_ok("substr(l.member_id, length(p.prefix) + 1)") }}
   or l.member_id in (select member_id from shared)
