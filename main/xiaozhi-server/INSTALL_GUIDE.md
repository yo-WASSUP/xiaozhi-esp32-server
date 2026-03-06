# Xiaozhi ESP32 Server 安装教程 (Conda)

## 前提条件

- 安装好 [Anaconda](https://www.anaconda.com/download) 或 [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- 有 NVIDIA 显卡（用于 FunASR GPU 加速，没有也可以用 CPU）

## 1. 创建 Conda 环境

```bash
conda create -n xiaozhi-esp32-server python=3.10 -y
conda activate xiaozhi-esp32-server
```

## 2. 安装 GPU 版 PyTorch（推荐）

必须先装 PyTorch，再装其他依赖，否则 pip 会装 CPU 版覆盖。

```bash
# GPU 版（NVIDIA 显卡，CUDA 12.1）
pip install torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu121
```

如果没有 NVIDIA 显卡，跳过这步，后面 pip install 会自动装 CPU 版。
装完后记得把 `.config.yaml` 里 FunASR 的 `device` 改成 `cpu`。

## 3. 安装项目依赖

```bash
cd main/xiaozhi-server
pip install -r requirements.txt
```

如果下载慢，用国内镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 4. 验证安装

```bash
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

应该输出：
```
PyTorch: 2.2.2
CUDA: True    # GPU版显示True，CPU版显示False
```

## 5. 配置

复制并修改配置文件：

```bash
cp data/.config.yaml.example data/.config.yaml
# 编辑 data/.config.yaml，填入你的 API Key 等信息
```

## 6. 下载模型

FunASR 和 SileroVAD 的模型会在首次运行时自动下载到 `models/` 目录。
如果网络不好，可以手动下载放到对应目录。

## 7. 启动

```bash
python app.py
```

## 常见问题

### PyTorch 报 "Torch not compiled with CUDA enabled"
装的是 CPU 版 PyTorch。按第 2 步重新装 GPU 版：
```bash
pip install torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu121
```

### pip install 报错 "Microsoft Visual C++ 14.0 or greater is required"
安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，勾选 "C++ build tools"。

### funasr 安装失败
先单独装：`pip install funasr==1.2.7`，看具体报错信息。
