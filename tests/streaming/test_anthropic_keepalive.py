"""Exercise the real converter without importing database/auth startup code."""
import ast
import asyncio
import json
import logging
import unittest
from pathlib import Path

source=Path(__file__).parents[2]/'backend/open_webui/utils/anthropic.py'
fn=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='openai_stream_to_anthropic_stream')
ns={'json':json,'log':logging.getLogger('test')}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
convert=ns[fn.name]

class ConverterTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_then_answer(self):
        async def upstream():
            yield b': keepalive\n\n'
            yield b'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":"stop"}]}\n\n'
            yield b'data: [DONE]\n\n'
        data=b''.join([x async for x in convert(upstream())])
        self.assertIn(b'event: ping',data);self.assertIn(b'hello',data);self.assertIn(b'event: message_stop',data)
    async def test_upstream_error_is_not_success(self):
        async def upstream():
            yield b'data: {"error":{"message":"busy"}}\n\n'
        data=b''.join([x async for x in convert(upstream())])
        self.assertIn(b'event: error',data);self.assertNotIn(b'event: message_stop',data)
    async def test_consumer_close_closes_upstream(self):
        closed=[]
        async def upstream():
            try:yield b': keepalive\n\n'
            finally:closed.append(True)
        stream=convert(upstream());await anext(stream);await anext(stream);await stream.aclose()
        self.assertEqual(closed,[True])
    async def test_exception_is_not_success(self):
        async def upstream():
            yield b': keepalive\n\n'
            raise ConnectionError('private upstream URL must not escape')
        data=b''.join([x async for x in convert(upstream())])
        self.assertIn(b'event: error',data);self.assertNotIn(b'private upstream',data);self.assertNotIn(b'event: message_stop',data)
if __name__=='__main__':unittest.main()
