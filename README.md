# OKR Planning App

A lightweight planning app on top of the cascaded OKR + business case schema.
Strategy → Objectives → Key Results → Initiatives → Business Cases, with outcomes
and output deliberately kept separate.

## Local setup

```bash
# 1. Clone, then create a virtual env
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 2. Install deps
pip install -r requirements.txt

# 3. Configure Supabase secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml with your project URL + anon key

# 4. Run
streamlit run app.py
```

## Pages

- **Overview** (`app.py`) — joined read-only view of objectives → KRs → initiatives → business cases. Confirms the wiring end to end.
- More pages get added under `pages/` as the read layer expands.

## Schema

See `okr_schema.sql` (in the parent project). Six tables: `org_unit`, `strategy`,
`objective`, `key_result`, `initiative`, `initiative_key_result`, `business_case`.
RLS is off for local dev.
