import os
import sys
import shutil
import random
import threading
import requests
from pydub import AudioSegment
import uvicorn
import subprocess
from fastapi import FastAPI, BackgroundTasks
import warnings
import logging
from datetime import datetime
from time import time, perf_counter
# 添加以下代码以设置 inference 模块的路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from inference.msst_infer import MSSeparator
from utils.logger import get_logger
import yaml
import base64
from pydantic import BaseModel
from typing import Optional, Literal
logger = get_logger(console_level=logging.INFO)

from constents import SERVICE_IP, SERVICE_PORT, MSST_DIR, MSST_DIR_TMP, IS_MAAS, MSST_INFER_OBJECT
from nacos_service import service_register, config_register, service_beat
from schema.response import GeneralResponse, RespStatus
from clogs import clogger

app = FastAPI()


model_info = {
    'dereverb': 
        {
            'model_name': "dereverb",
            'model_type': "mel_band_roformer",
            "model_path": "pretrain/single_stem_models/dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt",
            "config_path": "configs/single_stem_models/dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt.yaml"
        },
    "karaoke":
        {
            'model_name': "karaoke",
            'model_type': "mel_band_roformer",
            "model_path": "pretrain/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
            "config_path": "configs/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt.yaml"
        },
    "htdemucs4":
        {
            'model_name': "htdemucs4",
            'model_type': "htdemucs",
            "model_path": "pretrain/multi_stem_models/HTDemucs4_6stems.th",
            "config_path": "configs/multi_stem_models/HTDemucs4_6stems.th.yaml"
        }
}

# Load configuration from config file
with open("api/config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

class SData(BaseModel):
    input_audio_base64: str

class VocalsData(BaseModel):
    input_audio_mode: Literal['base64', 'path', 'url'] = 'url'
    output_audio_mode: Literal['base64', 'path', 'base64-all'] = 'path'
    input_audio_base64: Optional[str] = None
    input_audio_path: Optional[str] = None
    input_audio_url: Optional[str] = None

class VocalsResponse(BaseModel):
    vocals_base64: Optional[str] = None
    others_base64: Optional[str] = None
    vocals_audio: Optional[str] = None
    backing_track: Optional[str] = None

class SplitResponse(BaseModel):
    drums_base64: str
    bass_base64: str
    guitar_base64: str
    piano_base64: str
    others_base64: str
    reverb_base64: str
    vocals_base64: str

def file_to_base64(file_path: str):
    with open(file_path, "rb") as file:
        file_content = file.read()
        base64_data = base64.b64encode(file_content)
        return base64_data.decode("utf-8")

def base64_to_file(file_path: str, base64_data: str):
    decoded_data = base64.b64decode(base64_data)
    with open(file_path, 'wb') as file:
        file.write(decoded_data)

def msst_inference(file_path: str, output_dir: dict, model_type: str, model_path: str, model_config_path: str, model_name: str):
    if not config['debug']:
        warnings.filterwarnings("ignore", category=UserWarning)

    device_ids = config['device_ids'] if isinstance(config['device_ids'], list) else [config['device_ids']]

    start_time = time()

    separator_name = f"separator_{model_name}"

    if separator_name in MSST_INFER_OBJECT:
        separator = MSST_INFER_OBJECT[separator_name]
        clogger.info(f"MSST_INFER_OBJECT:{MSST_INFER_OBJECT}")
        clogger.info(f"Using existing {separator_name} object.")
    else:
        clogger.info(f"Creating new {separator_name} object.")
        separator = MSSeparator(
            model_type=model_type,
            config_path=model_config_path,
            model_path=model_path,
            device=config['device'],
            device_ids=device_ids,
            output_format=config['output_format'],
            use_tta=config['use_tta'],
            audio_params={
                "wav_bit_depth": config['wav_bit_depth'],
                "flac_bit_depth": config['flac_bit_depth'],
                "mp3_bit_rate": config['mp3_bit_rate']
            },
            logger=logger,
            debug=config['debug'],
            inference_params = {
                    "batch_size": 12,
                    "num_overlap": None,
                    "chunk_size": None,
                    "normalize": None
                }
        )
        MSST_INFER_OBJECT[separator_name] = separator
    success_files = separator.process_folder(file_path, output_dir)
    # separator.del_cache()
    clogger.info(f"Successfully separated files: {success_files}, total time: {time() - start_time:.2f} seconds.")
    return success_files

def remove_dir(dir_path):
    shutil.rmtree(dir_path, ignore_errors=True)

def get_all_other_audio(merge_others_dir, karaoke_other_path, reverb_karaoke_path):
    all_other_path = os.path.join(merge_others_dir, "all_other.wav")
    try:
        audio1 = AudioSegment.from_wav(karaoke_other_path)
        audio2 = AudioSegment.from_wav(reverb_karaoke_path)
        audio3 = audio1.overlay(audio2)
        audio3.export(all_other_path, format="wav")
        print("音频合并成功！")
    except subprocess.CalledProcessError as e:
        print("音频合并失败：", e)
    return all_other_path

def download_audio_from_url(url: str, save_path: str):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # 如果请求失败则抛出异常
    except Exception as e:
        print(f"下载过程中出现错误：{e}")
        return
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:  # 过滤掉 keep-alive 的空块
                f.write(chunk)
    print(f"文件已下载到 {save_path}")

@app.post("/vocals", response_model=GeneralResponse)
async def separate(vdata: VocalsData, background_tasks: BackgroundTasks):
    response = GeneralResponse()
    start_time = perf_counter()
    cur_time = datetime.now().strftime("%Y%m%d%H%M%S")
    vocals_dir_name = f"vocals_{cur_time}_{random.randint(100, 999)}"
    clogger.info(f"id: {vocals_dir_name}")
    audio_folder = f"{MSST_DIR_TMP}/{vocals_dir_name}"
    return_folder = f"{MSST_DIR}/{vocals_dir_name}"
    input_audio_dir = os.path.join(audio_folder, "input_audio")
    karaoke_dir = os.path.join(audio_folder, "karaoke")
    karaoke_other_dir = os.path.join(audio_folder, "karaoke_other")
    noreverb_karaoke_dir = os.path.join(audio_folder, "noreverb_karaoke")
    reverb_karaoke_dir = os.path.join(audio_folder, "reverb_karaoke")
    merge_others_dir =os.path.join(audio_folder, "merge_others")
    for item in [audio_folder, input_audio_dir, karaoke_dir, karaoke_other_dir, noreverb_karaoke_dir, reverb_karaoke_dir, merge_others_dir]:
        os.makedirs(item, exist_ok=True)
    input_audio_path = os.path.join(input_audio_dir, "input_audio.wav")
    karaoke_path = f"{karaoke_dir}/input_audio_karaoke.wav"
    karaoke_other_path = f"{karaoke_other_dir}/input_audio_other.wav"

    clogger.info(f"save path: {audio_folder}")

    clogger.info(f"input_audio_mode: {vdata.input_audio_mode}, output_audio_mode: {vdata.output_audio_mode}")
    if vdata.input_audio_mode == "base64":
        base64_to_file(input_audio_path, vdata.input_audio_base64)
    elif vdata.input_audio_mode == "path":
        # 把 vdata.input_audio_path 复制到 input_audio_path
        if not os.path.exists(vdata.input_audio_path):
            clogger.error(f"输入音频路径 {vdata.input_audio_path} 不存在")
            response.set_obj(RespStatus.FAILED, success=False, err_msg=f"输入音频路径 {vdata.input_audio_path} 不存在")
            return response
        shutil.copy(vdata.input_audio_path, input_audio_path)
    elif vdata.input_audio_mode == "url":
        download_audio_from_url(vdata.input_audio_url, input_audio_path)
        if not os.path.exists(input_audio_path):
            clogger.error(f"{vdata.input_audio_url} 链接数据下载失败")
            response.set_obj(RespStatus.FAILED, success=False, err_msg=f"{vdata.input_audio_url} 链接数据下载失败")
            return response
    else:
        # 没有输入音频
        clogger.error(f"输入音频不可使用，请检查 input_audio_mode 和输入音频数据")
        response.set_obj(RespStatus.FAILED, success=False, err_msg="输入音频不可使用，请检查 input_audio_mode 和输入音频数据")
        return response

    clogger.info(f"run karaoke model")
    karaoke_output_dir = {'karaoke': karaoke_dir, 'other': karaoke_other_dir}
    success_files = msst_inference(
        input_audio_dir,
        karaoke_output_dir,
        model_info["karaoke"]["model_type"],
        model_info["karaoke"]["model_path"],
        model_info["karaoke"]["config_path"],
        model_info["karaoke"]["model_name"],
    )

    noreverb_karaoke_path = os.path.join(noreverb_karaoke_dir, "input_audio_karaoke_noreverb.wav")
    reverb_karaoke_path = os.path.join(reverb_karaoke_dir, "input_audio_karaoke_reverb.wav")
    clogger.info(f"run dereverb model")
    noreverb_output_dir = {'noreverb': noreverb_karaoke_dir, 'reverb': reverb_karaoke_dir}
    success_files = msst_inference(
        karaoke_dir,
        noreverb_output_dir,
        model_info["dereverb"]["model_type"],
        model_info["dereverb"]["model_path"],
        model_info["dereverb"]["config_path"],
        model_info["dereverb"]["model_name"],
    )
    vocals_path = noreverb_karaoke_path

    # 返回类型
    # 不带混响的所有其他音轨
    if vdata.output_audio_mode == "base64":
        response.data = {"vocals_base64": file_to_base64(vocals_path), "others_base64": file_to_base64(karaoke_other_path)}
    # 带混响的所有其他音轨
    elif vdata.output_audio_mode == "base64-all":
        all_other_path = get_all_other_audio(merge_others_dir, karaoke_other_path, reverb_karaoke_path)
        response.data = {"vocals_base64": file_to_base64(vocals_path), "others_base64": file_to_base64(all_other_path)}
    # 返回音频路径
    elif vdata.output_audio_mode == "path":
        os.makedirs(return_folder, exist_ok=True)
        return_vocals_audio_path = os.path.join(return_folder, "vocals_audio.wav")
        return_backing_track_path = os.path.join(return_folder, "backing_track.wav")
        shutil.copy(vocals_path, return_vocals_audio_path)
        shutil.copy(karaoke_other_path, return_backing_track_path)
        response.data = {"vocals_audio": return_vocals_audio_path, "backing_track": return_backing_track_path}
        clogger.info(f"response: {response}")

    # background_tasks.add_task(remove_dir, audio_folder)
    clogger.info(f"提取干声总耗时: {perf_counter() - start_time:.1f}s")
    return response


@app.post("/track_split", response_model=SplitResponse)
async def audio_track_split(sdata: SData, background_tasks: BackgroundTasks):
    cur_time = datetime.now().strftime("%Y%m%d%H%M%S")
    audio_folder = f"{MSST_DIR_TMP}/split_{cur_time}_{random.randint(100, 999)}"
    input_audio_dir = f"{audio_folder}/input_audio"
    htdemucs_dir = f"{audio_folder}/htdemucs"
    htdemucs_vocals_dir = f"{audio_folder}/htdemucs/vocals"
    reverb_htdemucs_dir = f"{audio_folder}/htdemucs_reverb"
    for item in [audio_folder, htdemucs_dir, reverb_htdemucs_dir, input_audio_dir, htdemucs_vocals_dir]:
        os.makedirs(item, exist_ok=True)
    input_audio_path = os.path.join(input_audio_dir, "input_audio.wav")
    base64_to_file(input_audio_path, sdata.input_audio_base64)
    drums_path = f"{htdemucs_dir}/input_audio_drums.wav"
    bass_path = f"{htdemucs_dir}/input_audio_bass.wav"
    guitar_path = f"{htdemucs_dir}/input_audio_guitar.wav"
    piano_path = f"{htdemucs_dir}/input_audio_piano.wav"
    others_path = f"{htdemucs_dir}/input_audio_other.wav"
    reverb_path = f"{reverb_htdemucs_dir}/input_audio_vocals_reverb.wav"
    noreverb_vocals_path = f"{reverb_htdemucs_dir}/input_audio_vocals_noreverb.wav"

    karaoke_output_dir = {'vocals': htdemucs_vocals_dir, 'drums': htdemucs_dir, 'bass': htdemucs_dir, 'guitar': htdemucs_dir, 'piano': htdemucs_dir, 'other': htdemucs_dir}
    success_files = msst_inference(
        input_audio_dir,
        karaoke_output_dir,
        model_info["htdemucs4"]["model_type"],
        model_info["htdemucs4"]["model_path"],
        model_info["htdemucs4"]["config_path"],
        model_info["htdemucs4"]["model_name"],
    )

    clogger.info(f"run dereverb model")
    noreverb_output_dir = {'noreverb': reverb_htdemucs_dir, 'reverb': reverb_htdemucs_dir}

    success_files = msst_inference(
        htdemucs_vocals_dir,
        noreverb_output_dir,
        model_info["dereverb"]["model_type"],
        model_info["dereverb"]["model_path"],
        model_info["dereverb"]["config_path"],
        model_info["dereverb"]["model_name"],
    )

    response = {
        "drums_base64" : file_to_base64(drums_path),
        "bass_base64" : file_to_base64(bass_path),
        "guitar_base64" : file_to_base64(guitar_path),
        "piano_base64" : file_to_base64(piano_path),
        "others_base64" : file_to_base64(others_path),
        "reverb_base64" : file_to_base64(reverb_path),
        "vocals_base64" : file_to_base64(noreverb_vocals_path)
    }
    return response


if __name__ == "__main__":
    if IS_MAAS:
        service_register()  # 注册服务
        config_register()  # 发送配置
        threading.Timer(5, service_beat).start()  # 心跳
        logger.info("服务注册成功")
    uvicorn.run(app, host=SERVICE_IP, port=SERVICE_PORT)
