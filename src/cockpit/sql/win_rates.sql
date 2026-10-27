-- New-business win rate and average won ACV by lead source, last 12 months of closes.
select
    lead_source,
    count(*) as closed_deals,
    avg(is_won::int) as win_rate,
    avg(case when is_won then amount end) as avg_won_acv,
    sum(case when is_won then amount else 0 end) as won_acv
from opps
where type = 'New Business' and is_closed
  and close_date > (select max(close_date) from opps where is_closed) - interval 12 month
group by all
order by win_rate desc;
