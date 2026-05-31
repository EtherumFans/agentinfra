"""WebSocket endpoint — real-time bidirectional communication

iCoDer equivalent: WebSocket connections for real-time streaming.
"""
import json
import logging
import tempfile
import os
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.middleware.auth import decode_token
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Track active connections
active_connections: dict[str, WebSocket] = {}
# STT audio buffers per connection
stt_buffers: dict[str, list[bytes]] = {}
stt_chunk_count: dict[str, int] = {}
# Last interim transcription text per connection (for dedup)
stt_last_interim: dict[str, str] = {}

# Locate ffmpeg binary via imageio-ffmpeg (bundled) or system PATH
_FFMPEG_PATH = "ffmpeg"
try:
    import imageio_ffmpeg
    _FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    # Add ffmpeg directory to PATH so whisper can find it
    _FFMPEG_DIR = os.path.dirname(_FFMPEG_PATH)
    os.environ["PATH"] = _FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")
    logger.info(f"STT ffmpeg configured via imageio-ffmpeg: {_FFMPEG_PATH}")
except ImportError:
    logger.warning("imageio-ffmpeg not available — falling back to system ffmpeg")


@router.websocket("/ws/agent/{expert_id}")
async def agent_websocket(websocket: WebSocket, expert_id: str):
    """WebSocket for real-time agent interaction.

    Client sends: {"type": "message", "content": "user text"}
    Server sends: {"type": "token", "text": "..."}  {"type": "done"}  {"type": "error", "message": "..."}
    """
    # Extract token from query params for auth
    token = websocket.query_params.get("token", "")
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub", "anonymous")
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return
    else:
        user_id = "anonymous"

    await websocket.accept()
    conn_id = f"{expert_id}-{user_id}"
    active_connections[conn_id] = websocket
    logger.info(f"WebSocket connected: {conn_id}")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "message":
                content = msg.get("content", "")
                await websocket.send_json({"type": "ack", "message": f"Received: {content[:100]}"})

                # Stream LLM response
                try:
                    result = await llm_service.chat(
                        messages=[{"role": "user", "content": content}],
                        temperature=0.1, max_tokens=500,
                    )
                    response_text = result.get("content", "") if isinstance(result, dict) else str(result)
                    # Simulate streaming by sending chunks
                    words = response_text.split()
                    for i in range(0, len(words), 5):
                        chunk = " ".join(words[i:i+5])
                        await websocket.send_json({"type": "token", "text": chunk + " "})
                    await websocket.send_json({"type": "done"})
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {conn_id}")
    finally:
        active_connections.pop(conn_id, None)


@router.websocket("/ws/speech-to-text")
async def stt_websocket(websocket: WebSocket):
    """WebSocket for real-time speech-to-text.

    Client sends: binary audio chunks (WebM/Opus from MediaRecorder)
    Client sends: {"type": "start", "mimeType": "audio/webm"} to begin a session
    Client sends: {"type": "end"} to finish and request transcription
    Server sends: {"type": "interim", "text": "..."} during recognition
    Server sends: {"type": "final", "text": "..."} when done
    """
    await websocket.accept()
    conn_id = f"stt-{id(websocket)}"
    active_connections[conn_id] = websocket
    stt_buffers[conn_id] = []
    current_mime = "audio/webm"
    logger.info(f"STT WebSocket connected: {conn_id}")

    try:
        while True:
            # Receive either text (JSON commands) or binary (audio chunks)
            data = await websocket.receive()

            if "text" in data:
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "start":
                    current_mime = msg.get("mimeType", "audio/webm")
                    stt_buffers[conn_id] = []
                    await websocket.send_json({"type": "ready"})

                elif msg_type == "interim":
                    # Streaming transcription for interim results (low latency)
                    audio_chunks = stt_buffers.get(conn_id, [])
                    if not audio_chunks:
                        await websocket.send_json({"type": "interim", "text": ""})
                        continue

                    combined = b"".join(audio_chunks)
                    last = stt_last_interim.get(conn_id, "")
                    text, err = await _transcribe_streaming(combined, current_mime)
                    if text and text != last:
                        stt_last_interim[conn_id] = text
                        await websocket.send_json({"type": "interim", "text": text})
                    elif err:
                        logger.warning(f"Streaming interim error: {err}")

                elif msg_type == "end":
                    # Process accumulated audio
                    audio_chunks = stt_buffers.get(conn_id, [])
                    if not audio_chunks:
                        await websocket.send_json({"type": "error", "message": "未收到音频数据，请检查麦克风权限"})
                        continue

                    combined = b"".join(audio_chunks)
                    text, err = await _transcribe_audio(combined, current_mime)

                    # Run speaker diarization on the same audio
                    diarization = []
                    try:
                        from app.services.speaker_diarizer import speaker_diarizer
                        # Save combined audio to WAV for diarization
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                            f.write(combined)
                            diar_wav = f.name
                        diarization = speaker_diarizer.diarize(diar_wav)
                        try:
                            os.unlink(diar_wav)
                        except Exception:
                            pass
                    except Exception as diar_err:
                        logger.warning(f"Speaker diarization failed: {diar_err}")

                    if text:
                        await websocket.send_json({
                            "type": "final",
                            "text": text,
                            "diarization": diarization,
                        })
                    else:
                        logger.error(f"Transcription failed: {err}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"转录失败: {err}"
                        })

                    # Reset buffer
                    stt_buffers[conn_id] = []
                    stt_last_interim.pop(conn_id, None)

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

            elif "bytes" in data:
                # Binary audio chunk
                chunk = data["bytes"]
                if conn_id in stt_buffers:
                    stt_buffers[conn_id].append(chunk)
                    stt_chunk_count[conn_id] = stt_chunk_count.get(conn_id, 0) + 1
                    total_bytes = sum(len(c) for c in stt_buffers[conn_id])

                    # Server-push interim every ~10 chunks (~1s of audio at 4KB/chunk)
                    if stt_chunk_count[conn_id] % 10 == 0:
                        combined = b"".join(stt_buffers[conn_id])
                        last = stt_last_interim.get(conn_id, "")
                        try:
                            text, err = await _transcribe_streaming(combined, current_mime)
                            if text and text != last:
                                stt_last_interim[conn_id] = text
                                await websocket.send_json({"type": "interim", "text": text})
                            elif err:
                                logger.warning(f"Streaming interim error: {err}")
                        except Exception as e:
                            logger.warning(f"Streaming interim exception: {e}")

                    # Buffering notification
                    if total_bytes % 32768 < 4096:
                        await websocket.send_json({"type": "buffering", "bytes": total_bytes})

    except WebSocketDisconnect:
        logger.info(f"STT WebSocket disconnected: {conn_id}")
    except Exception as e:
        logger.error(f"STT WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        active_connections.pop(conn_id, None)
        stt_buffers.pop(conn_id, None)
        stt_chunk_count.pop(conn_id, None)
        stt_last_interim.pop(conn_id, None)


# Cached Whisper model (singleton)
_whisper_model = None
_whisper_model_size = None


def _get_whisper_device() -> str:
    """Determine the best available device for Whisper inference."""
    from app.config import settings
    if settings.STT_DEVICE != "auto":
        return settings.STT_DEVICE
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("Whisper: CUDA GPU detected, using cuda")
            return "cuda"
    except ImportError:
        pass
    logger.info("Whisper: using CPU")
    return "cpu"


def _get_whisper_model():
    """Load Whisper model with caching. Uses configurable model size."""
    global _whisper_model, _whisper_model_size
    from app.config import settings
    model_size = settings.STT_WHISPER_MODEL

    if _whisper_model is not None and _whisper_model_size == model_size:
        return _whisper_model

    import whisper
    device = _get_whisper_device()
    logger.info(f"Loading Whisper model '{model_size}' on {device}...")
    _whisper_model = whisper.load_model(model_size, device=device)
    _whisper_model_size = model_size
    logger.info(f"Whisper model '{model_size}' loaded successfully on {device}")
    return _whisper_model


# Medical terminology — loaded from knowledge base hotword file
def _load_medical_prompt() -> str:
    """Build medical context prompt from 15K hotword list for Whisper."""
    hotword_path = Path(__file__).parent.parent.parent / "data" / "medical_hotwords.txt"
    if hotword_path.exists():
        with open(hotword_path, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
        # Whisper initial_prompt works best with shorter context
        sample = words[:300]
        return (
            "以下是医生和患者的临床对话转录。包含医学术语、诊断名称、手术名称。"
            "常见词汇：" + "、".join(sample[:200])
        )
    # Fallback prompt
    return (
        "以下是医生和患者的临床对话转录。包含医学术语、诊断名称、手术名称、"
        "检查项目、药品名称等。常见词汇：主诉、现病史、既往史、查体、辅助检查、"
        "初步诊断、入院诊断、出院诊断、鉴别诊断、建议、处理、治疗、手术、操作、"
        "用药、医嘱、高血压、糖尿病、冠心病、脑梗死、肺炎、骨质疏松、骨折、肿瘤。"
    )

# Common medical term corrections (Whisper frequently confuses these)
_MEDICAL_TERM_CORRECTIONS = {
    "骨子疏松": "骨质疏松", "冠性病": "冠心病", "老梗死": "脑梗死",
    "高血压病": "高血压", "前列腺肥大": "前列腺增生",
    "慢性堵塞性肺病": "慢性阻塞性肺疾病",
    "胆囊切除": "胆囊切除术", "阑尾切除": "阑尾切除术",
    "髋关节置换": "全髋关节置换术", "膝关节置换": "全膝关节置换术",
    "心脏支架": "冠状动脉支架植入术",
    "他丁": "他汀", "二甲双瓜": "二甲双胍",
    "主数": "主诉", "线病史": "现病史", "寄往史": "既往史",
    "初步整断": "初步诊断", "入院整断": "入院诊断", "茶体": "查体",
    "毫升每分钟": "ml/min", "毫米汞柱": "mmHg", "毫摩尔每升": "mmol/L",
}


def _correct_medical_terms(text: str) -> str:
    """Post-process transcription to correct common medical term errors."""
    result = text
    for wrong, correct in _MEDICAL_TERM_CORRECTIONS.items():
        if wrong in result:
            result = result.replace(wrong, correct)
            logger.debug(f"Medical term corrected: '{wrong}' -> '{correct}'")
    return result


def _restore_punctuation(text: str) -> str:
    """Restore basic Chinese punctuation to transcribed text."""
    if not text or not text.strip():
        return text
    transitions = ['查体', '体检', '辅助检查', '既往史', '个人史', '家族史',
                   '初步诊断', '入院诊断', '出院诊断', '诊断', '鉴别诊断',
                   '建议', '处理', '治疗', '手术', '操作', '用药', '医嘱',
                   '患者', '病人', '否认', '自述', '主诉', '现病史', '既往',
                   '检查', '检验', '化验', '影像', '病理', '会诊', '转科',
                   '目前', '目前情况', '目前诊断', '目前治疗']
    for t in transitions:
        text = text.replace(f' {t}', f'。{t}')
        text = text.replace(f'{t} ', f'{t}，')

    if text and text[-1] not in '。！？…）)':
        text = text.rstrip() + '。'

    text = text.replace('。。', '。').replace('，，', '，')
    return text


async def _transcribe_streaming(audio_bytes: bytes, mime_type: str) -> tuple[str, str]:
    """Fast streaming transcription for interim results.

    Uses FunASR streaming Paraformer (no VAD, chunked inference).
    Falls back to whisper if unavailable.

    Returns (text, error_message).
    """
    suffix = ".webm" if "webm" in mime_type else ".wav"
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        # Attempt: FunASR streaming model
        try:
            from app.services.stt_service import transcribe_streaming as funasr_stream
            text, error = await funasr_stream(tmp_path)
            if text:
                return text, ""
            if error:
                logger.warning(f"Streaming ASR: {error}")
        except (ImportError, ModuleNotFoundError):
            pass
        except Exception as e:
            logger.warning(f"Streaming ASR failed: {e}")

        # Fallback: batch whisper
        return await _transcribe_audio(audio_bytes, mime_type)

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def _transcribe_audio(audio_bytes: bytes, mime_type: str) -> tuple[str, str]:
    """Transcribe audio bytes to text using available STT provider.

    Priority: 1) FunASR Paraformer batch (VAD + Punc pipeline, best accuracy)
              2) openai-whisper (fallback)
              3) speech_recognition (Google Web Speech, final fallback)

    Returns (text, error_message). If text is empty, error_message explains why.
    """
    suffix = ".webm" if "webm" in mime_type else ".wav"
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        audio_size_kb = len(audio_bytes) / 1024
        logger.info(f"Transcribing {audio_size_kb:.0f}KB audio ({mime_type})")

        # Attempt 1: FunASR Paraformer with 15K medical hotwords
        try:
            from app.services.stt_service import transcribe_audio as funasr_transcribe
            text, error = await funasr_transcribe(tmp_path)
            if text:
                return text, ""
            if error:
                logger.warning(f"FunASR: {error}")
        except (ImportError, ModuleNotFoundError):
            logger.info("stt_service not available, trying whisper...")
        except Exception as e:
            logger.warning(f"FunASR failed: {e}, trying whisper...")

        # Attempt 2: openai-whisper
        try:
            import whisper
            from app.config import settings

            model = _get_whisper_model()
            device = _get_whisper_device()

            transcribe_kwargs = {
                "language": "zh",
                "condition_on_previous_text": True,
                "no_speech_threshold": 0.6,
                "compression_ratio_threshold": 2.4,
                "logprob_threshold": -1.0,
            }
            if settings.STT_WHISPER_MODEL in ("medium", "large", "large-v3"):
                transcribe_kwargs["beam_size"] = 5
                transcribe_kwargs["best_of"] = 5
                transcribe_kwargs["temperature"] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
            if settings.STT_MEDICAL_TERMS_BOOST:
                transcribe_kwargs["initial_prompt"] = _load_medical_prompt()
            transcribe_kwargs["fp16"] = (device == "cuda")

            result = model.transcribe(tmp_path, **transcribe_kwargs)
            text = result["text"].strip()

            if text:
                text = _restore_punctuation(text)
                if settings.STT_MEDICAL_TERMS_BOOST:
                    text = _correct_medical_terms(text)
                logger.info(f"Whisper({settings.STT_WHISPER_MODEL}) transcribed {len(text)} chars")
                return text, ""
            else:
                logger.info("Whisper returned empty text")
        except (ImportError, ModuleNotFoundError):
            logger.info("whisper not installed, trying speech_recognition...")
        except FileNotFoundError as e:
            logger.warning(f"whisper needs ffmpeg on PATH: {e}")
        except Exception as e:
            logger.warning(f"whisper transcription failed: {e}")

        # Attempt 2: speech_recognition library (Google Web Speech)
        try:
            import speech_recognition as sr

            wav_path = tmp_path
            if "webm" in mime_type or suffix == ".webm":
                wav_path = tmp_path + ".wav"
                import subprocess
                result = subprocess.run(
                    [_FFMPEG_PATH, "-y", "-i", tmp_path, "-ar", "16000", "-ac", "1", wav_path],
                    capture_output=True, timeout=30,
                )
                if not os.path.exists(wav_path):
                    stderr = result.stderr.decode("utf-8", errors="replace")
                    logger.error(f"ffmpeg WebM→WAV conversion failed: {stderr[:200]}")
                    return "", f"音频格式转换失败，请确认 ffmpeg 已安装: {stderr[:100]}"

            r = sr.Recognizer()
            r.energy_threshold = 300
            r.dynamic_energy_threshold = True
            with sr.AudioFile(wav_path) as source:
                audio = r.record(source)
            logger.info(f"Audio loaded: {len(audio.frame_data)} frames, attempting Google STT...")
            try:
                text = r.recognize_google(audio, language="zh-CN")
                text = _restore_punctuation(text)
                from app.config import settings
                if settings.STT_MEDICAL_TERMS_BOOST:
                    text = _correct_medical_terms(text)
                if text.strip():
                    return text.strip(), ""
                else:
                    return "", "转录结果为空，请尝试更清晰的语音输入"
            except sr.UnknownValueError:
                return "", "语音识别无法理解该音频，请检查麦克风是否正常、音量是否足够"
            except sr.RequestError as e:
                logger.error(f"Google STT request failed: {e}")
                return "", f"Google 语音识别服务请求失败（可能网络受限），请检查网络连接或配置其他 STT 服务: {str(e)[:80]}"
            except Exception as e:
                logger.error(f"Google STT error: {e}")
                return "", f"语音识别失败: {str(e)[:100]}"

        except (ImportError, ModuleNotFoundError):
            pass
        except Exception as e:
            logger.warning(f"speech_recognition setup failed: {e}")
            return "", f"speech_recognition 初始化失败: {str(e)[:80]}"

        return "", "未安装 STT 引擎。请安装: pip install whisper openai-whisper SpeechRecognition imageio-ffmpeg"

    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return "", f"转录异常: {str(e)[:120]}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        wav_extra = tmp_path + ".wav" if tmp_path else None
        if wav_extra and os.path.exists(wav_extra):
            try:
                os.unlink(wav_extra)
            except Exception:
                pass


@router.get("/ws/connections")
async def ws_connections():
    """List active WebSocket connections."""
    return {"connections": list(active_connections.keys()), "count": len(active_connections)}
