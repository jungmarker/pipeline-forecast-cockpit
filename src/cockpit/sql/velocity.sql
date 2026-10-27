-- Median days spent in each open stage (closed deals only, so every span has an end).
select
    o.segment, s.stage,
    median(datediff('day', s.entered_at, s.exited_at)) as median_days,
    count(*) as spans
from stage_spans s
join opps o using (opportunity_id)
where o.type = 'New Business' and o.is_closed and s.exited_at is not null
  and s.stage in ('Discovery', 'Demo', 'Proposal', 'Negotiation')
group by o.segment, s.stage
order by o.segment, case s.stage when 'Discovery' then 1 when 'Demo' then 2 when 'Proposal' then 3 else 4 end;
