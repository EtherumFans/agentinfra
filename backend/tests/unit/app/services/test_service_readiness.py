import asyncio
import pytest
from app.services.service_readiness import database_readiness

class Connection:
    def __init__(self, failure=False, delay=0): self.failure=failure;self.delay=delay;self.closed=False
    async def __aenter__(self): return self
    async def __aexit__(self,*args): self.closed=True
    async def execute(self,statement):
        assert str(statement)=='SELECT 1'
        if self.failure: raise RuntimeError('postgres://private-password')
        await asyncio.sleep(self.delay)
    def connect(self): return self

@pytest.mark.asyncio
async def test_ready_requires_real_query_and_releases_connection():
    connection=Connection()
    assert (await database_readiness(connection))['ready']
    assert connection.closed

@pytest.mark.asyncio
async def test_failure_is_bounded_and_does_not_expose_database_details():
    connection=Connection(failure=True)
    result=await database_readiness(connection)
    assert result=={'schema':'icoder.readiness/v1','ready':False,'database':'unavailable'}
    assert connection.closed
    slow=Connection(delay=1)
    assert not (await database_readiness(slow,timeout=0.01))['ready']
    assert slow.closed
