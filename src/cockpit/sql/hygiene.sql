-- Pipeline hygiene: open deals a manager should challenge, by owner.
-- stale_close_date: close date already passed; missing_amount: no ACV; stuck: no stage change in 60+ days.
with last_move as (
    select opportunity_id, max(entered_at)::date as last_stage_change
    from raw.opportunity_stage_history group by 1
)
select
    u.full_name as owner, u.role,
    count(*) as open_deals,
    sum(coalesce(o.amount, 0)) as open_acv,
    sum((o.close_date < date '{as_of}')::int) as stale_close_date,
    sum((o.amount is null)::int) as missing_amount,
    sum((datediff('day', l.last_stage_change, date '{as_of}') > 60)::int) as stuck_60d
from opps o
join last_move l using (opportunity_id)
join raw.users u on u.user_id = o.owner_id
where not o.is_closed
group by all
order by stale_close_date + missing_amount + stuck_60d desc, open_acv desc;
