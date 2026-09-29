"""Align legacy PostgreSQL enum labels with SQLAlchemy enum member names."""
from alembic import op
import sqlalchemy as sa

revision='088'
down_revision='087'
branch_labels=None
depends_on=None

LABELS={
    'templatecategory':{v:v.upper() for v in ('inpatient','surgery','outpatient','emergency','consultation','custom')},
    'templatelanguage':{'zh-CN':'ZH_CN','en-US':'EN_US'},
    'templatescope':{'all_customers':'ALL_CUSTOMERS','single_customer':'SINGLE_CUSTOMER'},
    'customerregion':{v:v.upper() for v in ('us','eu','cn')},
    'ticketstatus':{v:v.upper() for v in ('open','in_progress','resolved','closed')},
    'ticketpriority':{v:v.upper() for v in ('low','medium','high')},
    'userrole':{'cdi_specialist':'CDI_SPECIALIST','medical_records_admin':'MEDICAL_RECORDS_ADMIN'},
}

def rename(reverse=False):
    conn=op.get_bind()
    if conn.dialect.name!='postgresql': return
    for name,mapping in LABELS.items():
        labels=set(conn.execute(sa.text('SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid WHERE t.typname=:name'),{'name':name}).scalars())
        for old,new in mapping.items():
            if reverse: old,new=new,old
            if old in labels:
                if new in labels: raise RuntimeError('Ambiguous enum labels require reconciliation')
                # Constants above only; identifiers/values never come from user input.
                op.execute(f'ALTER TYPE "{name}" RENAME VALUE \'{old}\' TO \'{new}\'')

def upgrade(): rename()
def downgrade(): rename(True)
