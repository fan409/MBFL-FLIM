# FLIM 识别实验步骤

## 环境准备

### 1. 在超绝GPU服务器上安装Docker和Ollama服务

#### 拉取Docker镜像
```bash
docker pull lero11/cuda:12.2.2-cudnn8-devel-ubuntu22.04-py3.10
```

> 参考链接：https://zhuanlan.zhihu.com/p/666672725

#### 检查GPU状态
确保Docker容器内可以使用宿主机的GPU（需安装NVIDIA GPU + NVIDIA驱动 + NVIDIA Container Toolkit）：
```bash
nvidia-smi
```

#### 运行Docker容器
为了让容器长期运行（不退出销毁）：
```bash
docker run --gpus all -d --name ollama_gpu -p <ollama_port>:11434 lero11/cuda:12.2.2-cudnn8-devel-ubuntu22.04-py3.10 tail -f /dev/null
```
**参数说明：**
- `<ollama_port>`: Ollama服务映射的端口号，例如：11434、11436、11437等

#### 进入容器并安装Ollama
```bash
docker exec -it ollama_gpu bash
```

在容器内执行以下命令安装Ollama：
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### 启动Ollama服务并下载模型
安装完成后启动服务：
```bash
ollama serve &
```

测试运行并下载 `deepseek-rl:14b` 模型：
```bash
ollama pull deepseek-rl:14b
```

---

### 2. 端口转发设置

#### 基础端口转发（临时）
由于外部无法直接SSH进入138服务器，需在**138服务器上建立反向隧道**到目标服务器：

```bash
ssh -R <forward_port>:localhost:<ollama_port> rs@<target_server_ip>
```

**参数说明：**
- `<forward_port>`: 转发端口号，例如：11437、11438、11439等
- `<ollama_port>`: Ollama服务实际运行的端口号
- `<target_server_ip>`: 目标服务器IP地址，例如：101.42.4.197

#### 端口转发配置示例：
```bash
# 示例1：将本地11434端口转发到远程11437端口
ssh -R 11437:localhost:11434 rs@101.42.4.197

# 示例2：将本地11436端口转发到远程11438端口  
ssh -R 11438:localhost:11436 rs@101.42.4.197

# 示例3：将本地11435端口转发到远程11439端口
ssh -R 11439:localhost:11435 rs@101.42.4.197
```

#### 端口转发服务化（持久化 - 推荐）

为了确保端口转发在SSH连接断开后仍然保持，可以创建系统服务：

##### 创建SSH配置文件
在138服务器上创建SSH配置文件：
```bash
sudo nano /etc/systemd/system/ollama-tunnel.service
```

添加以下内容：
```ini
[Unit]
Description=Ollama SSH Tunnel Service
After=network.target

[Service]
Type=simple
User=rs
ExecStart=/usr/bin/ssh -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -N -R <forward_port>:localhost:<ollama_port> rs@<target_server_ip>
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**参数说明：**
- `<forward_port>`: 转发端口号，例如：11437、11438、11439等
- `<ollama_port>`: Ollama服务实际运行的端口号
- `<target_server_ip>`: 目标服务器IP地址

##### 服务配置示例：
```ini
# 使用11438端口转发
ExecStart=/usr/bin/ssh -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -N -R 11438:localhost:11434 rs@101.42.4.197

# 使用11439端口转发
ExecStart=/usr/bin/ssh -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -N -R 11439:localhost:11434 rs@101.42.4.197
```

##### 启用并启动服务
```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable ollama-tunnel.service

# 启动服务
sudo systemctl start ollama-tunnel.service

# 检查服务状态
sudo systemctl status ollama-tunnel.service

# 查看服务日志
sudo journalctl -u ollama-tunnel.service -f
```

##### 服务管理命令
```bash
# 停止服务
sudo systemctl stop ollama-tunnel.service

# 重启服务
sudo systemctl restart ollama-tunnel.service

# 禁用开机自启
sudo systemctl disable ollama-tunnel.service
```

#### 配置SSH免密登录（可选）
为了避免服务需要密码，可以设置SSH密钥认证：
```bash
# 在138服务器生成SSH密钥（如果还没有）
ssh-keygen -t rsa -b 4096

# 将公钥复制到目标服务器
ssh-copy-id rs@101.42.4.197
```

#### 连通性测试
在客户端服务器上检测是否连通（返回版本号则表示成功）：
```bash
curl http://<target_server_ip>:<forward_port>/api/version
```

**测试示例：**
```bash
# 测试11438端口
curl http://101.42.4.197:11438/api/version

# 测试11439端口
curl http://101.42.4.197:11439/api/version
```

---

## FLIM识别实验执行

### 3. 准备FLIM识别脚本

#### 文件操作
- 将文件  
/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/RSPlayGround/rs_STEnv_playground/demo2STEnv/README_FLIM_Identification_in_Server.md
  `/home/rs/WorkEx/Projects/SoftwareTesting/0ExperimentPlayGround/RSPlayGround/rs_STEnv_playground/demo2STEnv/FLIM_Identification.py`  
  复制到  
  `/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/FLIMRecognitionResult/OFLIMRecognitionScripts`  
  并将 `FLIM_Identification.py` 重命名为 `FLIM_Identification-1436.py`

#### 配置修改
- 修改文件 `FLIM_Identification.py` 中的端口配置：
  - 将 `"http://localhost:11434"` 修改为 `"http://<target_server_ip>:<forward_port>"`
  
**配置示例：**
```python
# 使用11438端口
"http://101.42.4.197:11438"

# 使用11439端口  
"http://101.42.4.197:11439"

# 使用11437端口
"http://101.42.4.197:11437"
```

- 修改 `main` 函数中的 `project` 参数为需要运行的项目：
  - 先测试 `JxPath`
  - 如果可以运行完成，继续运行 `Jsoup`

---

## 执行流程说明

1. **环境准备阶段**：在GPU服务器上完成Docker容器、Ollama服务和deepseek模型的安装
2. **网络配置阶段**：设置端口转发（推荐使用服务化方式确保持久化）
3. **实验执行阶段**：配置并运行FLIM识别脚本，调用远程GPU资源进行代码分析

**端口配置总结：**
- **Ollama服务端口**：Docker容器内Ollama服务运行的端口（通常为11434）
- **容器映射端口**：Docker容器映射到宿主机的端口（可自定义，如11436、11437等）
- **转发端口**：通过SSH隧道转发到目标服务器的端口（可自定义，如11438、11439等）

**持久化优势：**
- 系统重启后自动恢复
- SSH连接断开自动重连
- 支持监控和日志记录
- 便于管理和维护

完成以上所有步骤后，即可在ZO主机上顺利运行FLIM识别实验，充分利用超绝服务器的GPU计算资源。