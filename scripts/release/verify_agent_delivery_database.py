"""Read-only application-role deployment check. Credentials come from environment."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))

async def verify():
    from app.database import engine, verify_production_database, PRODUCTION_SCHEMA_REVISION
    from sqlalchemy import text
    await verify_production_database()
    async with engine.connect() as connection:
        version=(await connection.execute(text('SHOW server_version'))).scalar_one()
        columns=set((await connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='run_history'"))).scalars())
        required={'executed_agent_version','draft_preview','manual_review_required'}
        if not required.issubset(columns):raise RuntimeError('Run execution evidence columns missing')
        # Missing tenant context must never reveal cross-tenant release evidence.
        await connection.execute(text("SELECT set_config('icoder.current_organization_id','',true)"))
        for table in ('agent_releases','agent_evaluations','agent_evaluation_reviews','agent_jobs','agent_dependencies','model_connections','run_history','evaluation_datasets','evaluation_batches','evaluation_batch_items'):
            count=(await connection.execute(text(f'SELECT COUNT(*) FROM {table}'))).scalar_one()
            if count:raise RuntimeError('Tenant context omission exposed rows')
    await engine.dispose()
    return {'passed':True,'database':'PostgreSQL','server_version':version,
        'schema_revision':PRODUCTION_SCHEMA_REVISION,'application_role_verified':True,
        'tenant_policies_verified':True,'execution_evidence_columns_verified':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    try: report=asyncio.run(verify())
    except Exception as exc:
        # Never include connection strings or driver exception payloads in reports.
        report={'passed':False,'error_type':type(exc).__name__}
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    sys.exit(0 if report['passed'] else 1)
