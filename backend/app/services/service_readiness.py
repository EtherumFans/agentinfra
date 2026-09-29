"""Bounded database readiness probe; no credentials or database names in responses."""
import asyncio
from sqlalchemy import text

async def database_readiness(engine, timeout=3.0):
    async def probe():
        async with engine.connect() as connection:
            await connection.execute(text('SELECT 1'))
    try:
        await asyncio.wait_for(probe(), timeout)
    except Exception:
        return {'schema':'icoder.readiness/v1','ready':False,'database':'unavailable'}
    return {'schema':'icoder.readiness/v1','ready':True,'database':'reachable'}
