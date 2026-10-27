-- One row per opportunity with account segment and cycle length.
create or replace view opps as
select
    o.opportunity_id, o.account_id, o.type, o.owner_id, o.lead_source,
    a.segment,
    o.created_at::date as created_date,
    o.close_date, o.stage, o.is_closed, o.is_won, o.loss_reason, o.forecast_category,
    o.amount,
    datediff('day', o.created_at::date, o.close_date) as cycle_days
from raw.opportunities o
join raw.accounts a using (account_id);

-- Stage spans: when each opportunity entered a stage and when it left it (null = still there).
create or replace view stage_spans as
select
    opportunity_id, stage, entered_at,
    lead(entered_at) over (partition by opportunity_id order by entered_at) as exited_at
from raw.opportunity_stage_history;
