"""Continue the existing authorized ledger; no silent budget reset."""
import json
import os
from pathlib import Path
import time

from nanomuse.llm.base import BaseLLM

LEDGER=Path(__file__).resolve().parents[1]/'.local/live-acceptance-20261022/budget.json'


def read_budget():
    if not LEDGER.exists():
        raise RuntimeError('缺少已授权请求账本，不会自动创建新额度')
    return json.loads(LEDGER.read_text(encoding='utf-8'))


def save_budget(data):
    temp=LEDGER.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(LEDGER)


class BudgetLLM(BaseLLM):
    vision_available=False
    def __init__(self,inner,log):
        self.inner=inner;self.settings=inner.settings;self.log=log

    async def ask(self,*args,**kwargs):
        import msvcrt
        with LEDGER.with_suffix('.lock').open('a+b') as lock:
            if os.fstat(lock.fileno()).st_size==0:
                lock.write(b'0');lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                raise RuntimeError('另一个验收任务正在使用模型额度') from None
            try:
                data=read_budget()
                limit=data.get('limit',60)
                if limit is not None and data['attempts']>=int(limit):
                    raise RuntimeError(f'授权的{limit}次请求已用完，请补充调用预算后继续')
                data['attempts']+=1
                record={'number':data['attempts'],'time':time.time(),'status':'sent','suite':'real-apps'}
                data['requests'].append(record);save_budget(data)
                self.log('budget',f'模型调用 #{data["attempts"]}，单次输出不超过1024 tokens')
                kwargs['max_tokens']=min(kwargs.get('max_tokens') or 1024,1024)
                try:
                    result=await self.inner.ask(*args,**kwargs)
                except BaseException as exc:
                    record.update(status='failed',error_type=type(exc).__name__)
                    if isinstance(getattr(exc,'status_code',None),int):
                        record['http_status']=exc.status_code
                    save_budget(data)
                    raise
                record.update(status='responded',seconds=round(time.time()-record['time'],2),usage=result.usage)
                data['responses']+=1
                data['input_tokens']+=int(result.usage.get('prompt_tokens',result.usage.get('input_tokens',0)))
                data['output_tokens']+=int(result.usage.get('completion_tokens',result.usage.get('output_tokens',0)))
                save_budget(data)
                return result
            finally:
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
