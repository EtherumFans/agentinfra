"""Copy a frozen SQLite backup into an empty, pre-migrated PostgreSQL database.

Credentials are environment-only. Default is a read-only compatibility inventory.
Requires a maintenance account able to read all tenants; runtime must use a
separate restricted account. Never truncates or overwrites destination data.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/scripts'))


def migrate(source, apply=False):
    from sqlalchemy import create_engine, MetaData, select, text, Boolean, JSON, DateTime, Date
    from backfill_phi_envelopes import TEXT_COLUMNS, JSON_COLUMNS
    TEXT_COLUMNS={**TEXT_COLUMNS,'agent_jobs':('payload','result')}
    from app.services.phi_encryption import encrypt_phi, decrypt_phi, is_encrypted_value
    engine = create_engine(os.environ['ICODER_MIGRATION_TARGET_URL'], hide_parameters=True)
    if engine.dialect.name!='postgresql': raise RuntimeError('PostgreSQL_destination_required')
    meta = MetaData()
    meta.reflect(engine)
    source_db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    source_db.row_factory = sqlite3.Row
    tables = [r[0] for r in source_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    counts = {t: source_db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables}
    populated = {t:n for t,n in counts.items() if n and t!='alembic_version'}
    missing = [t for t in populated if t not in meta.tables]
    if missing: raise RuntimeError('destination_tables_missing:' + ','.join(missing))
    extra = {t:sorted({r[1] for r in source_db.execute('PRAGMA table_info("'+t+'")')} - set(meta.tables[t].c.keys())) for t in populated}
    extra = {t:c for t,c in extra.items() if c}
    report = {'source_counts':populated, 'source_only_columns':extra, 'applied':False}
    if not apply: return report
    # Refuse silently dropping populated legacy columns.
    if extra: raise RuntimeError('source_only_columns_require_explicit_mapping')

    def canonical(value):
        if isinstance(value,dt.datetime):
            return value.replace(tzinfo=dt.timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(dt.timezone.utc).isoformat()
        if isinstance(value,dt.date): return value.isoformat()
        return value

    def logical(row,table):
        result=dict(row)
        for key in (*TEXT_COLUMNS.get(table,()),*JSON_COLUMNS.get(table,())):
            if result.get(key) is not None:
                result[key]=decrypt_phi(result[key]) if is_encrypted_value(result[key]) else result[key]
                if key in JSON_COLUMNS.get(table,()): result[key]=json.loads(result[key])
        return {k:canonical(v) for k,v in result.items()}

    def digest(rows):
        return hashlib.sha256('\n'.join(sorted(json.dumps(r,ensure_ascii=False,sort_keys=True,default=str) for r in rows)).encode()).hexdigest()

    with engine.begin() as conn:
        conn.execute(text("SET LOCAL timezone='UTC'"))
        from app.database import PRODUCTION_SCHEMA_REVISION
        if conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one_or_none()!=PRODUCTION_SCHEMA_REVISION:
            raise RuntimeError('destination_schema_revision_mismatch')
        for table in meta.tables.values():
            if table.name!='alembic_version' and conn.execute(select(table).limit(1)).first():
                raise RuntimeError('destination_not_empty:'+table.name)
        imported={}
        for table in meta.sorted_tables:
            name=table.name
            if name not in populated: continue
            rows=[]
            for raw in source_db.execute('SELECT * FROM "'+name+'"'):
                row=dict(raw)
                for key,value in list(row.items()):
                    if value is None: continue
                    typ=table.c[key].type
                    if key in (*TEXT_COLUMNS.get(name,()),*JSON_COLUMNS.get(name,())):
                        row[key]=value if is_encrypted_value(value) else encrypt_phi(value)
                    elif isinstance(typ,JSON) and isinstance(value,str): row[key]=json.loads(value)
                    elif isinstance(typ,Boolean): row[key]=bool(value)
                    elif isinstance(typ,DateTime) and isinstance(value,str): row[key]=dt.datetime.fromisoformat(value)
                    elif isinstance(typ,Date) and isinstance(value,str): row[key]=dt.date.fromisoformat(value)
                rows.append(row)
            try:
                conn.execute(table.insert(),rows)
            except Exception as exc:
                diag=getattr(getattr(exc,'orig',None),'diag',None)
                category=(getattr(diag,'message_primary','') or '').split(':')[0]
                raise RuntimeError('insert_failed:'+name+':'+str(getattr(diag,'sqlstate',''))+':'+category) from None
            actual=[dict(r) for r in conn.execute(select(table)).mappings()]
            expected=[{k:r[k] for k in rows[0]} for r in actual]
            if len(actual)!=len(rows) or digest([logical(r,name) for r in rows])!=digest([logical(r,name) for r in expected]):
                raise RuntimeError('row_verification_failed:'+name)
            imported[name]={'count':len(rows),'logical_digest':digest([logical(r,name) for r in expected])}
        # Reset only sequences belonging to imported tables, after explicit IDs.
        for name in imported:
            for col in meta.tables[name].primary_key:
                seq=conn.execute(text('SELECT pg_get_serial_sequence(:t,:c)'),{'t':name,'c':col.name}).scalar()
                if seq: conn.execute(text('SELECT setval(:seq,COALESCE((SELECT max("'+col.name+'") FROM "'+name+'"),1),true)'),{'seq':seq})
        report.update(applied=True,verified=imported)
    source_db.close();engine.dispose()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try: result=migrate(args.source.resolve(),args.apply)
    except Exception as exc:
        # Driver exceptions can contain bound clinical data or credentials.
        result={'applied':False,'error_type':type(exc).__name__}
        if type(exc) is RuntimeError: result['reason']=str(exc)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    sys.exit(1 if 'error_type' in result else 0)
