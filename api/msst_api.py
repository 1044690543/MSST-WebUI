import os
import sys
import shutil
import random
import subprocess
from fastapi import FastAPI, BackgroundTasks
import warnings
import logging
from datetime import datetime
from time import time
# 添加以下代码以设置 inference 模块的路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from inference.msst_infer import MSSeparator
from utils.logger import get_logger
import yaml
import base64
from pydantic import BaseModel
logger = get_logger(console_level=logging.INFO)

app = FastAPI()


model_info = {
    'dereverb': 
        {
            'model_type': "mel_band_roformer",
            "model_path": "pretrain/single_stem_models/dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt",
            "config_path": "configs/single_stem_models/dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt.yaml"
        },
    "karaoke":
        {
            'model_type': "mel_band_roformer",
            "model_path": "pretrain/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
            "config_path": "configs/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt.yaml"
        },
    "htdemucs4":
        {
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

class VocalsResponse(BaseModel):
    vocals_base64: str
    others_base64: str

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

def msst_inference(file_path: str, output_dir: dict, model_type: str, model_path: str, model_config_path: str):
    if not config['debug']:
        warnings.filterwarnings("ignore", category=UserWarning)

    device_ids = config['device_ids'] if isinstance(config['device_ids'], list) else [config['device_ids']]

    start_time = time()

    separator = MSSeparator(
        model_type=model_type,
        config_path=model_config_path,
        model_path=model_path,
        device=config['device'],
        device_ids=device_ids,
        output_format=config['output_format'],
        use_tta=config['use_tta'],
        store_dirs=output_dir,
        audio_params={
            "wav_bit_depth": config['wav_bit_depth'],
            "flac_bit_depth": config['flac_bit_depth'],
            "mp3_bit_rate": config['mp3_bit_rate']
        },
        logger=logger,
        debug=config['debug']
    )
    success_files = separator.process_folder(file_path)
    separator.del_cache()
    logger.info(f"Successfully separated files: {success_files}, total time: {time() - start_time:.2f} seconds.")
    return success_files

def remove_dir(dir_path):
    shutil.rmtree(dir_path, ignore_errors=True)

def get_all_other_audio(merge_others_dir, karaoke_other_path, reverb_karaoke_path):
    all_other_path = os.path.join(merge_others_dir, "all_other.wav")
    cmd = [
        "ffmpeg",
        "-i", karaoke_other_path,
        "-i", reverb_karaoke_path,
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2",
        "-c:a", "libmp3lame",
        all_other_path
    ]
    try:
        subprocess.run(cmd, check=True)
        print("音频合并成功！")
    except subprocess.CalledProcessError as e:
        print("音频合并失败：", e)
    return all_other_path


@app.post("/vocals", response_model=VocalsResponse)
async def separate(sdata: SData, background_tasks: BackgroundTasks):
    cur_time = datetime.now().strftime("%Y%m%d%H%M%S")
    audio_folder = f"./api/data/vocals_{cur_time}_{random.randint(100, 999)}"
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

    logger.info(f"save path: {audio_folder}")
    base64_to_file(input_audio_path, sdata.input_audio_base64)

    logger.info(f"run karaoke model")
    karaoke_output_dir = {'karaoke': karaoke_dir, 'other': karaoke_other_dir}
    success_files = msst_inference(
        input_audio_dir,
        karaoke_output_dir,
        model_info["karaoke"]["model_type"],
        model_info["karaoke"]["model_path"],
        model_info["karaoke"]["config_path"],
    )

    noreverb_karaoke_path = os.path.join(noreverb_karaoke_dir, "input_audio_karaoke_noreverb.wav")
    reverb_karaoke_path = os.path.join(reverb_karaoke_dir, "input_audio_karaoke_reverb.wav")
    logger.info(f"run dereverb model")
    noreverb_output_dir = {'noreverb': noreverb_karaoke_dir, 'reverb': reverb_karaoke_dir}
    success_files = msst_inference(
        karaoke_dir,
        noreverb_output_dir,
        model_info["dereverb"]["model_type"],
        model_info["dereverb"]["model_path"],
        model_info["dereverb"]["config_path"],
    )
    vocals_path = noreverb_karaoke_path

    # 带混响的所有其他音轨
    # all_other_path = get_all_other_audio(merge_others_dir, karaoke_other_path, reverb_karaoke_path)
    # response = {"vocals_base64": file_to_base64(vocals_path), "others_base64": file_to_base64(all_other_path)}

    # 不带混响的所有其他音轨
    response = {"vocals_base64": file_to_base64(vocals_path), "others_base64": file_to_base64(karaoke_other_path)}
    background_tasks.add_task(remove_dir, audio_folder)
    return response


@app.post("/track_split", response_model=SplitResponse)
async def audio_track_split(sdata: SData, background_tasks: BackgroundTasks):
    cur_time = datetime.now().strftime("%Y%m%d%H%M%S")
    audio_folder = f"./api/data/split_{cur_time}_{random.randint(100, 999)}"
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
    )

    logger.info(f"run dereverb model")
    noreverb_output_dir = {'noreverb': reverb_htdemucs_dir, 'reverb': reverb_htdemucs_dir}

    success_files = msst_inference(
        htdemucs_vocals_dir,
        noreverb_output_dir,
        model_info["dereverb"]["model_type"],
        model_info["dereverb"]["model_path"],
        model_info["dereverb"]["config_path"],
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2769)
