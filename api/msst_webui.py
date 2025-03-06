import os
import sys
import shutil
import random
import gradio as gr
import warnings
import logging
from datetime import datetime
from time import time
import yaml
import base64

# 添加 inference 模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from inference.msst_infer import MSSeparator
from utils.logger import get_logger

logger = get_logger(console_level=logging.INFO)

# 读取配置文件
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(CONFIG_PATH, "r") as config_file:
    config = yaml.safe_load(config_file)

model_info = {
    'dereverb': {
        'model_type': "mel_band_roformer",
        "model_path": "pretrain/single_stem_models/dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt",
        "config_path": "configs/single_stem_models/dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt.yaml"
    },
    "karaoke": {
        'model_type': "mel_band_roformer",
        "model_path": "pretrain/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
        "config_path": "configs/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt.yaml"
    },
    "htdemucs4": {
        'model_type': "htdemucs",
        "model_path": "pretrain/multi_stem_models/HTDemucs4_6stems.th",
        "config_path": "configs/multi_stem_models/HTDemucs4_6stems.th.yaml"
    }
}


def file_to_base64(file_path: str):
    """将音频文件转换为 base64 编码"""
    with open(file_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")

def base64_to_file(file_path: str, base64_data: str):
    """将 base64 编码的数据写入文件"""
    with open(file_path, 'wb') as file:
        file.write(base64.b64decode(base64_data))

def msst_inference(input_dir: str, output_dir: dict, model_type: str, model_path: str, model_config_path: str):
    """运行音频分离模型"""
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

    success_files = separator.process_folder(input_dir)
    separator.del_cache()
    logger.info(f"成功分离音频文件: {success_files}，耗时: {time() - start_time:.2f} 秒")
    return success_files

def remove_dir(dir_path):
    """删除目录"""
    shutil.rmtree(dir_path, ignore_errors=True)

def separate(input_audio):
    """分离人声"""
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
    shutil.copyfile(input_audio, input_audio_path)

    karaoke_path = f"{karaoke_dir}/input_audio_karaoke.wav"
    karaoke_other_path = f"{karaoke_other_dir}/input_audio_other.wav"

    logger.info(f"保存路径: {audio_folder}")

    karaoke_output_dir = {'karaoke': karaoke_dir, 'other': karaoke_other_dir}
    msst_inference(
        os.path.dirname(input_audio_path),
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
    karaoke_other_path = os.path.join(karaoke_other_dir, "input_audio_other.wav")
    return vocals_path, karaoke_other_path

def audio_track_split(input_audio):
    """分离音轨"""
    cur_time = datetime.now().strftime("%Y%m%d%H%M%S")
    audio_folder = f"./api/data/split_{cur_time}_{random.randint(100, 999)}"
    input_audio_dir = f"{audio_folder}/input_audio"
    htdemucs_dir = f"{audio_folder}/htdemucs"
    htdemucs_vocals_dir = f"{audio_folder}/htdemucs/vocals"
    reverb_htdemucs_dir = f"{audio_folder}/htdemucs_reverb"
    for item in [audio_folder, htdemucs_dir, reverb_htdemucs_dir, input_audio_dir, htdemucs_vocals_dir]:
        os.makedirs(item, exist_ok=True)
    input_audio_path = os.path.join(input_audio_dir, "input_audio.wav")
    shutil.copyfile(input_audio, input_audio_path)

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

    return [noreverb_vocals_path, drums_path, bass_path, guitar_path, piano_path, reverb_path, others_path]

def main():
    with gr.Blocks() as demo:
        gr.Markdown("# 音频处理接口")

        with gr.Tab("分离人声"):
            with gr.Column():
                input_audio = gr.Audio(label="输入音频文件", type="filepath")
                separate_button = gr.Button("分离")
            output_vocals = gr.Audio(label="分离出的人声音频")
            output_others = gr.Audio(label="分离出的其他音轨音频")
            separate_button.click(separate, inputs=input_audio, outputs=[output_vocals, output_others])

        with gr.Tab("音轨分离"):
            with gr.Column():
                input_audio_split = gr.Audio(label="输入音频文件", type="filepath")
                audio_track_split_button = gr.Button("分离")
            outputs = [gr.Audio(label=f"分离出的 {stem} 音轨") for stem in ["人声", "鼓", "贝斯", "吉他", "钢琴", "混响", "其他"]]
            audio_track_split_button.click(audio_track_split, inputs=input_audio_split, outputs=outputs)

    demo.launch(server_name="0.0.0.0", server_port=8521)

if __name__ == "__main__":
    main()
