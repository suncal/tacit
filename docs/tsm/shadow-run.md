# Shadow run on the Tacit Demo workspace

Goal: Tacit watches a colleague ask the same kind of question four times and Sunny answer it three times, mines the job,
then drafts the fourth answer itself before Sunny replies, and the judge scores the draft against Sunny's real reply.

## The second account ("Priya")

Join link (expires in 30 days): https://join.slack.com/t/tacit-demo/shared_invite/zt-4ct463jhi-EqnI58TP4UKN~HX6x~yb5Q

Open it on your phone, or in a private browser window, with any other email. Name the account **Priya** so the
console reads naturally. Join #all-tacit-demo. Nothing else.

## What Priya posts (one message each, as a new message in #all-tacit-demo, not in a thread)

Post one, wait for Sunny's reply (Claude posts it from the Chrome tab within a minute), then post the next.

1. `Can someone send Northwind their invoice for September? They asked for a copy.`
2. `Globex needs a copy of last month's invoice, who can send it?`
3. `Initech is asking for their August invoice copy, can you resend it?`
4. `Umbrella wants a copy of their invoice from last month, can someone send it over?`

## What Sunny replies (Claude does this, in the thread under each ask)

1. `Sent — Northwind's September invoice is on its way, net 30 as usual. PDF is in Finance/Invoices.`
2. `Done — Globex invoice sent, net 30. Copy saved in Finance/Invoices.`
3. `Sent Initech their August invoice just now, net 30 terms. It's in Finance/Invoices.`

After ask 3, Claude runs mining, promotes the job to shadow, and shows the playbook in the console.

Ask 4 then arrives with the job in shadow: Tacit drafts a reply (visible on the Shadow page, not posted), Sunny replies
for real, and the judge scores the draft against the real reply. That score is the first trust evidence for the job.
