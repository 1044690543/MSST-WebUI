# MSST-VOCALS 接口文档

### 提取干声服务-同步

- Request Url: /vocals
- Request method: POST
- Request port: 2769
- Request body

  ```
  {
      "input_audio_mode": "string",  # 输入形式，三选一['base64', 'path', 'url']
      "output_audio_mode": "string",  # 输出形式，二选一 ['base64', 'path']
      "input_audio_base64": "string",  # 音频的base64，非必传，但三个必传一个
      "input_audio_path": "float",  # 音频的路径，非必传，但三个必传一个
      "input_audio_url": "string"，  # 音频url，非必传，但三个必传一个
  }
  ```
- Response

  ```
  {
    "code": 200,
    "message": "Success",
    "success": True,
    "data": {
          "vocals_base64": "string",  # 音频干声数据，wav格式
          "others_base64": "string",  # 音频干声数据，wav格式
          "vocals_audio": "string",  # 音频干声数据，wav格式
          "backing_track": "string",  # 音频干声数据，wav格式
      }
  }
  # 路径和base64根据输入的出参形式而定
  
  code:200, "Success", "成功"
  code:201, "Faild", "失败"
  ```



```
启动命令 241为例。
sudo docker run -itd -e IS_MAAS=1 -e WORKER_IP=10.25.20.241 -e NACOS_ADDRESSES=10.25.20.20:38848 -e NACOS_SERVICE_IP=10.25.20.241 --gpus device=3 -p 2769:2769 -v /data/aigc_dir/seed_audio:/data/aigc_dir/seed_audio --restart=always --name msst msst:1.0

接口文档
http://10.25.20.223:8080/web/#/688507726/138245795
```

