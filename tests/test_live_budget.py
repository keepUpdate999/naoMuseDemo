import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_live_budget_rejects_before_extra_request(tmp_path, monkeypatch):
    # Import in a subprocess-free isolated module, restore server hooks afterwards.
    import server
    old_config, old_build = server.config, server.build_agent
    old_env_port = __import__('os').environ.get('DEMO_PORT')
    old_env_data = __import__('os').environ.get('DEMO_DATA')
    spec = importlib.util.spec_from_file_location('live_budget_fixture', Path(__file__).parent/'serve_live_acceptance.py')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, 'BUDGET', tmp_path/'budget.json')
        module.budget_save({'limit':60,'attempts':60,'responses':0,'input_tokens':0,'output_tokens':0,'requests':[]})
        calls=[]
        class Inner:
            settings=SimpleNamespace(max_tokens=1024)
            async def ask(self,*args,**kwargs):
                calls.append(1)
        with pytest.raises(RuntimeError,match='budget exhausted'):
            await module.BudgetLLM(Inner()).ask([])
        assert not calls
    finally:
        server.config, server.build_agent = old_config, old_build
        import os
        for key,value in [('DEMO_PORT',old_env_port),('DEMO_DATA',old_env_data)]:
            if value is None:
                os.environ.pop(key,None)
            else:
                os.environ[key]=value
