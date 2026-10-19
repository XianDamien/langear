"""Run inside the isolated backend container; credentials stay in its environment.

python /tmp/probe_model.py --model qwen-audio-3.1-realtime-plus --pcm /tmp/dialogue-smoke.pcm
Uses synthetic lesson data only. Prints evidence without keys or raw audio.
"""
import argparse
import asyncio
import base64
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from websockets.asyncio.client import connect
from core.config import get_settings


async def probe(model, pcm, voice):
    settings = get_settings()
    url = settings.dialogue_ws_url + ('&' if '?' in settings.dialogue_ws_url else '?') + urlencode({'model': model})
    report = {'requested_model': model, 'voice': voice, 'turns': [], 'audio_bytes': 0, 'tool_called': False}
    async with connect(url, additional_headers={'Authorization': 'Bearer ' + settings.dialogue_api_key.get_secret_value()},
            open_timeout=20, max_size=4 * 1024 * 1024) as ws:
        async def send(event):
            await ws.send(json.dumps(event))

        async def receive_until(target):
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), 60))
                kind = event.get('type')
                if kind == 'error':
                    error = event.get('error', {})
                    raise RuntimeError(json.dumps({'code': error.get('code'), 'message': error.get('message')}, ensure_ascii=False))
                if kind in ('response.audio.delta', 'response.output_audio.delta'):
                    report['audio_bytes'] += len(base64.b64decode(event['delta']))
                    report.setdefault('first_audio_seconds', round(time.monotonic() - started, 2))
                if kind in ('response.audio_transcript.delta', 'response.output_audio_transcript.delta', 'response.text.delta'):
                    transcript.append(event.get('delta', ''))
                if kind == 'response.function_call_arguments.done':
                    report['tool_called'] = event.get('name') == 'probe_context' and json.loads(event.get('arguments', '{}')).get('lesson') == 'apple'
                    await send({'type': 'conversation.item.create', 'item': {'type': 'function_call_output',
                        'call_id': event['call_id'], 'output': '{"available":true}'}})
                if kind == target:
                    return event

        transcript = []
        started = time.monotonic()
        created = await receive_until('session.created')
        report['returned_model'] = created.get('session', {}).get('model')
        await send({'type': 'session.update', 'session': {
            'modalities': ['text', 'audio'], 'turn_detection': None,
            'audio': {'input': {'format': {'type': 'pcm', 'sample_rate': 16000}},
                'output': {'voice': voice, 'format': {'type': 'pcm', 'sample_rate': 24000}}},
            'input_audio_transcription': {'model': settings.dialogue_asr_model},
            'instructions': 'You are a friendly English teacher. Use brief simple English. The learner just practised buying an apple. First ask them to recap what they practised. Wait for their reply.',
            'tools': [{'type': 'function', 'name': 'probe_context', 'description': 'Read a test lesson context.',
                'parameters': {'type': 'object', 'properties': {'lesson': {'type': 'string'}}, 'required': ['lesson'], 'additionalProperties': False}}],
        }})
        await receive_until('session.updated')
        await send({'type': 'conversation.item.create', 'item': {'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text': 'Let’s start. Ask me for a brief recap of my practice.'}]}})
        await send({'type': 'response.create'})
        response = await receive_until('response.done')
        assert response['response']['status'] == 'completed', response
        report['turns'].append({'teacher': ''.join(transcript)})
        transcript.clear()
        raw = Path(pcm).read_bytes()
        await send({'type': 'input_audio_buffer.clear'})
        for offset in range(0, len(raw), 3200):
            await send({'type': 'input_audio_buffer.append', 'audio': base64.b64encode(raw[offset:offset + 3200]).decode()})
        await send({'type': 'input_audio_buffer.commit'})
        learner = await receive_until('conversation.item.input_audio_transcription.completed')
        report['learner_transcript'] = learner.get('transcript')
        await send({'type': 'response.create', 'response': {'instructions': 'Respond to the learner in one short English sentence, then ask a short follow-up question.'}})
        response = await receive_until('response.done')
        assert response['response']['status'] == 'completed', response
        report['turns'].append({'teacher': ''.join(transcript)})
        await send({'type': 'response.create', 'response': {'instructions': 'This is a tool capability test. Call probe_context with lesson="apple" now. Do not speak before calling the tool.'}})
        await receive_until('response.done')
        assert report['audio_bytes'] > 0 and report['learner_transcript'] and report['tool_called'], report
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='qwen-audio-3.1-realtime-plus')
    parser.add_argument('--pcm', required=True)
    parser.add_argument('--voice', default='loongmary')
    args = parser.parse_args()
    asyncio.run(probe(args.model, args.pcm, args.voice))
