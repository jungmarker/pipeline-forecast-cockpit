-- Stage-to-stage conversion for closed new-business deals, by segment.
-- A deal "reached" a stage if it has a history row for it; closed-won deals reached every stage.
with closed as (
    select opportunity_id, segment from opps where type = 'New Business' and is_closed
), reached as (
    select c.segment, h.stage, count(distinct h.opportunity_id) as deals
    from closed c join raw.opportunity_stage_history h using (opportunity_id)
    group by all
)
select
    segment, stage, deals,
    deals / first_value(deals) over (partition by segment order by
        case stage when 'Discovery' then 1 when 'Demo' then 2 when 'Proposal' then 3
                   when 'Negotiation' then 4 when 'Closed Won' then 5 else 6 end) as share_of_created
from reached
where stage <> 'Closed Lost'
order by segment, case stage when 'Discovery' then 1 when 'Demo' then 2 when 'Proposal' then 3
                             when 'Negotiation' then 4 when 'Closed Won' then 5 end;
