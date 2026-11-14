"""Shared provider usage collection and membership reservation client."""
import asyncio, json, logging, os, re, threading, uuid
import requests
from contextvars import ContextVar

current_meter=ContextVar('current_membership_meter',default=None)
log=logging.getLogger(__name__)

class Meter:
    def __init__(self, base, secret, identity, model, source):
        self.base=base.rstrip('/');self.secret=secret;self.identity=identity;self.model=model;self.source=source
        self.id=str(uuid.uuid4());self.reservation=None;self.usage={};self.anthropic=False
        self.buffer=b'';self.sse=None;self.stop=threading.Event();self.finished=False
    def post(self,path,payload):
        r=requests.post(self.base+path,json=payload,headers={'Authorization':'Bearer '+self.secret},timeout=(5,20))
        r.raise_for_status();return r.json()
    def start(self,payload):
        if payload.get('n',1) != 1 or payload.get('best_of',1) != 1:
            raise ValueError('Use one completion per request; concurrent requests are supported by your plan.')
        output=payload.get('max_output_tokens',payload.get('max_completion_tokens',payload.get('max_tokens',65536)))
        if isinstance(output,bool) or not isinstance(output,int) or output<=0:raise ValueError('Invalid maximum output tokens')
        # A byte upper bound is conservative for text. The server rejects requests
        # exceeding its 1M total context; cap that bound at the supported context.
        prompt={k:v for k,v in payload.items() if k not in ('max_tokens','max_completion_tokens','max_output_tokens','stream','stream_options')}
        inputs=min(1_000_000,len(json.dumps(prompt,ensure_ascii=False).encode())+4096)
        r=self.post('/generation/admit',{**self.identity,'model':self.model,'input_tokens':inputs,'max_output_tokens':output})
        if r.get('member') and not r.get('allowed'):raise PermissionError(r.get('message','Allowance unavailable'))
        self.identity={'email':r['email']}
        if r.get('reservation_id'):
            self.reservation=r['reservation_id']
            for key in ('max_output_tokens','max_completion_tokens','max_tokens'):
                if key in payload:payload[key]=r['max_output_tokens']
            if not any(k in payload for k in ('max_output_tokens','max_completion_tokens','max_tokens')):
                payload['max_output_tokens' if 'input' in payload else 'max_tokens']=r['max_output_tokens']
            threading.Thread(target=self.heartbeat,daemon=True).start()
        if payload.get('stream') and 'messages' in payload:
            payload['stream_options']={**(payload.get('stream_options') or {}),'include_usage':True}
        return payload
    def heartbeat(self):
        while not self.stop.wait(45):
            try:self.post('/generation/touch',{'reservation_id':self.reservation})
            except Exception:log.warning('Membership lease heartbeat failed: %s',self.id)
    def observe(self,obj):
        if not isinstance(obj,dict):return
        kind=obj.get('type','')
        envelope=obj
        if kind=='message_start':envelope=obj.get('message') or {};self.anthropic=True
        elif kind in ('message_delta','message'):self.anthropic=True
        elif kind.startswith('response.'):envelope=obj.get('response') or {}
        if isinstance(envelope.get('usage'),dict):self.usage.update(envelope['usage'])
    def feed(self,chunk):
        if isinstance(chunk,str):chunk=chunk.encode()
        self.buffer+=chunk
        if self.sse is None and self.buffer.strip():self.sse=not self.buffer.lstrip().startswith((b'{',b'['))
        if self.sse:
            while (boundary:=re.search(rb'\r?\n\r?\n',self.buffer)):
                event,self.buffer=self.buffer[:boundary.start()],self.buffer[boundary.end():]
                data=b'\n'.join(line[5:].strip() for line in event.splitlines() if line.startswith(b'data:'))
                try:self.observe(json.loads(data))
                except (ValueError,UnicodeDecodeError):pass
            if len(self.buffer)>8_000_000:self.buffer=b''
    def finish(self):
        if self.finished:return
        self.finished=True
        if self.sse is False and self.buffer:
            try:self.observe(json.loads(self.buffer))
            except (ValueError,UnicodeDecodeError):pass
        u=self.usage
        cached=(u.get('cache_read_input_tokens',0) if self.anthropic else (u.get('prompt_tokens_details') or u.get('input_tokens_details') or {}).get('cached_tokens',u.get('cached_tokens',0))) or 0
        inp=u.get('prompt_tokens',u.get('input_tokens',0)) or 0
        if self.anthropic:inp+=cached+(u.get('cache_creation_input_tokens') or 0)
        out=u.get('completion_tokens',u.get('output_tokens',0)) or 0
        payload={**self.identity,'source':self.source,'model':self.model,'request_id':self.id,'input_tokens':inp,'output_tokens':out,'cached_tokens':cached}
        path='/usage'
        if self.reservation:path='/generation/settle';payload['reservation_id']=self.reservation
        try:
            if not self.usage and self.reservation:log.warning('Generation ended without provider usage: %s',self.id)
            for attempt in range(3):
                try:self.post(path,payload);break
                except Exception:
                    if attempt==2:log.exception('Usage settlement failed: %s',self.id)
        finally:self.stop.set()
    async def wrap(self,iterator):
        try:
            async for chunk in iterator:
                self.feed(chunk);yield chunk
        finally:
            await asyncio.shield(asyncio.to_thread(self.finish))
