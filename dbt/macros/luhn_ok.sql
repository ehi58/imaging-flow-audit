{% macro luhn_ok(digits) %}
  {#- Standard Luhn over a digit string: from the right, double every second digit. -#}
  (
    {{ digits }} is not null
    and regexp_matches({{ digits }}, '^[0-9]+$')
    and list_sum(
      list_transform(
        list_reverse(regexp_split_to_array({{ digits }}, '')),
        (x, i) -> case when i % 2 = 0
                       then case when x::int * 2 > 9 then x::int * 2 - 9 else x::int * 2 end
                       else x::int end
      )
    ) % 10 = 0
  )
{% endmacro %}
